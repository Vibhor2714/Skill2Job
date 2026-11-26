from datetime import datetime, timedelta
import re
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, User, JobSeekerProfile, OTPRecord
from app.otp_service import OTPService, OTPDeliveryService, FutureSMSProvider


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _cleanup(email: str):
    db = SessionLocal()
    try:
        db.query(OTPRecord).filter(OTPRecord.email == email).delete()
        u = db.query(User).filter(User.email == email).first()
        if u:
            db.query(JobSeekerProfile).filter(JobSeekerProfile.user_id == u.id).delete()
            db.delete(u)
        db.commit()
    finally:
        db.close()


def _create_verified_user(email: str) -> User:
    from app.auth import hash_password

    db = SessionLocal()
    try:
        user = User(
            email=email,
            hashed_password=hash_password("VerifiedTestPass123"),
            full_name="Verified OTP Tester",
            role="JOB_SEEKER",
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        db.add(JobSeekerProfile(user_id=user.id))
        db.commit()
        return user
    finally:
        db.close()


def _extract_code_from_stdout(output: str) -> str:
    m = re.search(r"\[DEVELOPMENT OTP\] Code\s*:\s*(\d{6})", output)
    assert m is not None, f"OTP code not found in backend terminal output: {output}"
    return m.group(1)


def test_register_hashes_otp_prints_masked_to_terminal_and_rejects_123456(client, capsys):
    email = "otp_register_test@example.com"
    _cleanup(email)

    reg_res = client.post(
        "/api/auth/register",
        json={
            "full_name": "OTP Tester",
            "email": email,
            "password": "OtpTestPassword123",
            "confirm_password": "OtpTestPassword123",
        },
    )
    assert reg_res.status_code == 200
    captured = capsys.readouterr().out
    assert "[DEVELOPMENT OTP]" in captured
    assert "ot***@example.com" in captured
    assert email not in captured  # Email must be masked in logs
    real_code = _extract_code_from_stdout(captured)

    # DB must store a 64-char HMAC-SHA256 hash, never plaintext
    db = SessionLocal()
    try:
        rec = (
            db.query(OTPRecord)
            .filter(OTPRecord.email == email, OTPRecord.is_used == False)
            .order_by(OTPRecord.id.desc())
            .first()
        )
        assert rec is not None
        assert rec.code != real_code
        assert len(rec.code) == 64
        delta_seconds = (rec.expires_at - rec.created_at).total_seconds()
        assert 290 <= delta_seconds <= 310  # 5 minutes
    finally:
        db.close()

    if real_code != "123456":
        assert client.post("/api/auth/verify-email", json={"email": email, "code": "123456"}).status_code == 400

    ok_verify = client.post("/api/auth/verify-email", json={"email": email, "code": real_code})
    assert ok_verify.status_code == 200
    assert ok_verify.json()["success"] is True

    # Single-use enforcement
    assert client.post("/api/auth/verify-email", json={"email": email, "code": real_code}).status_code == 400
    _cleanup(email)


def test_otp_request_invalidates_previous_never_leaks_and_handles_expiry(client, capsys, monkeypatch):
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    email = "otp_login_test@example.com"
    _cleanup(email)
    _create_verified_user(email)

    req1 = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert req1.status_code == 200
    assert "code" not in req1.json()
    assert "dev_code" not in req1.json()
    assert req1.json()["expires_in_minutes"] == 5
    code1 = _extract_code_from_stdout(capsys.readouterr().out)

    # Second request invalidates first OTP
    req2 = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert req2.status_code == 200
    code2 = _extract_code_from_stdout(capsys.readouterr().out)

    if code1 != code2:
        assert client.post("/api/auth/otp/verify", json={"email": email, "code": code1}).status_code == 400

    login_res = client.post("/api/auth/otp/verify", json={"email": email, "code": code2})
    assert login_res.status_code == 200
    assert login_res.json()["access_token"]

    # Expired hashed OTP rejected
    db = SessionLocal()
    try:
        expired_otp = OTPRecord(
            email=email,
            code=OTPService.hash_otp(email, "LOGIN", "654321"),
            purpose="LOGIN",
            expires_at=datetime.utcnow() - timedelta(minutes=1),
            attempts=0,
            is_used=False,
        )
        db.add(expired_otp)
        db.commit()
    finally:
        db.close()

    assert client.post("/api/auth/otp/verify", json={"email": email, "code": "654321"}).status_code == 400
    _cleanup(email)


@pytest.fixture(autouse=True)
def reset_limits():
    OTPService.reset_rate_limits()
    yield
    OTPService.reset_rate_limits()


def test_resend_cooldown_and_max_attempts_lockout(client, capsys, monkeypatch):
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "60")
    email = "otp_security_limits@example.com"
    _cleanup(email)
    _create_verified_user(email)

    # First request succeeds
    r1 = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert r1.status_code == 200
    real_code = _extract_code_from_stdout(capsys.readouterr().out)

    # Immediate resend blocked by 60s cooldown (429)
    r2 = client.post("/api/auth/otp/resend", json={"email": email, "purpose": "LOGIN"})
    assert r2.status_code == 429
    assert "wait" in r2.json()["detail"].lower()

    # 5 wrong attempts lock out the OTP (5th returns 429)
    wrong_code = "000000" if real_code != "000000" else "999999"
    for idx in range(5):
        bad = client.post("/api/auth/otp/verify", json={"email": email, "code": wrong_code})
        if idx < 4:
            assert bad.status_code == 400
            assert "remaining" in bad.json()["detail"].lower()
        else:
            assert bad.status_code == 429
            assert "maximum verification attempts" in bad.json()["detail"].lower()

    # Real code must now be locked out
    locked = client.post("/api/auth/otp/verify", json={"email": email, "code": real_code})
    assert locked.status_code == 429
    _cleanup(email)


