import asyncio
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.limiter import limiter
from app.db.mongo import db
from app.dependencies.auth import get_current_active_user
from app.models.subject import subject_data
from app.repositories import chat as chat_repo
from app.repositories import feedback as feedback_repo
from app.repositories import quiz as quiz_repo
from app.repositories import users as users_repo
from app.schemas.quiz import QuizGenerateRequest, QuizSubmitRequest
from app.services.analytics_service import track, QUIZ_COMPLETED
from app.services.session_manager import get_learning_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate")
@limiter.limit("10/minute")
async def generate_quiz_endpoint(
    request: Request,
    body: QuizGenerateRequest,
    current_user: dict = Depends(get_current_active_user),
):
    session = await get_learning_session(current_user)
    quiz = await session.generate_quiz(body.topic)
    if not quiz:
        raise HTTPException(status_code=500, detail="Failed to generate quiz")
    return {"quiz": quiz, "total_questions": len(quiz)}


@router.post("/submit")
@limiter.limit("10/minute")
async def submit_quiz(
    request: Request,
    body: QuizSubmitRequest,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])

    if body.total_questions <= 0:
        raise HTTPException(status_code=400, detail="total_questions must be > 0")
    if body.score < 0 or body.score > body.total_questions:
        raise HTTPException(
            status_code=400,
            detail=f"score must be between 0 and {body.total_questions}",
        )

    subject = current_user.get("current_subject", "general")
    s_data = subject_data(current_user, subject)
    logger.debug(
        "quiz_submit user_id=%s subject=%s weak_count=%d prof=%s",
        user_id, subject,
        len(s_data.get("weak_topics", [])),
        s_data.get("proficiency_score", 0),
    )

    await quiz_repo.insert_performance({
        "user_id": user_id,
        "topic": body.topic,
        "score": body.score,
        "total_questions": body.total_questions,
        "subject": subject,
        "created_at": datetime.utcnow(),
    })

    session = await get_learning_session(current_user)
    # Filter by subject so weak_topics are never mixed across domains
    all_perf = await quiz_repo.find_by_subject(user_id, subject, limit=200)
    quiz_data = [
        {"topic": p["topic"], "score": (p["score"] / p["total_questions"]) * 100}
        for p in all_perf if p.get("total_questions", 0) > 0
    ]

    weak_topics = session.update_weak_topics(quiz_data)

    correctness = body.score / body.total_questions if body.total_questions > 0 else 0

    # O(1) incremental proficiency — scoped per subject
    prev_cumulative = s_data.get("cumulative_score", 0.0)
    prev_attempts = s_data.get("total_attempts", 0)
    new_cumulative = prev_cumulative + correctness
    new_attempts = prev_attempts + 1
    proficiency_score = round((new_cumulative / new_attempts) * 100, 1)

    now = datetime.utcnow()
    update_op: dict = {
        "$set": {
            f"subjects.{subject}.weak_topics": weak_topics,
            f"subjects.{subject}.proficiency_score": proficiency_score,
            "last_active": now,
        },
        "$inc": {
            f"subjects.{subject}.engagement_score": 1,
            f"subjects.{subject}.cumulative_score": correctness,
            f"subjects.{subject}.total_attempts": 1,
        },
    }
    if correctness > 0.70:
        update_op["$addToSet"] = {f"subjects.{subject}.strong_topics": body.topic}

    try:
        await asyncio.gather(
            users_repo.apply_update(current_user["_id"], update_op),
            db.learning_events.insert_one({
                "user_id": user_id,
                "type": "quiz",
                "topic": body.topic,
                "subject": subject,
                "correctness": correctness,
                "response_time": None,
                "created_at": now,
            }),
        )
    except Exception as gather_err:
        logger.error(
            "quiz parallel write failed user_id=%s op=quiz_submit: %s",
            user_id, gather_err,
        )

    await track(db, QUIZ_COMPLETED, user_id=user_id, properties={
        "topic": body.topic,
        "subject": subject,
        "score_pct": round(correctness * 100, 1),
        "proficiency_after": proficiency_score,
    })

    # Score < 40% means the preceding explanation didn't land — record it
    if correctness < 0.4:
        last_explanation = await chat_repo.find_last_assistant_message(user_id)
        if last_explanation:
            await feedback_repo.insert_explanation_failure({
                "user_id": user_id,
                "topic": body.topic,
                "subject": subject,
                "explanation": last_explanation["message"][:500],
                "score_pct": round(correctness * 100, 1),
                "source": "quiz",
                "created_at": now,
            })
            logger.info(
                "explanation_failure recorded user=%s topic=%s score=%.0f%%",
                user_id, body.topic, correctness * 100,
            )

    return {"message": "Quiz submitted", "weak_topics": weak_topics}


@router.get("/weak_topics")
async def get_weak_topics(current_user: dict = Depends(get_current_active_user)):
    session = await get_learning_session(current_user)
    return {"weak_topics": session.weak_topics}


@router.get("/history")
async def get_quiz_history(
    subject: Optional[str] = None,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    active_subject = subject or current_user.get("current_subject", "general")
    performances = await quiz_repo.find_recent_by_subject(user_id, active_subject, limit=500)

    return {
        "history": [
            {
                "id": str(p["_id"]),
                "topic": p["topic"],
                "subject": p.get("subject", active_subject),
                "score": p["score"],
                "total_questions": p["total_questions"],
                "percentage": round((p["score"] / p["total_questions"]) * 100) if p.get("total_questions", 0) > 0 else 0,
                "created_at": p["created_at"].isoformat()
            }
            for p in performances
        ]
    }
