import json
import os
import re
from typing import Any, Dict, List, Optional, Tuple
import requests

CRITERIA_WEIGHTS = {
    "technical_correctness": 0.30,
    "question_relevance": 0.25,
    "explanation_quality": 0.20,
    "problem_solving_approach": 0.15,
    "communication_clarity": 0.10,
}

STOP_WORDS = {
    "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
    "can", "may", "might", "that", "this", "these", "those", "it", "its", "you",
    "your", "i", "we", "they", "what", "how", "why", "when", "where", "which",
    "about", "into", "through", "during", "before", "after", "above", "below",
    "between", "under", "again", "further", "then", "once", "here", "there",
    "all", "any", "both", "each", "few", "more", "most", "other", "some", "such",
    "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very",
    "tell", "me", "explain", "describe", "would", "use", "using", "scenario",
}

TOPIC_RUBRICS: List[Dict[str, Any]] = [
    {
        "match_keywords": ["rest", "graphql", "api"],
        "expected_concepts": [
            ("stateless", ["stateless", "statelessness"]),
            ("http verbs / status codes", ["http", "get", "post", "put", "delete", "status code"]),
            ("caching", ["cache", "caching", "cdn", "etag"]),
            ("over-fetching / under-fetching", ["over-fetching", "overfetching", "under-fetching", "exact fields", "payload"]),
            ("schema / endpoints", ["schema", "endpoint", "resource", "query", "mutation"]),
        ],
        "misconceptions": [
            (r"\brest\b[^.]{0,40}\bstateful\b", "REST APIs are stateless by design, not stateful."),
            (r"\bgraphql\b[^.]{0,50}\b(?:only|always)\s+uses?\s+get\b", "GraphQL typically uses POST for queries/mutations rather than relying only on GET."),
            (r"\bhttp\s+get\b[^.]{0,40}\b(?:delete|mutate|modify)\b", "HTTP GET should be safe and idempotent, not used for destructive mutations."),
        ],
        "improved_sample": (
            "REST is stateless and models resources via standard HTTP verbs and status codes, making HTTP/CDN caching straightforward. "
            "GraphQL exposes a strongly typed schema at a single endpoint so clients fetch exact fields without over-fetching, though caching is more complex. "
            "I would favor REST for public, cache-heavy CRUD microservices with predictable payloads."
        ),
        "recommended_topics": [
            "HTTP caching semantics (ETag, Cache-Control) vs GraphQL normalized caches",
            "REST resource modeling and idempotency",
        ],
    },
    {
        "match_keywords": ["docker", "container", "compose", "containerize"],
        "expected_concepts": [
            ("dockerfile", ["dockerfile", "from", "copy", "run", "cmd", "entrypoint"]),
            ("multi-stage build", ["multi-stage", "multistage", "alpine", "slim", "image size"]),
            ("docker compose / services", ["compose", "docker-compose", "service", "services", "depends_on"]),
            ("volumes / persistence", ["volume", "volumes", "persist", "persistence"]),
            ("networking / env vars", ["network", "bridge", "port", "env", "environment"]),
        ],
        "misconceptions": [
            (r"\bdocker\b[^.]{0,50}\b(?:full\s+os|guest\s+os|hypervisor|virtual\s+machine)\b", "Docker containers share the host OS kernel rather than running a full guest OS like a VM."),
            (r"\bcontainer\b[^.]{0,40}\bpersists?\s+data\s+automatically\b", "Container filesystems are ephemeral; persistent data requires named volumes or bind mounts."),
        ],
        "improved_sample": (
            "Use a multi-stage Dockerfile: build dependencies and compile assets in a builder stage, then copy only production artifacts into a minimal runtime image. "
            "Coordinate the app, database, and cache in docker-compose.yml with an isolated bridge network, environment variables, healthchecks, and named volumes for database persistence."
        ),
        "recommended_topics": [
            "Docker multi-stage builds and layer caching",
            "Docker Compose networking, healthchecks, and volume persistence",
        ],
    },
    {
        "match_keywords": ["cache", "caching", "redis", "100k", "high-traffic", "scalability"],
        "expected_concepts": [
            ("redis / in-memory store", ["redis", "memcached", "in-memory"]),
            ("cache-aside / write-through", ["cache-aside", "write-through", "write-back", "read-through"]),
            ("invalidation / ttl", ["ttl", "invalidation", "invalidate", "eviction", "lru"]),
            ("cdn / edge caching", ["cdn", "edge", "cloudflare", "cloudfront"]),
            ("thundering herd / fallback", ["stampede", "thundering herd", "rate limit", "replication", "cluster"]),
        ],
        "misconceptions": [
            (r"\bredis\b[^.]{0,40}\brelational\s+sql\b", "Redis is an in-memory key-value data structure store, not a relational SQL database."),
            (r"\bcache\b[^.]{0,40}\bnever\s+needs?\s+invalidation\b", "Stale data must be managed via TTLs or explicit cache invalidation."),
        ],
        "improved_sample": (
            "Place a CDN at the edge for static/public responses and use a clustered Redis layer with cache-aside reads and explicit TTLs. "
            "Protect the database from cache stampedes using request coalescing or short-lived locks, and invalidate keys on writes."
        ),
        "recommended_topics": [
            "Cache-aside vs write-through vs write-behind patterns",
            "Cache stampede mitigation and TTL/eviction policies",
        ],
    },
]


