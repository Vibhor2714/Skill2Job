from unittest.mock import patch, MagicMock
import requests
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.interview_evaluator import CRITERIA_WEIGHTS


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_headers(client):
    res = client.get("/api/auth/demo/job_seeker")
    assert res.status_code == 200
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_criteria_weights_total_100_percent():
    assert abs(sum(CRITERIA_WEIGHTS.values()) - 1.0) < 1e-9


def test_empty_answers_rejected(client, auth_headers):
    # Empty list
    res_empty_list = client.post(
        "/api/ai-tools/mock-interview/evaluate",
        headers=auth_headers,
        json=[],
    )
    assert res_empty_list.status_code == 400

    # Empty / whitespace user_answer
    res_blank = client.post(
        "/api/ai-tools/mock-interview/evaluate",
        headers=auth_headers,
        json=[
            {
                "question_id": 1,
                "question": "What is the architectural difference between REST APIs and GraphQL?",
                "user_answer": "   ",
                "category": "Technical",
            }
        ],
    )
    assert res_blank.status_code == 400


def test_short_correct_vs_long_irrelevant_answer(client, auth_headers):
    q = "What is the architectural difference between REST APIs and GraphQL, and in what production scenario would you favor REST?"

    short_correct = (
        "REST is stateless using HTTP verbs, status codes, and URI caching. "
        "GraphQL uses a single endpoint schema to avoid over-fetching. "
        "Favor REST for cache-heavy CRUD APIs because CDN caching is simpler."
    )
    long_irrelevant = " ".join(
        ["In my daily routine I enjoy organizing folders, drinking coffee, reading novels, and attending morning standups with teammates to discuss office logistics."]
        * 12
    )

    res_short = client.post(
        "/api/ai-tools/mock-interview/evaluate",
        headers=auth_headers,
        json=[{"question_id": 1, "question": q, "user_answer": short_correct, "category": "Technical"}],
    )
    res_long = client.post(
        "/api/ai-tools/mock-interview/evaluate",
        headers=auth_headers,
        json=[{"question_id": 1, "question": q, "user_answer": long_irrelevant, "category": "Technical"}],
    )

    assert res_short.status_code == 200
    assert res_long.status_code == 200

    short_score = res_short.json()["overall_score"]
    long_score = res_long.json()["overall_score"]
    assert short_score > long_score + 30
    assert long_score < 35


def test_technically_incorrect_answer_penalized(client, auth_headers):
    q = "What is the architectural difference between REST APIs and GraphQL?"
    wrong_answer = (
        "REST is stateful and stores session state in the HTTP protocol, and HTTP GET is used to delete records. "
        "GraphQL only uses GET requests for mutations."
    )
    res = client.post(
        "/api/ai-tools/mock-interview/evaluate",
        headers=auth_headers,
        json=[{"question_id": 1, "question": q, "user_answer": wrong_answer, "category": "Technical"}],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["technical_score"] < 40
    assert any("stateless" in w.lower() or "get" in w.lower() for w in body["weak_areas"])


def test_behavioral_star_rubric(client, auth_headers):
    q = "Tell me about a challenging project deadline or unexpected production regression you encountered. How did you diagnose and resolve it?"
    star_answer = (
        "During a major release last quarter, our checkout service experienced a production outage under peak traffic. "
        "My task was to restore stability quickly. I investigated query logs for root cause analysis, identified a missing index, "
        "and implemented a hotfix with automated regression tests. As a result, we resolved the outage in 20 minutes and reduced latency by 45%."
    )
    res = client.post(
        "/api/ai-tools/mock-interview/evaluate",
        headers=auth_headers,
        json=[{"question_id": 3, "question": q, "user_answer": star_answer, "category": "Behavioral"}],
    )
    assert res.status_code == 200
    body = res.json()
    assert body["overall_score"] >= 75
    qe = body["question_evaluations"][0]
    assert "STAR" in qe["score_explanation"]
    assert qe["user_answer"] == star_answer


def test_llm_unavailable_invalid_response_and_timeout_fallbacks(client, auth_headers, monkeypatch):
    payload = [
        {
            "question_id": 1,
            "question": "How would you containerize a multi-tier web application using Docker and coordinate services with Docker Compose?",
            "user_answer": "Use a multi-stage Dockerfile for smaller images and docker-compose.yml with bridge networks and named volumes for database persistence.",
            "category": "Skill Gap",
        }
    ]

    # 1. Provider unavailable (no key)
    monkeypatch.delenv("INTERVIEW_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    res_unavail = client.post("/api/ai-tools/mock-interview/evaluate", headers=auth_headers, json=payload)
    assert res_unavail.status_code == 200
    assert res_unavail.json()["evaluation_mode"] == "deterministic_rubric_fallback"

    # 2. Invalid API response from provider
    monkeypatch.setenv("INTERVIEW_LLM_API_KEY", "test-key")
    bad_resp = MagicMock()
    bad_resp.status_code = 200
    bad_resp.json.return_value = {"choices": [{"message": {"content": "not-json"}}]}
    with patch("app.interview_evaluator.requests.post", return_value=bad_resp):
        res_invalid = client.post("/api/ai-tools/mock-interview/evaluate", headers=auth_headers, json=payload)
        assert res_invalid.status_code == 200
        assert res_invalid.json()["evaluation_mode"] == "deterministic_rubric_fallback"

    # 3. Timeout from provider
    with patch("app.interview_evaluator.requests.post", side_effect=requests.Timeout("timed out")):
        res_timeout = client.post("/api/ai-tools/mock-interview/evaluate", headers=auth_headers, json=payload)
        assert res_timeout.status_code == 200
        assert res_timeout.json()["evaluation_mode"] == "deterministic_rubric_fallback"
        assert "timed out" in res_timeout.json()["evaluation_note"].lower()


def test_multiple_questions_aggregated_correctly(client, auth_headers, monkeypatch):
    monkeypatch.delenv("INTERVIEW_LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    payload = [
        {
            "question_id": 1,
            "question": "What is the architectural difference between REST APIs and GraphQL?",
            "user_answer": "REST is stateless using HTTP verbs and status codes with easy CDN caching. GraphQL uses a typed schema at one endpoint to prevent over-fetching.",
            "category": "Technical",
        },
        {
            "question_id": 2,
            "question": "How would you design a caching layer with Redis for 100k requests/second?",
            "user_answer": "Use a CDN at the edge and Redis cluster with cache-aside reads, explicit TTL invalidation, and locks to prevent cache stampedes.",
            "category": "System Design",
        },
        {
            "question_id": 3,
            "question": "Tell me about a production regression you resolved.",
            "user_answer": "During a release, we saw high DB CPU. I was responsible for root cause analysis, added an index, and reduced query latency by 50%.",
            "category": "Behavioral",
        },
    ]
    res = client.post("/api/ai-tools/mock-interview/evaluate", headers=auth_headers, json=payload)
    assert res.status_code == 200
    body = res.json()
    assert len(body["question_evaluations"]) == 3
    expected_overall = int(round(sum(q["score"] for q in body["question_evaluations"]) / 3))
    assert body["overall_score"] == expected_overall
    assert "strength_areas" in body
    assert "weak_areas" in body
    assert "recommended_topics" in body
