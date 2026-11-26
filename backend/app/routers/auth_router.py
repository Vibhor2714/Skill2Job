from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.database import get_db, User, JobSeekerProfile, HRProfile, OTPRecord
from app.schemas import UserRegister, UserLogin, OTPVerify, OTPRequest, RoleSelect, TokenResponse
from app.auth import (
    hash_password,
    verify_password,
    needs_password_rehash,
    validate_password_strength,
    create_access_token,
    get_current_user,
)
from app.otp_service import issue_otp, verify_otp, OTPError

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register")
def register(req: UserRegister, request: Request, db: Session = Depends(get_db)):
    validate_password_strength(req.password)
    if req.confirm_password is not None and req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match.")

    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists.")

    new_user = User(
        email=req.email,
        hashed_password=hash_password(req.password),
        full_name=req.full_name,
        phone=req.phone,
        role="JOB_SEEKER",
        verification_code=None,
        is_email_verified=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # Create default job seeker profile
    profile = JobSeekerProfile(user_id=new_user.id)
    db.add(profile)
    db.commit()

    client_ip = request.client.host if request.client else None
    try:
        issue_otp(db, new_user.email, purpose="VERIFY", client_ip=client_ip)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    return {
        "message": "Registration successful! Check the backend terminal for your 6-digit verification code.",
        "requires_verification": True,
        "user": {
            "id": new_user.id,
            "email": new_user.email,
            "full_name": new_user.full_name,
            "role": new_user.role,
            "is_email_verified": new_user.is_email_verified
        }
    }

@router.post("/login")
def login(req: UserLogin, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user or not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not user.is_email_verified:
        raise HTTPException(
            status_code=403,
            detail="Account is not verified. Please complete OTP verification before logging in.",
        )

    # Upgrade legacy SHA-256 (or outdated Argon2) hash only after successful verification
    if needs_password_rehash(user.hashed_password):
        user.hashed_password = hash_password(req.password)
        db.commit()

    token = create_access_token({"sub": user.email, "role": user.role, "id": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "role": user.role,
            "avatar_url": user.avatar_url,
            "is_email_verified": user.is_email_verified
        }
    }

@router.post("/verify-email")
def verify_email(req: OTPVerify, request: Request, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if user.is_email_verified:
        raise HTTPException(status_code=400, detail="Account is already verified.")

    client_ip = request.client.host if request.client else None
    try:
        verify_otp(db, req.email, req.code, purpose="VERIFY", client_ip=client_ip)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    user.is_email_verified = True
    user.verification_code = None
    db.commit()
    return {
        "success": True,
        "message": "Account verified successfully! Please log in to continue.",
    }

@router.post("/otp/request")
def request_otp(req: OTPRequest, request: Request, db: Session = Depends(get_db)):
    """Generate a real 6-digit numeric OTP with 5-minute expiry and print to backend terminal."""
    purpose = (req.purpose or "LOGIN").strip().upper()
    if purpose not in {"VERIFY", "LOGIN"}:
        raise HTTPException(status_code=400, detail="Invalid OTP purpose. Must be VERIFY or LOGIN.")

    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    if purpose == "VERIFY" and user.is_email_verified:
        raise HTTPException(status_code=400, detail="Account is already verified.")
    if purpose == "LOGIN" and not user.is_email_verified:
        raise HTTPException(
            status_code=403,
            detail="Account is not verified. Please complete OTP verification before logging in.",
        )

    client_ip = request.client.host if request.client else None
    try:
        ttl_minutes = issue_otp(db, req.email, purpose=purpose, client_ip=client_ip)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return {
        "success": True,
        "message": f"A 6-digit verification code has been generated for {req.email}. Check the backend terminal.",
        "expires_in_minutes": ttl_minutes,
    }

@router.post("/otp/resend")
def resend_otp(req: OTPRequest, request: Request, db: Session = Depends(get_db)):
    """Resend OTP endpoint enforcing the 60-second cooldown and rate limits."""
    return request_otp(req, request, db)

@router.get("/verification-status")
def get_verification_status(current_user: User = Depends(get_current_user)):
    return {
        "email": current_user.email,
        "is_email_verified": current_user.is_email_verified,
        "is_phone_verified": current_user.is_phone_verified,
    }

@router.post("/otp/verify")
def verify_otp_login(req: OTPVerify, request: Request, db: Session = Depends(get_db)):
    """Verify LOGIN OTP and authenticate an existing verified user."""
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found. Please register first.")
    if not user.is_email_verified:
        raise HTTPException(
            status_code=403,
            detail="Account is not verified. Please complete OTP verification before logging in.",
        )

    client_ip = request.client.host if request.client else None
    try:
        verify_otp(db, req.email, req.code, purpose="LOGIN", client_ip=client_ip)
    except OTPError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)

    token = create_access_token({"sub": user.email, "role": user.role, "id": user.id})
    return {
        "success": True,
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "role": user.role,
            "avatar_url": user.avatar_url,
            "is_email_verified": user.is_email_verified
        }
    }

@router.post("/select-role")
def select_role(req: RoleSelect, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == req.email).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")

    user.role = req.role
    if req.role == "HR" and not user.hr_profile:
        hr_p = HRProfile(user_id=user.id, recruiter_name=user.full_name)
        db.add(hr_p)
    elif req.role == "JOB_SEEKER" and not user.job_seeker_profile:
        js_p = JobSeekerProfile(user_id=user.id)
        db.add(js_p)

    db.commit()
    token = create_access_token({"sub": user.email, "role": user.role, "id": user.id})
    return {"success": True, "role": user.role, "access_token": token}

@router.get("/demo/{role}")
def login_as_demo(role: str, db: Session = Depends(get_db)):
    """Instant one-click demo login for examiners and recruiters."""
    if role.lower() in ["hr", "recruiter"]:
        user = db.query(User).filter(User.email == "sarah.jenkins@techcorp.example.com").first()
    elif role.lower() in ["admin"]:
        user = db.query(User).filter(User.email == "admin@skills2job.example.com").first()
    else:
        user = db.query(User).filter(User.email == "alex.sharma@example.com").first()

    if not user:
        raise HTTPException(status_code=404, detail="Demo account not found in database.")

    token = create_access_token({"sub": user.email, "role": user.role, "id": user.id})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": user.id,
            "email": user.email,
            "full_name": user.full_name,
            "phone": user.phone,
            "role": user.role,
            "avatar_url": user.avatar_url,
            "is_email_verified": user.is_email_verified
        }
    }

@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name,
        "phone": current_user.phone,
        "role": current_user.role,
        "avatar_url": current_user.avatar_url,
        "is_email_verified": current_user.is_email_verified,
        "is_phone_verified": current_user.is_phone_verified
    }
