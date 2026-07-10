import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_LOW_ENGAGEMENT_THRESHOLD = 3


def decide_next_step(user: dict, subject_data: dict) -> dict:
    weak_topics: list = subject_data.get("weak_topics") or []
    # proficiency_score stored as 0–100 in subject_data; normalize to 0–1
    proficiency: float = subject_data.get("proficiency_score", 0) / 100.0
    engagement_score: int = subject_data.get("engagement_score", 0)

    logger.debug(
        "decision_engine weak_count=%d prof=%.2f engagement=%d",
        len(weak_topics), proficiency, engagement_score,
    )

    next_topic = weak_topics[0] if weak_topics else None

    if proficiency < 0.5:
        strategy = "teach"
        difficulty = "basic"
    elif proficiency < 0.8:
        strategy = "revise"
        difficulty = "intermediate"
    else:
        strategy = "challenge"
        difficulty = "advanced"

    # Engagement-based tone + difficulty tuning
    tone = "neutral"
    if engagement_score < _LOW_ENGAGEMENT_THRESHOLD:
        difficulty = "basic"
        tone = "supportive"
    elif engagement_score > 10:
        tone = "challenging"

    # Inactivity detection — override to revise + re-engage if away > 5 min
    last_active = user.get("last_active")
    if last_active:
        now_utc = datetime.now(timezone.utc)
        if last_active.tzinfo is None:          # MongoDB stores naive UTC datetimes
            last_active = last_active.replace(tzinfo=timezone.utc)
        if (now_utc - last_active).total_seconds() > 300:
            strategy = "revise"
            tone = "re-engage"

    return {
        "next_topic": next_topic,
        "difficulty": difficulty,
        "strategy": strategy,
        "tone": tone,
    }
