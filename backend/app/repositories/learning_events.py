from datetime import datetime
from typing import List, Optional

from app.db.mongo import db


async def find_since(user_id: str, subject: str, since: datetime, limit: int = 500) -> List[dict]:
    return await db.learning_events.find({
        "user_id": user_id,
        "subject": subject,
        "created_at": {"$gte": since},
    }).limit(limit).to_list(None)


async def find_last_chat_event(user_id: str) -> Optional[dict]:
    return await db.learning_events.find_one(
        {"user_id": user_id, "type": "chat"},
        sort=[("created_at", -1)],
    )
