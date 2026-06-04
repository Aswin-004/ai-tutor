"""
Lightweight analytics event tracker.

Writes structured events to MongoDB `analytics_events` collection.
Every event has: user_id, event name, properties dict, timestamp.

Five core events:
    user_signed_up       — new account created
    document_uploaded    — PDF processed and embedded
    question_asked       — chat message sent
    quiz_completed       — quiz submitted with score
    roadmap_generated    — roadmap created or regenerated
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Canonical event names — use these constants everywhere
USER_SIGNED_UP      = "user_signed_up"
DOCUMENT_UPLOADED   = "document_uploaded"
QUESTION_ASKED      = "question_asked"
QUIZ_COMPLETED      = "quiz_completed"
ROADMAP_GENERATED   = "roadmap_generated"


async def track(
    db,
    event: str,
    user_id: Optional[str] = None,
    properties: Optional[Dict[str, Any]] = None,
) -> None:
    """Write one analytics event. Never raises — failures are logged and swallowed."""
    try:
        await db.analytics_events.insert_one({
            "event":      event,
            "user_id":    user_id,
            "properties": properties or {},
            "created_at": datetime.utcnow(),
        })
        logger.debug("analytics: %s user=%s props=%s", event, user_id, properties)
    except Exception as exc:
        logger.warning("analytics: failed to record event %s — %s", event, exc)
