from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime, timedelta
import hashlib
import hmac
import os
import secrets
import threading
import time
from typing import Dict, List, Optional
from sqlalchemy import case
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.auth import SECRET_KEY
from app.database import OTPRecord, User

DEFAULT_OTP_EXPIRY_MINUTES = 5
DEFAULT_RESEND_COOLDOWN_SECONDS = 60
MAX_OTP_ATTEMPTS = 5
DEFAULT_GEN_RATE_LIMIT = 5
DEFAULT_GEN_WINDOW_SECONDS = 900  # 15 minutes
DEFAULT_VERIFY_RATE_LIMIT = 10
DEFAULT_VERIFY_WINDOW_SECONDS = 300  # 5 minutes


class OTPError(Exception):
    """Base exception for OTP operations carrying an HTTP status code."""

    def __init__(self, message: str, status_code: int = 400):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class OTPCooldownError(OTPError):
    """Raised when an OTP resend is requested before the cooldown period elapses."""

    def __init__(self, retry_after_seconds: int):
        self.retry_after_seconds = retry_after_seconds
        super().__init__(
            f"Please wait {retry_after_seconds} seconds before requesting a new OTP.",
            status_code=429,
        )


class OTPRateLimitError(OTPError):
    """Raised when OTP generation or verification exceeds rate limits."""

    def __init__(self, message: str = "Too many OTP requests. Please try again later."):
        super().__init__(message, status_code=429)


class RateLimiterBackend(ABC):
    """
    Abstract rate-limiter interface so the in-memory limiter can be swapped
    for a shared store (e.g., Redis) in multi-worker production deployments.
    """

    @abstractmethod
    def check_and_record(self, key: str, max_requests: int, window_seconds: int) -> None:
        """Record a request and raise OTPRateLimitError if the limit is exceeded."""

    @abstractmethod
    def reset(self) -> None:
        """Clear recorded rate-limit state (used in tests)."""


class SlidingWindowRateLimiter(RateLimiterBackend):
    """
    Thread-safe in-memory sliding-window rate limiter for single-process
    development/college-demo use.

    Limitation: State is stored in process memory, so counters reset on backend
    restart and are not shared across multiple worker processes. Replace with a
    shared RateLimiterBackend (e.g., Redis) when scaling to multiple workers.
    """

    def __init__(self) -> None:
        self._events: Dict[str, List[float]] = defaultdict(list)
        self._lock = threading.Lock()

    def check_and_record(self, key: str, max_requests: int, window_seconds: int) -> None:
        if max_requests <= 0 or window_seconds <= 0:
            return
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            recent = [t for t in self._events[key] if t > cutoff]
            if len(recent) >= max_requests:
                self._events[key] = recent
                raise OTPRateLimitError(
                    "Too many OTP attempts or requests. Please wait before trying again."
                )
            recent.append(now)
            self._events[key] = recent

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


_rate_limiter: RateLimiterBackend = SlidingWindowRateLimiter()


def mask_recipient(identifier: str) -> str:
    """Mask email address or phone number for safe terminal logging."""
    raw = (identifier or "").strip()
    if "@" in raw:
        local, domain = raw.split("@", 1)
        visible = local[:2] if len(local) >= 2 else local[:1]
        return f"{visible}***@{domain}"
    if len(raw) >= 4:
        return f"{'*' * max(4, len(raw) - 4)}{raw[-4:]}"
    return "******"


class OTPDeliveryProvider(ABC):
    """Abstract interface for OTP delivery channels."""

    @abstractmethod
    def send_otp(self, recipient: str, code: str, purpose: str, expires_in_minutes: int) -> None:
        """Deliver an OTP to the recipient."""


class ConsoleOTPProvider(OTPDeliveryProvider):
    """
    Development/college-demo provider that prints the OTP to the backend terminal.
    Permitted only when APP_ENV=development.
    """

    def send_otp(self, recipient: str, code: str, purpose: str, expires_in_minutes: int) -> None:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if app_env != "development":
            raise RuntimeError(
                "Console OTP delivery is only permitted when APP_ENV=development."
            )

        masked = mask_recipient(recipient)
        print(
            "\n"
            "==================================================\n"
            f"[DEVELOPMENT OTP] OTP generated successfully for user: {masked}\n"
            f"[DEVELOPMENT OTP] Purpose : {purpose}\n"
            f"[DEVELOPMENT OTP] Code    : {code}\n"
            f"[DEVELOPMENT OTP] Expires : {expires_in_minutes} minutes\n"
            "==================================================\n",
            flush=True,
        )


