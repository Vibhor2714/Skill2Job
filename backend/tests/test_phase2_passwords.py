import hashlib
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, User, JobSeekerProfile, OTPRecord
from app.auth import is_legacy_sha256_hash, verify_password


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def _cleanup_user(email: str):
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


def test_registration_stores_argon2id_and_rejects_weak_passwords(client, capsys):
    email = "argon2_new_user@example.com"
    _cleanup_user(email)

    # Weak password rejected
    weak_res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Weak Pass User",
            "email": email,
            "password": "short",
            "confirm_password": "short",
        },
    )
    assert weak_res.status_code == 400

    # Strong password succeeds and stores Argon2id
    reg_res = client.post(
        "/api/auth/register",
        json={
            "full_name": "Argon2 User",
            "email": email,
            "password": "StrongPassword123",
            "confirm_password": "StrongPassword123",
        },
    )
    assert reg_res.status_code == 200
    body = reg_res.json()
    assert "password" not in body["user"]
    assert "hashed_password" not in body["user"]
    assert "access_token" not in body

    import re
    m = re.search(r"\[DEVELOPMENT OTP\] Code\s*:\s*(\d{6})", capsys.readouterr().out)
    assert m is not None
    ver_res = client.post("/api/auth/verify-email", json={"email": email, "code": m.group(1)})
    assert ver_res.status_code == 200

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.email == email).first()
        assert user is not None
        assert user.hashed_password.startswith("$argon2id$")
        assert verify_password("StrongPassword123", user.hashed_password)
    finally:
        db.close()

    # Correct password authenticates
    ok_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "StrongPassword123"},
    )
    assert ok_login.status_code == 200
    login_body = ok_login.json()
    assert "password" not in login_body["user"]
    assert "hashed_password" not in login_body["user"]

    # Incorrect password rejected with generic error
    bad_login = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongPassword123"},
    )
    assert bad_login.status_code == 401

    # Nonexistent email returns same generic error
    unknown_login = client.post(
        "/api/auth/login",
        json={"email": "nonexistent_user_xyz@example.com", "password": "WrongPassword123"},
    )
    assert unknown_login.status_code == 401
    assert bad_login.json()["detail"] == unknown_login.json()["detail"]

    _cleanup_user(email)


def test_legacy_sha256_login_and_transparent_upgrade(client):
    email = "legacy_sha256_user@example.com"
    raw_password = "LegacyPassword99"
    legacy_hash = hashlib.sha256(("skills2job_salt_" + raw_password).encode("utf-8")).hexdigest()
    assert is_legacy_sha256_hash(legacy_hash)

    _cleanup_user(email)
    db = SessionLocal()
    try:
        u = User(
            email=email,
            hashed_password=legacy_hash,
            full_name="Legacy User",
            role="JOB_SEEKER",
            is_email_verified=True,
        )
        db.add(u)
        db.commit()
    finally:
        db.close()

    # 1. Incorrect legacy password must NOT upgrade the hash
    bad_res = client.post(
        "/api/auth/login",
        json={"email": email, "password": "WrongLegacyPassword"},
    )
    assert bad_res.status_code == 401

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        assert u.hashed_password == legacy_hash
    finally:
        db.close()

    # 2. Correct legacy password logs in AND upgrades hash to Argon2id
    good_res = client.post(
        "/api/auth/login",
        json={"email": email, "password": raw_password},
    )
    assert good_res.status_code == 200
    assert good_res.json()["access_token"]

    db = SessionLocal()
    try:
        u = db.query(User).filter(User.email == email).first()
        assert u.hashed_password.startswith("$argon2id$")
        assert u.hashed_password != legacy_hash
    finally:
        db.close()

    # 3. Subsequent login works with upgraded Argon2id hash
    relogin_res = client.post(
        "/api/auth/login",
        json={"email": email, "password": raw_password},
    )
    assert relogin_res.status_code == 200

    _cleanup_user(email)


def test_demo_login_and_no_password_leakage(client):
    demo_res = client.get("/api/auth/demo/job_seeker")
    assert demo_res.status_code == 200
    data = demo_res.json()
    assert "password" not in data["user"]
    assert "hashed_password" not in data["user"]

    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert "password" not in me_res.json()
    assert "hashed_password" not in me_res.json()

    prof_res = client.get("/api/profile/job-seeker", headers=headers)
    assert prof_res.status_code == 200
    assert "hashed_password" not in prof_res.json()