def _is_behavioral_question(question: str, category: Optional[str]) -> bool:
    if category and category.strip().lower() == "behavioral":
        return True
    q_low = question.lower()
    return any(
        phrase in q_low
        for phrase in ["tell me about", "describe a time", "conflict", "deadline", "regression", "teamwork", "challenge"]
    )


def _tokenize_meaningful(text: str) -> set:
    tokens = set(re.findall(r"[a-z0-9+#\.\-]{2,}", text.lower()))
    return {t for t in tokens if t not in STOP_WORDS}


def _find_matching_rubric(question: str) -> Optional[Dict[str, Any]]:
    q_low = question.lower()
    for rubric in TOPIC_RUBRICS:
        if any(kw in q_low for kw in rubric["match_keywords"]):
            return rubric
    return None


def _evaluate_single_behavioral(question: str, answer: str, category: str) -> Dict[str, Any]:
    ans_low = answer.lower()

    star_checks = {
        "Situation": ["when", "during", "project", "production", "team", "sprint", "encountered", "deadline", "outage"],
        "Task": ["needed to", "responsible", "goal", "task", "had to", "required", "assigned"],
        "Action": ["i ", "investigated", "analyzed", "implemented", "fixed", "refactored", "communicated", "added", "mitigated", "rolled back"],
        "Result": ["resolved", "reduced", "improved", "prevented", "delivered", "eliminated", "post-mortem", "%", "minutes", "hours"],
    }

    matched_star = [part for part, markers in star_checks.items() if any(m in ans_low for m in markers)]
    missing_star = [part for part in star_checks if part not in matched_star]

    q_tokens = _tokenize_meaningful(question)
    a_tokens = _tokenize_meaningful(answer)
    overlap = len(q_tokens & a_tokens)

    # Relevance check: behavioral answer must relate to work/projects/problem resolution
    work_context_markers = ["project", "team", "bug", "issue", "deadline", "production", "code", "system", "user", "client", "fix", "task"]
    has_work_context = any(m in ans_low for m in work_context_markers) or overlap >= 2

    if not has_work_context:
        relevance = 18
        tech_correctness = 20
        problem_solving = 20
        explanation = 25
        comm = 35
    else:
        relevance = min(95, 45 + len(matched_star) * 12 + min(15, overlap * 4))
        tech_correctness = min(92, 40 + len(matched_star) * 13)
        problem_solving = min(95, 38 + (20 if "Action" in matched_star else 0) + (20 if "Result" in matched_star else 0) + (15 if any(w in ans_low for w in ["root cause", "rca", "logs", "metrics", "post-mortem", "test"]) else 0))
        explanation = min(92, 40 + len(matched_star) * 12)
        comm = min(94, 45 + len(matched_star) * 11)

    weighted_score = int(round(
        tech_correctness * CRITERIA_WEIGHTS["technical_correctness"]
        + relevance * CRITERIA_WEIGHTS["question_relevance"]
        + explanation * CRITERIA_WEIGHTS["explanation_quality"]
        + problem_solving * CRITERIA_WEIGHTS["problem_solving_approach"]
        + comm * CRITERIA_WEIGHTS["communication_clarity"]
    ))

    strengths = [f"Clear STAR '{s}' framing in your response." for s in matched_star]
    if not strengths:
        strengths = ["Attempted to provide a narrative response."]

    weak_areas = [f"Missing or weak STAR '{m}' component." for m in missing_star]
    if not has_work_context:
        weak_areas.insert(0, "Response does not clearly address a workplace, project, or engineering scenario.")

    return {
        "question": question,
        "category": category or "Behavioral",
        "user_answer": answer,
        "score": weighted_score,
        "criteria_scores": {
            "technical_correctness": tech_correctness,
            "question_relevance": relevance,
            "explanation_quality": explanation,
            "problem_solving_approach": problem_solving,
            "communication_clarity": comm,
        },
        "strengths": strengths,
        "missing_concepts": [f"STAR: {m}" for m in missing_star],
        "weak_areas": weak_areas,
        "score_explanation": (
            f"Evaluated using the STAR behavioral rubric: covered {len(matched_star)}/4 STAR elements "
            f"({', '.join(matched_star) if matched_star else 'none'})."
        ),
        "suggested_improved_answer": (
            "Structure your answer with STAR: (1) Situation: state the production or deadline context; "
            "(2) Task: clarify your ownership; (3) Action: detail the root-cause analysis and concrete fix; "
            "(4) Result: quantify the outcome and post-mortem prevention steps."
        ),
        "recommended_topics": [
            "STAR Behavioral Interview Framework",
            "Incident Root Cause Analysis & Post-Mortem Communication",
        ],
    }