class FutureSMSProvider(OTPDeliveryProvider):
    """Placeholder interface for future SMS integration."""

    def send_otp(self, recipient: str, code: str, purpose: str, expires_in_minutes: int) -> None:
        raise NotImplementedError(
            "SMS delivery provider is not configured. "
            "Set OTP_DELIVERY_MODE=console with APP_ENV=development for local/demo terminal delivery."
        )


class MSG91OTPProvider(OTPDeliveryProvider):
    """
    Placeholder provider for future MSG91 SMS integration.
    Reads MSG91_AUTH_KEY, MSG91_TEMPLATE_ID, and MSG91_SENDER_ID only when OTP_DELIVERY_MODE=msg91.
    """

    def __init__(self) -> None:
        self.auth_key = os.getenv("MSG91_AUTH_KEY", "").strip()
        self.template_id = os.getenv("MSG91_TEMPLATE_ID", "").strip()
        self.sender_id = os.getenv("MSG91_SENDER_ID", "").strip()
        if not self.auth_key or not self.template_id or not self.sender_id:
            raise RuntimeError(
                "Missing MSG91 configuration: set MSG91_AUTH_KEY, MSG91_TEMPLATE_ID, "
                "and MSG91_SENDER_ID when OTP_DELIVERY_MODE=msg91."
            )

    def send_otp(self, recipient: str, code: str, purpose: str, expires_in_minutes: int) -> None:
        raise NotImplementedError(
            "MSG91 SMS delivery is intentionally not enabled in this college demo build."
        )


class OTPDeliveryService:
    """Selects and invokes the configured OTP delivery provider."""

    def __init__(self, mode: Optional[str] = None):
        raw_mode = mode or os.getenv("OTP_DELIVERY_MODE") or os.getenv("OTP_PROVIDER") or "console"
        self.mode = raw_mode.strip().lower()
        self.provider = self._resolve_provider(self.mode)

    @staticmethod
    def _resolve_provider(mode: str) -> OTPDeliveryProvider:
        app_env = os.getenv("APP_ENV", "development").strip().lower()
        if mode == "console":
            if app_env != "development":
                raise RuntimeError(
                    f"Configuration error: OTP_DELIVERY_MODE=console is forbidden when APP_ENV={app_env}. "
                    "Configure a real SMS/email provider in production."
                )
            return ConsoleOTPProvider()
        if mode == "msg91":
            return MSG91OTPProvider()
        if mode in ("sms", "twilio"):
            return FutureSMSProvider()
        raise RuntimeError(f"Unsupported OTP_DELIVERY_MODE '{mode}'. Supported: console, msg91, sms.")

    def deliver(self, recipient: str, code: str, purpose: str, expires_in_minutes: int) -> None:
        self.provider.send_otp(
            recipient=recipient,
            code=code,
            purpose=purpose,
            expires_in_minutes=expires_in_minutes,
        )


def validate_otp_configuration() -> None:
    """Fail fast at startup if production is misconfigured to use console OTP delivery."""
    OTPDeliveryService()