def test_verification_status_and_already_verified_error(client, capsys):
    email = "otp_status_check@example.com"
    _cleanup(email)

    reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Status Checker",
            "email": email,
            "password": "OtpStatusPass123",
            "confirm_password": "OtpStatusPass123",
        },
    )
    assert reg.status_code == 200
    assert "access_token" not in reg.json()
    assert reg.json()["requires_verification"] is True
    real_code = _extract_code_from_stdout(capsys.readouterr().out)

    # Unverified user cannot log in
    unverified_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "OtpStatusPass123"},
    )
    assert unverified_login.status_code == 403

    # Verify email (does not auto-login)
    ver = client.post("/api/auth/verify-email", json={"email": email, "code": real_code})
    assert ver.status_code == 200
    assert ver.json()["success"] is True
    assert "access_token" not in ver.json()

    # Now user can log in and check verification status
    ok_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "OtpStatusPass123"},
    )
    assert ok_login.status_code == 200
    token = ok_login.json()["access_token"]

    st2 = client.get("/api/auth/verification-status", headers={"Authorization": f"Bearer {token}"})
    assert st2.status_code == 200
    assert st2.json()["is_email_verified"] is True

    # Re-verifying already verified account returns 400
    again = client.post("/api/auth/verify-email", json={"email": email, "code": real_code})
    assert again.status_code == 400
    assert "already verified" in again.json()["detail"].lower()

    # Unknown user returns 404
    unknown = client.post("/api/auth/verify-email", json={"email": "missing_user_otp@example.com", "code": "123456"})
    assert unknown.status_code == 404
    _cleanup(email)


def test_otp_generation_rate_limit(client, monkeypatch):
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("OTP_GEN_RATE_LIMIT", "2")
    email = "otp_ratelimit@example.com"
    _cleanup(email)
    _create_verified_user(email)

    assert client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"}).status_code == 200
    assert client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"}).status_code == 200
    limited = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert limited.status_code == 429
    _cleanup(email)


