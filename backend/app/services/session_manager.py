"""In-memory LearningSystem session cache with TTL eviction.

Shared across the auth/chat/documents/quiz/roadmap/stats routers so a
user's LearningSystem instance (and its ChromaDB handle) isn't rebuilt
on every request.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict

from app.db.mongo import db
from app.models.subject import subject_data
from app.repositories import quiz as quiz_repo
from app.services.learning_system import LearningSystem
from app.services.user_memory import UserMemoryManager

logger = logging.getLogger(__name__)

# Active learning sessions (in-memory cache)
active_sessions: Dict[str, LearningSystem] = {}
# Tracks when each session was last accessed for TTL eviction
_session_last_access: Dict[str, datetime] = {}
_SESSION_TTL_HOURS = 4


def _evict_stale_sessions() -> None:
    """Remove sessions idle longer than _SESSION_TTL_HOURS."""
    cutoff = datetime.utcnow() - timedelta(hours=_SESSION_TTL_HOURS)
    stale = [uid for uid, ts in _session_last_access.items() if ts < cutoff]
    for uid in stale:
        active_sessions.pop(uid, None)
        _session_last_access.pop(uid, None)
    if stale:
        logger.info("evicted %d stale session(s)", len(stale))


async def get_learning_session(user: dict) -> LearningSystem:
    user_id = str(user["_id"])
    _evict_stale_sessions()
    if user_id not in active_sessions:
        profile = {
            "username": user["username"],
            "full_name": user.get("full_name"),
            # Drive the tutor's persona/style-guide subject from the active
            # workspace (current_subject), not the legacy singular `subject`
            # field — that field has no UI to set it and was always None,
            # so the AI persona never reflected which workspace was active.
            "subject": (user.get("current_subject") or "general").title(),
            "level": user.get("level") or "Intermediate",
            "learning_style": user.get("learning_style") or "Visual",
            "goals": user.get("goals") or "Learn effectively",
        }

        # Load persistent user memory and enrich profile
        memory_mgr = UserMemoryManager(user_id, db)
        user_model = await memory_mgr.load()

        if user_model.get("style_profile"):
            profile["style_profile"] = user_model["style_profile"]

        session = LearningSystem(user_id, profile)
        session.memory_mgr = memory_mgr
        session.user_model = user_model

        subject = user.get("current_subject", "general")
        s_data = subject_data(user, subject)
        weak_topics = s_data.get("weak_topics") or user.get("weak_topics")
        if weak_topics:
            session.weak_topics = weak_topics
            session.system_instruction = session._build_persona()
        else:
            all_perf = await quiz_repo.find_recent_all_subjects(user_id, limit=200)
            quiz_data = [
                {"topic": p["topic"], "score": (p["score"] / p["total_questions"]) * 100}
                for p in all_perf if p.get("total_questions", 0) > 0
            ]
            session.update_weak_topics(quiz_data)

        active_sessions[user_id] = session
    _session_last_access[user_id] = datetime.utcnow()
    return active_sessions[user_id]


def evict_user_session(user_id: str) -> None:
    """Drop a cached session — call after profile/password/subject changes
    that invalidate the cached persona/profile."""
    active_sessions.pop(user_id, None)
    _session_last_access.pop(user_id, None)
