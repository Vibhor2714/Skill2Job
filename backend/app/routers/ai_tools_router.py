from typing import Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db, Job, User
from app.schemas import CoverLetterRequest, MockInterviewRequest, MockInterviewAnswerSubmit
from app.auth import get_current_user
from app.ai_engine import generate_cover_letter, generate_mock_interview_questions
from app.interview_evaluator import evaluate_mock_interview
from app.routers.jobs_router import get_candidate_context, build_job_dict

router = APIRouter(prefix="/api/ai-tools", tags=["ai-tools"])

MAX_ANSWER_LENGTH = 10000

@router.post("/cover-letter")
def create_cover_letter(req: CoverLetterRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cand_ctx = get_candidate_context(current_user)

    target_job = None
    if req.job_id:
        target_job = db.query(Job).filter(Job.id == req.job_id).first()

    job_info = {
        "title": target_job.title if target_job else req.job_title,
        "company_name": target_job.company_name if target_job else req.company_name
    }

    letter = generate_cover_letter(cand_ctx, job_info, req.tone, req.length)
    return {
        "job_title": job_info["title"],
        "company_name": job_info["company_name"],
        "tone": req.tone,
        "length": req.length,
        "cover_letter": letter
    }

@router.post("/mock-interview/questions")
def get_mock_interview_questions(req: MockInterviewRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    cand_ctx = get_candidate_context(current_user)

    target_job = None
    if req.job_id:
        target_job = db.query(Job).filter(Job.id == req.job_id).first()

    job_title = target_job.title if target_job else req.job_title
    missing = ["Docker", "AWS", "Kubernetes"]

    questions = generate_mock_interview_questions(job_title, cand_ctx["skills"], missing)
    return {
        "job_title": job_title,
        "difficulty": req.difficulty,
        "interview_type": req.interview_type,
        "questions": questions
    }

@router.post("/mock-interview/evaluate")
def evaluate_interview_answers(answers: list[MockInterviewAnswerSubmit], current_user: User = Depends(get_current_user)):
    """
    Evaluates candidate mock interview answers using weighted criteria and STAR/technical rubrics.
    """
    if not answers:
        raise HTTPException(status_code=400, detail="Please submit at least one interview answer for evaluation.")

    formatted_answers = []
    for item in answers:
        cleaned_answer = (item.user_answer or "").strip()
        if not cleaned_answer or cleaned_answer.lower() == "no answer provided.":
            raise HTTPException(
                status_code=400,
                detail=f"Question {item.question_id} requires a non-empty answer before evaluation.",
            )
        if len(cleaned_answer) > MAX_ANSWER_LENGTH:
            raise HTTPException(
                status_code=400,
                detail=f"Answer for question {item.question_id} exceeds maximum length of {MAX_ANSWER_LENGTH} characters.",
            )
        formatted_answers.append({
            "question_id": item.question_id,
            "question": item.question,
            "user_answer": cleaned_answer,
            "category": item.category,
        })

    return evaluate_mock_interview(formatted_answers)