def test_production_refuses_console_otp_and_future_sms_provider_not_faked(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("OTP_DELIVERY_MODE", "console")
    with pytest.raises(RuntimeError, match="forbidden"):
        OTPDeliveryService(mode="console").deliver("user@example.com", "987654", "LOGIN", 5)

    sms_service = OTPDeliveryService(mode="sms")
    assert isinstance(sms_service.provider, FutureSMSProvider)
    with pytest.raises(NotImplementedError):
        sms_service.deliver("user@example.com", "987654", "LOGIN", 5)


def test_duplicate_registration_and_unverified_token_blocked(client, capsys):
    from app.auth import create_access_token

    email = "otp_duplicate_check@example.com"
    _cleanup(email)

    r1 = client.post(
        "/api/auth/register",
        json={
            "full_name": "Dup User",
            "email": email,
            "password": "DupPassword123",
            "confirm_password": "DupPassword123",
        },
    )
    assert r1.status_code == 200
    real_code = _extract_code_from_stdout(capsys.readouterr().out)
    assert real_code not in r1.text

    # Duplicate registration rejected
    r2 = client.post(
        "/api/auth/register",
        json={
            "full_name": "Dup User",
            "email": email,
            "password": "DupPassword123",
            "confirm_password": "DupPassword123",
        },
    )
    assert r2.status_code == 400

    # Even if an unverified user presents a signed JWT, protected route rejects with 403
    unverified_token = create_access_token({"sub": email, "role": "JOB_SEEKER", "id": 9999})
    me_res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {unverified_token}"})
    assert me_res.status_code == 403

    _cleanup(email)


def test_msg91_missing_config_and_mocked_delivery(client, monkeypatch):
    from unittest.mock import patch

    monkeypatch.delenv("MSG91_AUTH_KEY", raising=False)
    monkeypatch.delenv("MSG91_TEMPLATE_ID", raising=False)
    monkeypatch.delenv("MSG91_SENDER_ID", raising=False)

    with pytest.raises(RuntimeError, match="Missing MSG91 configuration"):
        OTPDeliveryService(mode="msg91")

    with pytest.raises(RuntimeError, match="Unsupported OTP_DELIVERY_MODE"):
        OTPDeliveryService(mode="invalid_provider")

    # Mock delivery during automated test so no external SMS/console side effect occurs
    email = "otp_mock_delivery@example.com"
    _cleanup(email)
    _create_verified_user(email)
    with patch.object(OTPDeliveryService, "deliver") as mock_deliver:
        res = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
        assert res.status_code == 200
        mock_deliver.assert_called_once()
        args, kwargs = mock_deliver.call_args
        delivered_code = kwargs.get("code") or args[1]
        assert len(delivered_code) == 6 and delivered_code.isdigit()
    _cleanup(email)


def test_no_hardcoded_otp_in_frontend_auth_pages():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    verify_page = (repo_root / "frontend" / "src" / "app" / "(auth)" / "verify-email" / "page.tsx").read_text(encoding="utf-8")
    login_page = (repo_root / "frontend" / "src" / "app" / "(auth)" / "login" / "page.tsx").read_text(encoding="utf-8")

    assert "123456" not in verify_page
    assert "123456" not in login_page
    assert "dev_code" not in verify_page
    assert "dev_code" not in login_page


def test_otp_purpose_isolation_and_invalid_purpose_rejected(client, capsys, monkeypatch):
    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    email = "otp_purpose_isolation@example.com"
    _cleanup(email)

    # 1. Register creates a VERIFY OTP for an unverified user
    reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Purpose Tester",
            "email": email,
            "password": "PurposePass123",
            "confirm_password": "PurposePass123",
        },
    )
    assert reg.status_code == 200
    verify_code = _extract_code_from_stdout(capsys.readouterr().out)

    # VERIFY OTP cannot be used on /api/auth/otp/verify (LOGIN endpoint)
    bad_login = client.post("/api/auth/otp/verify", json={"email": email, "code": verify_code})
    assert bad_login.status_code == 403

    # Resend with VERIFY preserves VERIFY purpose
    resend_verify = client.post("/api/auth/otp/resend", json={"email": email, "purpose": "VERIFY"})
    assert resend_verify.status_code == 200
    verify_code_2 = _extract_code_from_stdout(capsys.readouterr().out)

    # Complete email verification with VERIFY OTP
    ok_verify = client.post("/api/auth/verify-email", json={"email": email, "code": verify_code_2})
    assert ok_verify.status_code == 200

    # 2. Invalid purpose is rejected on request & resend
    assert client.post("/api/auth/otp/request", json={"email": email, "purpose": "ADMIN_BYPASS"}).status_code == 400
    assert client.post("/api/auth/otp/resend", json={"email": email, "purpose": "RESET"}).status_code == 400

    # Even for a verified user, a VERIFY OTP cannot be used on /api/auth/otp/verify (LOGIN)
    db = SessionLocal()
    try:
        db.add(
            OTPRecord(
                email=email,
                code=OTPService.hash_otp(email, "VERIFY", "246810"),
                purpose="VERIFY",
                expires_at=datetime.utcnow() + timedelta(minutes=5),
                attempts=0,
                is_used=False,
            )
        )
        db.commit()
    finally:
        db.close()
    assert client.post("/api/auth/otp/verify", json={"email": email, "code": "246810"}).status_code == 400

    # 3. Issue a LOGIN OTP for the verified user
    req_login = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert req_login.status_code == 200
    login_code = _extract_code_from_stdout(capsys.readouterr().out)

    # Even if user were unverified, a LOGIN OTP must not verify email
    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        u.is_email_verified = False
        db.commit()
    finally:
        db.close()

    cross_purpose = client.post("/api/auth/verify-email", json={"email": email, "code": login_code})
    assert cross_purpose.status_code == 400

    _cleanup(email)


