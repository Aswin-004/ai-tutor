from typing import List, Optional

from app.db.mongo import db


async def insert_performance(record: dict) -> None:
    await db.quiz_performance.insert_one(record)


async def find_by_subject(user_id: str, subject: str, limit: int = 200) -> List[dict]:
    """Unsorted — used to aggregate scores per topic for weak-topic recompute."""
    return await db.quiz_performance.find(
        {"user_id": user_id, "subject": subject}
    ).limit(limit).to_list(None)


async def find_recent_by_subject(user_id: str, subject: str, limit: int) -> List[dict]:
    """Newest-first — used for score history/trend displays."""
    return await db.quiz_performance.find(
        {"user_id": user_id, "subject": subject}
    ).sort("created_at", -1).limit(limit).to_list(None)


async def find_recent_all_subjects(user_id: str, limit: int = 200) -> List[dict]:
    """All-subject recent performance — seeds a brand-new session's weak topics."""
    return await db.quiz_performance.find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(limit).to_list(None)


async def find_last(user_id: str) -> Optional[dict]:
    """Most recent quiz for any subject — used as a chat-topic hint."""
    return await db.quiz_performance.find_one({"user_id": user_id}, sort=[("created_at", -1)])


async def count_for_subject(user_id: str, subject: str) -> int:
    return await db.quiz_performance.count_documents({"user_id": user_id, "subject": subject})
