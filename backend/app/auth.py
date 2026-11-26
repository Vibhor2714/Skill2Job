import hashlib
import hmac
import os
import re
import jwt
from datetime import datetime, timedelta
from typing import Optional
from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.database import get_db, User

_DEFAULT_DEV_SECRET = "skills2job_ultra_secure_secret_key_change_in_production"
SECRET_KEY = os.getenv("JWT_SECRET_KEY", _DEFAULT_DEV_SECRET)
if os.getenv("APP_ENV", "development").lower() == "production" and (
    not SECRET_KEY or SECRET_KEY == _DEFAULT_DEV_SECRET
):
    raise RuntimeError(
        "Missing required production secret: set JWT_SECRET_KEY to a strong random value when APP_ENV=production."
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7 days

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

# Argon2id configuration (OWASP-aligned parameters suitable for local/cloud deployment)
_password_hasher = PasswordHasher(
    time_cost=3,
    memory_cost=65536,  # 64 MiB
    parallelism=4,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

_LEGACY_SALT = "skills2job_salt_"
_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")


def is_legacy_sha256_hash(hashed_password: str) -> bool:
    """Return True if the stored hash is a legacy 64-char hex SHA-256 digest."""
    return bool(hashed_password and _HEX64_RE.match(hashed_password))


def hash_password(password: str) -> str:
    """Hash a password using Argon2id."""
    return _password_hasher.hash(password)


def _verify_legacy_sha256(plain_password: str, hashed_password: str) -> bool:
    legacy_digest = hashlib.sha256((_LEGACY_SALT + plain_password).encode("utf-8")).hexdigest()
    return hmac.compare_digest(legacy_digest, hashed_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against an Argon2id hash or a legacy SHA-256 hash."""
    if not plain_password or not hashed_password:
        return False

    if hashed_password.startswith("$argon2"):
        try:
            return _password_hasher.verify(hashed_password, plain_password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False

    if is_legacy_sha256_hash(hashed_password):
        return _verify_legacy_sha256(plain_password, hashed_password)

    return False


def needs_password_rehash(hashed_password: str) -> bool:
    """Return True if a legacy SHA-256 hash or outdated Argon2 hash should be upgraded."""
    if not hashed_password:
        return False
    if is_legacy_sha256_hash(hashed_password):
        return True
    if hashed_password.startswith("$argon2"):
        try:
            return _password_hasher.check_needs_rehash(hashed_password)
        except InvalidHashError:
            return False
    return False


def validate_password_strength(password: str) -> None:
    """Enforce sensible password validation rules during registration."""
    if not password or not password.strip():
        raise HTTPException(status_code=400, detail="Password is required.")
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters long.")
    if len(password) > 128:
        raise HTTPException(status_code=400, detail="Password must not exceed 128 characters.")
    if not re.search(r"[A-Za-z]", password) or not re.search(r"[0-9]", password):
        raise HTTPException(
            status_code=400,
            detail="Password must include at least one letter and one number.",
        )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def _decode_token_and_get_user(token: str, db: Session) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")
        if not email:
            raise credentials_exception
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise credentials_exception

    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if not user.is_email_verified:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is not verified. Please complete OTP verification.",
        )
    return user


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> User:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return _decode_token_and_get_user(token, db)


def get_optional_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> Optional[User]:
    if not token:
        return None
    return _decode_token_and_get_user(token, db)


def require_role(*allowed_roles: str):
    def _role_dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this resource",
            )
        return current_user
    return _role_dependency
