import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_job_search_and_detail_regression(client):
    # Public job search
    res = client.get("/api/jobs?q=Developer")
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    assert len(jobs) > 0
    job_id = jobs[0]["id"]

    # Public job detail
    detail = client.get(f"/api/jobs/{job_id}")
    assert detail.status_code == 200
    assert detail.json()["id"] == job_id


def test_job_matching_github_skill_gap_and_analytics_regression(client):
    demo = client.get("/api/auth/demo/job_seeker")
    assert demo.status_code == 200
    headers = {"Authorization": f"Bearer {demo.json()['access_token']}"}

    # Matches
    matches = client.get("/api/matches", headers=headers)
    assert matches.status_code == 200
    assert "counts" in matches.json()

    # GitHub Insights
    gh = client.get("/api/github/insights", headers=headers)
    assert gh.status_code == 200
    assert "username" in gh.json()

    # Skill Gap
    sg = client.get("/api/skill-gap", headers=headers)
    assert sg.status_code == 200
    assert "you_have" in sg.json()

    # Career Insights
    ci = client.get("/api/analytics/career-insights", headers=headers)
    assert ci.status_code == 200
    assert "overview" in ci.json()


def test_application_tracking_regression(client):
    demo = client.get("/api/auth/demo/job_seeker")
    headers = {"Authorization": f"Bearer {demo.json()['access_token']}"}

    apps_res = client.get("/api/applications", headers=headers)
    assert apps_res.status_code == 200
    assert "columns" in apps_res.json()

    jobs_res = client.get("/api/jobs")
    job_id = jobs_res.json()["jobs"][0]["id"]

    apply_res = client.post(f"/api/applications/apply/{job_id}?status_name=Saved", headers=headers)
    assert apply_res.status_code == 200
    assert apply_res.json()["success"] is True


def test_hr_and_admin_dashboards_regression(client):
    hr_token = client.get("/api/auth/demo/hr").json()["access_token"]
    hr_headers = {"Authorization": f"Bearer {hr_token}"}

    assert client.get("/api/hr/dashboard-stats", headers=hr_headers).status_code == 200
    assert client.get("/api/hr/jobs", headers=hr_headers).status_code == 200
    assert client.get("/api/hr/candidates", headers=hr_headers).status_code == 200
    assert client.get("/api/hr/interviews", headers=hr_headers).status_code == 200

    admin_token = client.get("/api/auth/demo/admin").json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    assert client.get("/api/admin/stats", headers=admin_headers).status_code == 200
