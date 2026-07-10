from datetime import datetime, timedelta

from fastapi import APIRouter, Depends

from app.dependencies.auth import get_current_active_user
from app.models.subject import subject_data
from app.repositories import learning_events as learning_events_repo
from app.repositories import quiz as quiz_repo

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/overview")
async def analytics_overview(
    subject: str = "general",
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    s_data = subject_data(current_user, subject)

    proficiency_score = round(s_data.get("proficiency_score", 0))
    engagement_score = int(s_data.get("engagement_score", 0))
    weak_topics = s_data.get("weak_topics", [])

    quizzes_attempted = await quiz_repo.count_for_subject(user_id, subject)

    recent_quizzes = await quiz_repo.find_recent_by_subject(user_id, subject, limit=5)

    recent_scores = [
        round((q["score"] / q["total_questions"]) * 100)
        for q in reversed(recent_quizzes)
        if q.get("total_questions", 0) > 0
    ]

    now = datetime.utcnow()
    day_buckets = {
        (now - timedelta(days=4 - i)).strftime("%b %d"): 0
        for i in range(5)
    }

    recent_events = await learning_events_repo.find_since(
        user_id, subject, since=now - timedelta(days=5), limit=500
    )

    for ev in recent_events:
        day_key = ev["created_at"].strftime("%b %d")
        if day_key in day_buckets:
            day_buckets[day_key] += 1

    return {
        "proficiency_score": proficiency_score,
        "engagement_score": engagement_score,
        "weak_topics": weak_topics,
        "quizzes_attempted": quizzes_attempted,
        "recent_scores": recent_scores or [0],
        "recent_activity": list(day_buckets.values()),
    }
