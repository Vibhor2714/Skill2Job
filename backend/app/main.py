import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def _load_env_files() -> None:
    """Load .env from backend/ or project root without overriding exported shell variables."""
    backend_dir = Path(__file__).resolve().parent.parent
    for env_path in (backend_dir.parent / ".env", backend_dir / ".env"):
        if not env_path.is_file():
            continue
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = val


_load_env_files()

from app.database import engine, Base, SessionLocal, ensure_otp_schema
from app.otp_service import validate_otp_configuration
from app.seed_data import seed_database

validate_otp_configuration()
from app.routers import (
    auth_router, profile_router, jobs_router, match_router,
    resume_router, github_router, skill_gap_router,
    application_router, ai_tools_router, hr_router,
    analytics_router, admin_router
)

# Initialize database schema and apply non-destructive column migrations
Base.metadata.create_all(bind=engine)
ensure_otp_schema(engine)

app = FastAPI(
    title="Skills2Job API",
    description="AI-Powered Career Matchmaking and Recruitment Platform",
    version="1.0.0"
)

_default_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_env_origins = os.getenv("CORS_ORIGINS", "").strip()
_cors_origins = [o.strip() for o in _env_origins.split(",") if o.strip()] if _env_origins else _default_origins

# Enable CORS for Next.js frontend on both Windows and macOS
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def on_startup():
    db = SessionLocal()
    try:
        seed_database(db)
    finally:
        db.close()

# Mount all routers
app.include_router(auth_router.router)
app.include_router(profile_router.router)
app.include_router(jobs_router.router)
app.include_router(match_router.router)
app.include_router(resume_router.router)
app.include_router(github_router.router)
app.include_router(skill_gap_router.router)
app.include_router(application_router.router)
app.include_router(ai_tools_router.router)
app.include_router(hr_router.router)
app.include_router(analytics_router.router)
app.include_router(admin_router.router)

@app.get("/api/health")
def health_check():
    return {
        "status": "healthy",
        "app": "Skills2Job API",
        "version": "1.0.0",
        "ai_engine": "Active (5-Factor Explainable Matcher + Vector Sim)"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
