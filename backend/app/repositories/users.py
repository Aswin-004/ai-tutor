from datetime import datetime
from typing import Optional

from bson import ObjectId

from app.db.mongo import db


async def find_by_email(email: str) -> Optional[dict]:
    return await db.users.find_one({"email": email.lower()})


async def find_by_username(username: str) -> Optional[dict]:
    return await db.users.find_one({"username": username.lower()})


async def find_by_id(user_id: str) -> Optional[dict]:
    try:
        return await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


async def insert_user(user_doc: dict) -> dict:
    result = await db.users.insert_one(user_doc)
    return await db.users.find_one({"_id": result.inserted_id})


async def update_by_id(user_id: str, update_data: dict) -> None:
    await db.users.update_one({"_id": ObjectId(user_id)}, {"$set": update_data})


async def set_last_login(user_oid: ObjectId) -> None:
    await db.users.update_one(
        {"_id": user_oid},
        {"$set": {"last_login": datetime.utcnow()}}
    )


async def find_by_object_id(oid: ObjectId) -> Optional[dict]:
    return await db.users.find_one({"_id": oid})


async def apply_update(user_oid: ObjectId, update_op: dict) -> None:
    """Apply a raw update operator dict ($set/$inc/$addToSet/...) to a user
    document by ObjectId. The update shape varies per caller (quiz
    submission, chat engagement bump, heartbeat, subject switch, roadmap
    storage) and doesn't fit a single named method, so this stays generic."""
    await db.users.update_one({"_id": user_oid}, update_op)
