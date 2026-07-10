import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, status

from app.db.mongo import db
from app.dependencies.auth import get_current_active_user
from app.repositories import chat as chat_repo
from app.repositories import documents as documents_repo
from app.repositories import feedback as feedback_repo
from app.repositories import learning_events as learning_events_repo
from app.repositories import users as users_repo
from app.schemas.feedback import FeedbackRequest
from app.services.session_manager import get_learning_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["misc"])


@router.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    docs_count = await documents_repo.count_for_user(user_id)
    messages_count = await chat_repo.count_for_user(user_id)

    session = await get_learning_session(current_user)
    db_stats = session.get_db_stats()

    return {
        "documents_count": docs_count,
        "messages_count": messages_count,
        "chunks_count": db_stats.get("total_chunks", 0)
    }


@router.post("/heartbeat")
async def heartbeat(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    subject = current_user.get("current_subject", "general")
    now = datetime.utcnow()
    try:
        await asyncio.gather(
            users_repo.apply_update(
                current_user["_id"],
                {
                    "$set": {"last_active": now},
                    "$inc": {f"subjects.{subject}.engagement_score": 1},
                },
            ),
            db.learning_events.insert_one({
                "type": "heartbeat",
                "user_id": user_id,
                "subject": subject,
                "created_at": now,
            }),
        )
    except Exception as e:
        logger.error("heartbeat write failed user_id=%s: %s", user_id, e)
    logger.info("heartbeat user=%s subject=%s", user_id, subject)
    return {"status": "ok"}


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    subject = current_user.get("current_subject", "general")

    # Fetch the last AI response and the emotion at that time so failures
    # can be analyzed to find patterns in what doesn't work.
    last_ai_msg = await chat_repo.find_last_assistant_message(user_id)
    last_event = await learning_events_repo.find_last_chat_event(user_id)

    await feedback_repo.insert_feedback({
        "user_id": user_id,
        "message": body.message,
        "feedback_type": body.feedback_type,
        "last_ai_response": last_ai_msg["message"] if last_ai_msg else None,
        "topic": last_event["topic"] if last_event else None,
        "emotion_at_time": last_event["emotion"] if last_event else None,
        "subject": subject,
        "created_at": datetime.utcnow(),
    })

    # If thumbs down — store as a failed explanation for the nightly analyzer
    if body.feedback_type == "down" and last_ai_msg:
        await feedback_repo.insert_explanation_failure({
            "user_id": user_id,
            "topic": last_event["topic"] if last_event else None,
            "subject": subject,
            "explanation": last_ai_msg["message"][:500],
            "emotion_at_time": last_event["emotion"] if last_event else None,
            "created_at": datetime.utcnow(),
        })

    logger.info("Feedback '%s' recorded for user %s", body.feedback_type, user_id)
    return {"message": "Feedback recorded"}
