import json
from datetime import datetime, timedelta
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.database import SessionLocal, User, Resume, Application, Job
from app.auth import create_access_token, hash_password


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_protected_endpoint_without_token(client):
    res = client.get("/api/auth/me")
    assert res.status_code == 401

    res_profile = client.get("/api/profile/job-seeker")
    assert res_profile.status_code == 401

    res_matches = client.get("/api/matches")
    assert res_matches.status_code == 401

    res_eval = client.post("/api/ai-tools/mock-interview/evaluate", json=[])
    assert res_eval.status_code == 401


def test_protected_endpoint_with_invalid_token(client):
    headers = {"Authorization": "Bearer invalid.jwt.token"}
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401


def test_protected_endpoint_with_expired_token(client):
    expired_token = create_access_token(
        {"sub": "alex.sharma@example.com", "role": "JOB_SEEKER", "id": 1},
        expires_delta=timedelta(minutes=-5),
    )
    headers = {"Authorization": f"Bearer {expired_token}"}
    res = client.get("/api/auth/me", headers=headers)
    assert res.status_code == 401


def test_protected_endpoint_with_valid_token_and_logout(client):
    demo_res = client.get("/api/auth/demo/job_seeker")
    assert demo_res.status_code == 200
    data = demo_res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "alex.sharma@example.com"

    # Valid token succeeds
    headers = {"Authorization": f"Bearer {data['access_token']}"}
    me_res = client.get("/api/auth/me", headers=headers)
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "alex.sharma@example.com"

    # After logout (no Authorization header), protected route returns 401
    logged_out_res = client.get("/api/auth/me")
    assert logged_out_res.status_code == 401


def test_deleted_user_with_old_token(client):
    db = SessionLocal()
    temp_email = "deleted_user_test@example.com"
    try:
        user = User(
            email=temp_email,
            hashed_password=hash_password("TestPass123!"),
            full_name="Temp User",
            role="JOB_SEEKER",
            is_email_verified=True,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        token = create_access_token({"sub": user.email, "role": user.role, "id": user.id})

        # Delete user from DB
        db.delete(user)
        db.commit()
    finally:
        db.close()

    res = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert res.status_code == 401


def test_valid_demo_logins(client):
    for role_path, expected_role in [
        ("job_seeker", "JOB_SEEKER"),
        ("hr", "HR"),
        ("admin", "ADMIN"),
    ]:
        res = client.get(f"/api/auth/demo/{role_path}")
        assert res.status_code == 200
        body = res.json()
        assert body["access_token"]
        assert body["user"]["role"] == expected_role


def test_user_cannot_access_another_users_resume_or_application(client):
    db = SessionLocal()
    owner_email = "resume_owner@example.com"
    other_email = "other_user@example.com"
    resume_id = None
    app_id = None
    try:
        for email, name in [(owner_email, "Owner User"), (other_email, "Other User")]:
            existing = db.query(User).filter(User.email == email).first()
            if existing:
                db.query(Resume).filter(Resume.user_id == existing.id).delete()
                db.query(Application).filter(Application.user_id == existing.id).delete()
                db.delete(existing)
        db.commit()

        owner = User(
            email=owner_email,
            hashed_password=hash_password("Pass123!"),
            full_name="Owner User",
            role="JOB_SEEKER",
            is_email_verified=True,
        )
        other = User(
            email=other_email,
            hashed_password=hash_password("Pass123!"),
            full_name="Other User",
            role="JOB_SEEKER",
            is_email_verified=True,
        )
        db.add_all([owner, other])
        db.commit()
        db.refresh(owner)
        db.refresh(other)

        resume = Resume(
            user_id=owner.id,
            filename="owner_resume.pdf",
            raw_text="Python FastAPI",
            parsed_json=json.dumps({"technical_skills": ["Python"]}),
            ats_score=88,
        )
        job = db.query(Job).first()
        application = Application(
            user_id=owner.id,
            job_id=job.id if job else 1,
            status="Applied",
        )
        db.add_all([resume, application])
        db.commit()
        db.refresh(resume)
        db.refresh(application)
        resume_id = resume.id
        app_id = application.id

        other_token = create_access_token({"sub": other.email, "role": other.role, "id": other.id})
        owner_token = create_access_token({"sub": owner.email, "role": owner.role, "id": owner.id})
    finally:
        db.close()

    # Other user cannot access owner's resume
    res_resume = client.get(
        f"/api/resume/{resume_id}",
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_resume.status_code == 403

    # Owner can access own resume
    res_owner_resume = client.get(
        f"/api/resume/{resume_id}",
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert res_owner_resume.status_code == 200

    # Other user cannot update owner's application status
    res_app = client.put(
        f"/api/applications/{app_id}/status",
        json={"status": "Interview"},
        headers={"Authorization": f"Bearer {other_token}"},
    )
    assert res_app.status_code == 403


def test_role_based_access_control(client):
    hr_res = client.get("/api/auth/demo/hr")
    hr_token = hr_res.json()["access_token"]
    hr_headers = {"Authorization": f"Bearer {hr_token}"}

    js_res = client.get("/api/auth/demo/job_seeker")
    js_token = js_res.json()["access_token"]
    js_headers = {"Authorization": f"Bearer {js_token}"}

    admin_res = client.get("/api/auth/demo/admin")
    admin_token = admin_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # HR accesses Admin endpoint -> 403
    assert client.get("/api/admin/stats", headers=hr_headers).status_code == 403
    # Job Seeker accesses Admin endpoint -> 403
    assert client.get("/api/admin/stats", headers=js_headers).status_code == 403
    # Admin accesses Admin endpoint -> 200
    assert client.get("/api/admin/stats", headers=admin_headers).status_code == 200

    # Job Seeker accesses HR endpoints -> 403
    assert client.get("/api/hr/dashboard-stats", headers=js_headers).status_code == 403
    assert client.get("/api/hr/candidates", headers=js_headers).status_code == 403
    # HR accesses HR endpoints -> 200
    assert client.get("/api/hr/dashboard-stats", headers=hr_headers).status_code == 200


def test_public_jobs_endpoint_accessible_without_leaking_demo_user(client):
    res = client.get("/api/jobs")
    assert res.status_code == 200
    data = res.json()
    assert "jobs" in data
    assert len(data["jobs"]) > 0
    # Unauthenticated guest has no matched_skills from Alex Sharma
    assert data["jobs"][0]["matched_skills"] == []