class OTPService:
    """Generates, hashes, stores, validates, rate-limits, and invalidates single-use OTPs."""

    @staticmethod
    def generate_code() -> str:
        return f"{secrets.randbelow(900000) + 100000}"

    @staticmethod
    def hash_otp(email: str, purpose: str, code: str) -> str:
        msg = f"{email.strip().lower()}:{purpose.strip().upper()}:{code.strip()}".encode("utf-8")
        return hmac.new(SECRET_KEY.encode("utf-8"), msg, hashlib.sha256).hexdigest()

    @classmethod
    def get_ttl_minutes(cls) -> int:
        try:
            val = int(os.getenv("OTP_EXPIRY_MINUTES", str(DEFAULT_OTP_EXPIRY_MINUTES)))
            return max(1, val)
        except ValueError:
            return DEFAULT_OTP_EXPIRY_MINUTES

    @classmethod
    def get_cooldown_seconds(cls) -> int:
        try:
            val = int(os.getenv("OTP_RESEND_COOLDOWN_SECONDS", str(DEFAULT_RESEND_COOLDOWN_SECONDS)))
            return max(0, val)
        except ValueError:
            return DEFAULT_RESEND_COOLDOWN_SECONDS

    @classmethod
    def reset_rate_limits(cls) -> None:
        _rate_limiter.reset()

    VALID_PURPOSES = {"VERIFY", "LOGIN"}

    @classmethod
    def issue_otp(
        cls,
        db: Session,
        email: str,
        purpose: str = "VERIFY",
        ttl_minutes: Optional[int] = None,
        client_ip: Optional[str] = None,
    ) -> int:
        normalized_email = email.strip().lower()
        normalized_purpose = (purpose or "").strip().upper()
        if normalized_purpose not in cls.VALID_PURPOSES:
            raise OTPError("Invalid OTP purpose. Must be VERIFY or LOGIN.", status_code=400)
        effective_ttl = ttl_minutes if ttl_minutes is not None else cls.get_ttl_minutes()
        now = datetime.utcnow()

        # Rate limit OTP generation per email
        gen_limit = int(os.getenv("OTP_GEN_RATE_LIMIT", str(DEFAULT_GEN_RATE_LIMIT)))
        _rate_limiter.check_and_record(
            f"gen:{normalized_email}", gen_limit, DEFAULT_GEN_WINDOW_SECONDS
        )
        if client_ip:
            _rate_limiter.check_and_record(
                f"gen_ip:{client_ip}", gen_limit * 3, DEFAULT_GEN_WINDOW_SECONDS
            )

        # Enforce resend cooldown (60 seconds default)
        cooldown = cls.get_cooldown_seconds()
        if cooldown > 0:
            latest = (
                db.query(OTPRecord)
                .filter(
                    OTPRecord.email == normalized_email,
                    OTPRecord.purpose == normalized_purpose,
                )
                .order_by(OTPRecord.id.desc())
                .first()
            )
            if latest and latest.last_sent_at:
                elapsed = (now - latest.last_sent_at).total_seconds()
                if elapsed < cooldown:
                    raise OTPCooldownError(max(1, int(cooldown - elapsed)))

        plain_code = cls.generate_code()
        hashed_code = cls.hash_otp(normalized_email, normalized_purpose, plain_code)
        expires_at = now + timedelta(minutes=effective_ttl)

        try:
            # Invalidate previous unused OTPs for this user & purpose atomically with new OTP creation
            db.query(OTPRecord).filter(
                OTPRecord.email == normalized_email,
                OTPRecord.purpose == normalized_purpose,
                OTPRecord.is_used == False,
            ).update({"is_used": True}, synchronize_session=False)

            user = db.query(User).filter(User.email == normalized_email).first()
            if user:
                user.verification_code = None

            otp_entry = OTPRecord(
                user_id=user.id if user else None,
                email=normalized_email,
                code=hashed_code,
                purpose=normalized_purpose,
                expires_at=expires_at,
                attempts=0,
                is_used=False,
                last_sent_at=now,
            )
            db.add(otp_entry)
            db.commit()
        except SQLAlchemyError as exc:
            db.rollback()
            raise OTPError("Failed to persist OTP. Please try again.", status_code=503) from exc

        try:
            OTPDeliveryService().deliver(
                recipient=normalized_email,
                code=plain_code,
                purpose=normalized_purpose,
                expires_in_minutes=effective_ttl,
            )
        except (RuntimeError, NotImplementedError) as exc:
            raise OTPError(f"OTP delivery configuration error: {exc}", status_code=503) from exc
        except Exception as exc:
            raise OTPError("Failed to deliver OTP. Please try again later.", status_code=502) from exc

        return effective_ttl

    @classmethod
    def verify_otp(
        cls,
        db: Session,
        email: str,
        code: str,
        purpose: Optional[str] = None,
        client_ip: Optional[str] = None,
    ) -> bool:
        """
        Validate a submitted 6-digit OTP and raise OTPError with specific diagnostics on failure.
        Uses atomic conditional SQL updates for both consumption and attempt counting
        to prevent replay, lost updates, and concurrency race conditions.
        """
        normalized_email = (email or "").strip().lower()
        cleaned_code = (code or "").strip()
        normalized_purpose = (purpose or "").strip().upper()
        if normalized_purpose not in cls.VALID_PURPOSES:
            raise OTPError("OTP purpose is required and must be VERIFY or LOGIN.", status_code=400)

        verify_limit = int(os.getenv("OTP_VERIFY_RATE_LIMIT", str(DEFAULT_VERIFY_RATE_LIMIT)))
        _rate_limiter.check_and_record(
            f"verify:{normalized_email}", verify_limit, DEFAULT_VERIFY_WINDOW_SECONDS
        )
        if client_ip:
            _rate_limiter.check_and_record(
                f"verify_ip:{client_ip}", verify_limit * 3, DEFAULT_VERIFY_WINDOW_SECONDS
            )

        if len(cleaned_code) != 6 or not cleaned_code.isdigit():
            raise OTPError("Please enter a valid 6-digit numeric OTP.", status_code=400)

        now = datetime.utcnow()
        latest_record = (
            db.query(OTPRecord)
            .filter(
                OTPRecord.email == normalized_email,
                OTPRecord.purpose == normalized_purpose,
            )
            .order_by(OTPRecord.id.desc())
            .first()
        )
        if not latest_record:
            raise OTPError("No OTP found for this account. Please request a new code.", status_code=400)

        user = db.query(User).filter(User.email == normalized_email).first()
        if user and latest_record.user_id is not None and latest_record.user_id != user.id:
            raise OTPError("OTP does not belong to this account.", status_code=403)

        if latest_record.attempts >= MAX_OTP_ATTEMPTS:
            raise OTPError("Maximum verification attempts exceeded. Please request a new OTP.", status_code=429)

        if latest_record.is_used:
            raise OTPError("This OTP has already been used or invalidated. Please request a new code.", status_code=400)

        if latest_record.expires_at < now:
            raise OTPError("This OTP has expired. Please request a new code.", status_code=400)

        expected_hash = cls.hash_otp(normalized_email, latest_record.purpose, cleaned_code)
        if hmac.compare_digest(latest_record.code, expected_hash):
            try:
                updated = (
                    db.query(OTPRecord)
                    .filter(
                        OTPRecord.id == latest_record.id,
                        OTPRecord.is_used == False,
                        OTPRecord.attempts < MAX_OTP_ATTEMPTS,
                        OTPRecord.expires_at >= now,
                    )
                    .update({"is_used": True}, synchronize_session=False)
                )
                db.commit()
            except SQLAlchemyError as exc:
                db.rollback()
                raise OTPError("Could not verify OTP due to a database error. Please retry.", status_code=503) from exc

            if updated != 1:
                raise OTPError("This OTP has already been used or locked.", status_code=400)
            return True

        try:
            updated = (
                db.query(OTPRecord)
                .filter(
                    OTPRecord.id == latest_record.id,
                    OTPRecord.is_used == False,
                    OTPRecord.attempts < MAX_OTP_ATTEMPTS,
                )
                .update(
                    {
                        OTPRecord.attempts: OTPRecord.attempts + 1,
                        OTPRecord.is_used: case(
                            (OTPRecord.attempts + 1 >= MAX_OTP_ATTEMPTS, True),
                            else_=OTPRecord.is_used,
                        ),
                    },
                    synchronize_session=False,
                )
            )
            db.commit()
            refreshed = db.query(OTPRecord).filter(OTPRecord.id == latest_record.id).first()
        except SQLAlchemyError as exc:
            db.rollback()
            raise OTPError("Could not record verification attempt. Please retry.", status_code=503) from exc

        if updated != 1 or not refreshed:
            if refreshed and (refreshed.attempts or 0) >= MAX_OTP_ATTEMPTS:
                raise OTPError("Maximum verification attempts exceeded. Please request a new OTP.", status_code=429)
            raise OTPError("This OTP has already been used or invalidated. Please request a new code.", status_code=400)

        if (refreshed.attempts or 0) >= MAX_OTP_ATTEMPTS:
            raise OTPError("Maximum verification attempts exceeded. Please request a new OTP.", status_code=429)

        remaining = MAX_OTP_ATTEMPTS - refreshed.attempts
        raise OTPError(
            f"Incorrect verification code. {remaining} attempt(s) remaining.",
            status_code=400,
        )


def issue_otp(
    db: Session,
    email: str,
    purpose: str = "VERIFY",
    ttl_minutes: Optional[int] = None,
    client_ip: Optional[str] = None,
) -> int:
    return OTPService.issue_otp(
        db, email=email, purpose=purpose, ttl_minutes=ttl_minutes, client_ip=client_ip
    )


def verify_otp(
    db: Session,
    email: str,
    code: str,
    purpose: Optional[str] = None,
    client_ip: Optional[str] = None,
) -> bool:
    return OTPService.verify_otp(
        db, email=email, code=code, purpose=purpose, client_ip=client_ip
    )