def _evaluate_single_technical(question: str, answer: str, category: str) -> Dict[str, Any]:
    ans_low = answer.lower()
    rubric = _find_matching_rubric(question)

    q_tokens = _tokenize_meaningful(question)
    a_tokens = _tokenize_meaningful(answer)
    overlap_tokens = q_tokens & a_tokens

    matched_concepts: List[str] = []
    missing_concepts: List[str] = []
    misconceptions_found: List[str] = []

    if rubric:
        for label, synonyms in rubric["expected_concepts"]:
            if any(syn in ans_low for syn in synonyms):
                matched_concepts.append(label)
            else:
                missing_concepts.append(label)
        for pattern, msg in rubric["misconceptions"]:
            if re.search(pattern, ans_low):
                misconceptions_found.append(msg)
    else:
        # Generic technical evaluation based on question concepts & reasoning markers
        for tok in sorted(q_tokens)[:5]:
            if tok in a_tokens:
                matched_concepts.append(tok)
            else:
                missing_concepts.append(tok)

    # Reasoning, trade-offs, and practical implementation markers (NOT raw length)
    reasoning_markers = ["because", "therefore", "trade-off", "tradeoff", "whereas", "however", "latency", "scale", "edge case", "bottleneck", "avoid", "instead"]
    reasoning_hits = sum(1 for m in reasoning_markers if m in ans_low)

    # Check relevance strictly: must share question concepts or expected rubric concepts
    total_expected = max(1, len(matched_concepts) + len(missing_concepts))
    concept_ratio = len(matched_concepts) / total_expected
    is_irrelevant = (len(overlap_tokens) == 0 and len(matched_concepts) == 0)

    if is_irrelevant:
        relevance = 15
        tech_correctness = 15
        explanation = 20
        problem_solving = 15
        comm = 35
    else:
        relevance = min(96, int(round(35 + concept_ratio * 45 + min(16, len(overlap_tokens) * 5))))
        tech_base = 35 + concept_ratio * 55
        if misconceptions_found:
            tech_base = max(10, tech_base - 35 * len(misconceptions_found))
        tech_correctness = min(96, int(round(tech_base)))

        explanation = min(94, int(round(35 + concept_ratio * 40 + min(18, reasoning_hits * 6))))
        problem_solving = min(95, int(round(30 + concept_ratio * 40 + min(24, reasoning_hits * 8))))

        sentences = [s.strip() for s in re.split(r"[.!?]+", answer) if s.strip()]
        comm = min(92, 50 + min(25, len(sentences) * 8) + (15 if not misconceptions_found else 0))

    weighted_score = int(round(
        tech_correctness * CRITERIA_WEIGHTS["technical_correctness"]
        + relevance * CRITERIA_WEIGHTS["question_relevance"]
        + explanation * CRITERIA_WEIGHTS["explanation_quality"]
        + problem_solving * CRITERIA_WEIGHTS["problem_solving_approach"]
        + comm * CRITERIA_WEIGHTS["communication_clarity"]
    ))

    strengths = [f"Accurately addressed '{c}'." for c in matched_concepts]
    if reasoning_hits > 0 and not is_irrelevant:
        strengths.append("Included architectural reasoning or trade-off analysis.")
    if not strengths:
        strengths = ["Submitted a response, though key question concepts were not covered."]

    weak_areas = list(misconceptions_found)
    if is_irrelevant:
        weak_areas.append("Answer does not address the technical topic asked in the question.")
    if missing_concepts:
        weak_areas.append(f"Omitted key concepts: {', '.join(missing_concepts[:3])}.")

    improved = rubric["improved_sample"] if rubric else (
        f"Directly address {', '.join(missing_concepts[:3]) if missing_concepts else 'core concepts'}, "
        "explain the architectural trade-offs, and include concrete implementation details or edge cases."
    )
    rec_topics = rubric["recommended_topics"] if rubric else [
        f"Review fundamentals related to: {', '.join(sorted(q_tokens)[:3]) or 'core system design'}"
    ]

    return {
        "question": question,
        "category": category or "Technical",
        "user_answer": answer,
        "score": weighted_score,
        "criteria_scores": {
            "technical_correctness": tech_correctness,
            "question_relevance": relevance,
            "explanation_quality": explanation,
            "problem_solving_approach": problem_solving,
            "communication_clarity": comm,
        },
        "strengths": strengths,
        "missing_concepts": missing_concepts,
        "weak_areas": weak_areas if weak_areas else ["No major technical gaps detected."],
        "score_explanation": (
            f"Covered {len(matched_concepts)}/{total_expected} expected concepts"
            + (f" with {len(misconceptions_found)} technical misconception(s) penalized" if misconceptions_found else "")
            + ("." if not is_irrelevant else "; response was off-topic relative to the question.")
        ),
        "suggested_improved_answer": improved,
        "recommended_topics": rec_topics,
    }


