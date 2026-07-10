from typing import List, Optional

from app.db.mongo import db


async def find_recent(user_id: str, limit: int) -> List[dict]:
    """Most recent messages for a user, newest first."""
    return await db.chat_history.find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(limit).to_list(None)


async def find_last_assistant_message(user_id: str) -> Optional[dict]:
    return await db.chat_history.find_one(
        {"user_id": user_id, "role": "assistant"},
        sort=[("created_at", -1)],
    )


async def delete_all(user_id: str) -> None:
    await db.chat_history.delete_many({"user_id": user_id})


async def count_for_user(user_id: str) -> int:
    return await db.chat_history.count_documents({"user_id": user_id})