def test_otp_login_does_not_auto_create_user_and_blocks_unverified(client, capsys):
    unknown_email = "unknown_otp_login@example.com"
    _cleanup(unknown_email)

    # Requesting LOGIN OTP or verifying OTP for unknown email must return 404 and not create user
    req_unknown = client.post("/api/auth/otp/request", json={"email": unknown_email, "purpose": "LOGIN"})
    assert req_unknown.status_code == 404

    ver_unknown = client.post("/api/auth/otp/verify", json={"email": unknown_email, "code": "654321"})
    assert ver_unknown.status_code == 404

    db = SessionLocal()
    try:
        assert db.query(User).filter(User.email == unknown_email).first() is None
    finally:
        db.close()

    # Unverified user cannot log in via /api/auth/otp/request or /api/auth/otp/verify
    unverified_email = "unverified_otp_login@example.com"
    _cleanup(unverified_email)
    reg = client.post(
        "/api/auth/register",
        json={
            "full_name": "Unverified User",
            "email": unverified_email,
            "password": "UnverifiedPass123",
            "confirm_password": "UnverifiedPass123",
        },
    )
    assert reg.status_code == 200
    verify_code = _extract_code_from_stdout(capsys.readouterr().out)

    assert client.post("/api/auth/otp/request", json={"email": unverified_email, "purpose": "LOGIN"}).status_code == 403
    assert client.post("/api/auth/otp/verify", json={"email": unverified_email, "code": verify_code}).status_code == 403

    _cleanup(unverified_email)


def test_concurrent_otp_verification_is_atomic(client, capsys, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    monkeypatch.setenv("OTP_RESEND_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("OTP_VERIFY_RATE_LIMIT", "50")
    email = "otp_concurrent_atomic@example.com"
    _cleanup(email)
    _create_verified_user(email)

    # 1. Two concurrent valid verification requests: only ONE can succeed
    req1 = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert req1.status_code == 200
    real_code = _extract_code_from_stdout(capsys.readouterr().out)

    def _submit(code: str):
        db = SessionLocal()
        try:
            OTPService.verify_otp(db, email=email, code=code, purpose="LOGIN")
            return 200
        except Exception as exc:
            return getattr(exc, "status_code", 500)
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(_submit, [real_code, real_code]))

    assert results.count(200) == 1
    assert results.count(400) == 1

    # 2. Concurrent wrong attempts: atomic increment locks out at 5 attempts without lost updates
    req2 = client.post("/api/auth/otp/request", json={"email": email, "purpose": "LOGIN"})
    assert req2.status_code == 200
    real_code_2 = _extract_code_from_stdout(capsys.readouterr().out)
    wrong_code = "000000" if real_code_2 != "000000" else "999999"

    with ThreadPoolExecutor(max_workers=5) as pool:
        wrong_results = list(pool.map(_submit, [wrong_code] * 5))

    assert all(code in (400, 429) for code in wrong_results)
    assert wrong_results.count(429) >= 1

    # Subsequent valid code must be rejected with 429 (locked out)
    assert _submit(real_code_2) == 429
    _cleanup(email)