def _evaluate_with_llm(answers: List[Dict[str, Any]]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Attempt structured evaluation using an OpenAI-compatible LLM endpoint configured via backend env vars.
    Returns (result_dict, None) on success, or (None, reason_string) on unavailability/failure.
    """
    api_key = os.getenv("INTERVIEW_LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None, "No LLM provider API key configured; using deterministic rubric evaluator."

    base_url = os.getenv("INTERVIEW_LLM_BASE_URL", "https://api.openai.com/v1/chat/completions")
    model = os.getenv("INTERVIEW_LLM_MODEL", "gpt-4o-mini")
    try:
        timeout_sec = float(os.getenv("INTERVIEW_LLM_TIMEOUT_SECONDS", "15"))
    except ValueError:
        timeout_sec = 15.0

    system_prompt = (
        "You are a strict technical & behavioral interview evaluator. "
        "Evaluate each answer using weights: technical_correctness (30%), question_relevance (25%), "
        "explanation_quality (20%), problem_solving_approach (15%), communication_clarity (10%). "
        "Do NOT reward answer length by itself. Penalize irrelevant or factually wrong answers. "
        "For behavioral questions use STAR. Return ONLY valid JSON with keys: "
        "'summary', 'question_evaluations' (list of objects with question_id, question, category, score, "
        "criteria_scores, strengths, missing_concepts, weak_areas, score_explanation, suggested_improved_answer, recommended_topics)."
    )

    payload = {
        "model": model,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": json.dumps({"answers": answers})},
        ],
    }

    try:
        resp = requests.post(
            base_url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=payload,
            timeout=timeout_sec,
        )
        if resp.status_code != 200:
            return None, f"LLM provider returned HTTP {resp.status_code}; using deterministic rubric fallback."
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        q_evals = parsed.get("question_evaluations")
        if not isinstance(q_evals, list) or len(q_evals) != len(answers):
            return None, "LLM provider returned an incomplete evaluation structure; using deterministic rubric fallback."

        # Attach user_answer and validate numeric fields
        for idx, qe in enumerate(q_evals):
            qe["question_id"] = answers[idx]["question_id"]
            qe["user_answer"] = answers[idx]["user_answer"]
            cs = qe.get("criteria_scores", {})
            for k in CRITERIA_WEIGHTS:
                val = int(cs.get(k, qe.get("score", 50)))
                cs[k] = max(0, min(100, val))
            qe["criteria_scores"] = cs
            qe["score"] = int(round(sum(cs[k] * w for k, w in CRITERIA_WEIGHTS.items())))

        return parsed, None
    except requests.Timeout:
        return None, "LLM evaluation request timed out; using deterministic rubric fallback."
    except (requests.RequestException, ValueError, KeyError, TypeError):
        return None, "LLM provider response was invalid or unreachable; using deterministic rubric fallback."


def evaluate_mock_interview(answers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Evaluate submitted interview answers. Uses configured LLM provider if available,
    falling back transparently to the deterministic rubric evaluator.
    """
    llm_result, fallback_reason = _evaluate_with_llm(answers)

    if llm_result is not None:
        q_evals = llm_result["question_evaluations"]
        eval_mode = "llm"
        eval_note = "Evaluated by configured LLM provider using weighted interview criteria."
        summary = llm_result.get("summary") or "Interview evaluation completed by LLM."
    else:
        eval_mode = "deterministic_rubric_fallback"
        eval_note = fallback_reason or "Evaluated using deterministic rubric-based fallback."
        q_evals = []
        for item in answers:
            q_text = item["question"]
            a_text = item["user_answer"]
            cat = item.get("category") or ("Behavioral" if _is_behavioral_question(q_text, None) else "Technical")
            if _is_behavioral_question(q_text, cat):
                ev = _evaluate_single_behavioral(q_text, a_text, cat)
            else:
                ev = _evaluate_single_technical(q_text, a_text, cat)
            ev["question_id"] = item["question_id"]
            q_evals.append(ev)
        summary = (
            f"Evaluated {len(q_evals)} answer(s) using the weighted rubric "
            "(Technical 30%, Relevance 25%, Explanation 20%, Problem Solving 15%, Communication 10%)."
        )

    n = max(1, len(q_evals))
    overall_score = int(round(sum(q["score"] for q in q_evals) / n))
    technical_score = int(round(sum(q["criteria_scores"]["technical_correctness"] for q in q_evals) / n))
    communication_score = int(round(sum(q["criteria_scores"]["communication_clarity"] for q in q_evals) / n))
    problem_solving_score = int(round(sum(q["criteria_scores"]["problem_solving_approach"] for q in q_evals) / n))

    strength_areas: List[str] = []
    weak_areas: List[str] = []
    recommended_topics: List[str] = []

    for q in q_evals:
        for s in q.get("strengths", []):
            if s not in strength_areas:
                strength_areas.append(s)
        for w in q.get("weak_areas", []):
            if w not in weak_areas:
                weak_areas.append(w)
        for r in q.get("recommended_topics", []):
            if r not in recommended_topics:
                recommended_topics.append(r)

    return {
        "evaluation_mode": eval_mode,
        "evaluation_note": eval_note,
        "criteria_weights": CRITERIA_WEIGHTS,
        "overall_score": overall_score,
        "technical_score": technical_score,
        "communication_score": communication_score,
        "problem_solving_score": problem_solving_score,
        "summary": summary,
        "strength_areas": strength_areas[:6],
        "weak_areas": weak_areas[:6],
        "recommended_topics": recommended_topics[:6],
        "question_evaluations": q_evals,
    }
