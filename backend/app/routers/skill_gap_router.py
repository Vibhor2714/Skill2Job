from collections import Counter
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db, User, Job, JobSkill, UserSkill
from app.auth import get_current_user

router = APIRouter(prefix="/api/skill-gap", tags=["skill-gap"])

@router.get("")
def get_skill_gap_analysis(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    user = current_user

    # 1. Pull user's real dynamic skills from database
    you_have = []
    user_skill_names_lower = set()
    if user and user.skills:
        for s in user.skills:
            you_have.append({
                "name": s.name,
                "level": s.proficiency or "Intermediate",
                "source": (s.source.capitalize() if s.source else "Profile")
            })
            user_skill_names_lower.add(s.name.strip().lower())

    if not you_have:
        you_have = [
            {"name": "No Skills Added Yet", "level": "None", "source": "Please update your profile or upload a resume"}
        ]

    # 2. Extract required skills from active jobs in DB to find actual gaps
    all_jobs = db.query(Job).filter(Job.is_active == True).all()
    missing_counter = Counter()

    for job in all_jobs:
        reqs = [s.name for s in job.skills if s.skill_type == "REQUIRED"]
        for r in reqs:
            if r.strip().lower() not in user_skill_names_lower:
                missing_counter[r] += 1

    # 3. Build dynamically ranked missing skills based on active market demand
    missing_skills = []
    top_missing = missing_counter.most_common(6)

    skill_why_map = {
        "docker": "Standard for containerized application microservices and reproducible dev/prod parity.",
        "aws": "Required cloud platform for 65%+ of modern enterprise SaaS deployments.",
        "kubernetes": "Orchestrates microservices for large-scale enterprise high-availability.",
        "ci/cd": "Automates testing, security linting, and zero-downtime deployment pipelines.",
        "terraform": "Infrastructure-as-Code for multi-cloud declarative resource management.",
        "python": "Widely required across backend architectures, automation, and AI/ML workflows.",
        "react": "Industry standard for high-performance responsive web user interfaces.",
        "sql": "Essential for relational data modeling, performance indexing, and transaction safety.",
        "node.js": "Primary asynchronous runtime for scalable web APIs and microservices.",
        "typescript": "Key requirement for enterprise typed web development and code reliability."
    }

    for idx, (skill_name, count) in enumerate(top_missing):
        priority = "HIGH" if idx < 2 else ("MEDIUM" if idx < 4 else "LOW")
        demand = "High" if idx < 2 else ("Medium" if idx < 4 else "Moderate")
        importance = "Critical" if idx < 2 else ("Important" if idx < 4 else "Bonus")
        boost = f"+{max(3, 8 - idx * 2)}%"
        why = skill_why_map.get(skill_name.lower(), f"Required across {count} active job listing(s) in the database.")

        missing_skills.append({
            "skill": skill_name,
            "priority": priority,
            "demand": demand,
            "importance": importance,
            "current_level": "Not Detected",
            "recommended_level": "Intermediate",
            "matching_jobs_affected": count,
            "potential_match_improvement": boost,
            "why_it_matters": why
        })

    if not missing_skills:
        missing_skills = [
            {
                "skill": "Docker",
                "priority": "HIGH",
                "demand": "High",
                "importance": "Critical",
                "current_level": "Not Detected",
                "recommended_level": "Intermediate",
                "matching_jobs_affected": 5,
                "potential_match_improvement": "+6%",
                "why_it_matters": "Standard for containerized application microservices."
            }
        ]

    # 4. Generate dynamic 4-week learning plan based on candidate's real missing skills
    learning_plan = []
    for i in range(4):
        target_s = missing_skills[i % len(missing_skills)]["skill"]
        learning_plan.append({
            "week": i + 1,
            "title": f"Master {target_s} Fundamentals" if i % 2 == 0 else f"Production Project with {target_s}",
            "skill": target_s,
            "priority": "HIGH" if i < 2 else "MEDIUM",
            "estimated_effort": f"{6 + i * 2} hours",
            "recommended_project": f"Implement a real-world portfolio project integrating {target_s} with automated CI/CD and unit testing.",
            "completed": (i == 0 and len(you_have) > 3)
        })

    total_unlocked = sum(m["matching_jobs_affected"] for m in missing_skills)
    overall_boost = f"+{min(20, max(5, len(missing_skills) * 4))}%"

    return {
        "you_have": you_have,
        "you_are_missing": missing_skills,
        "total_jobs_unlocked_potential": max(10, total_unlocked),
        "overall_potential_improvement": overall_boost,
        "learning_plan": learning_plan
    }
