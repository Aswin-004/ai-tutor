from typing import List, Optional

from bson import ObjectId

from app.db.mongo import db


async def insert_document(record: dict) -> None:
    await db.documents.insert_one(record)


async def find_for_user(user_id: str, skip: int, limit: int) -> List[dict]:
    return await db.documents.find(
        {"user_id": user_id}
    ).sort("uploaded_at", -1).skip(skip).limit(limit).to_list(None)


async def find_owned(doc_id: ObjectId, user_id: str) -> Optional[dict]:
    return await db.documents.find_one({"_id": doc_id, "user_id": user_id})


async def delete_by_id(doc_id: ObjectId) -> None:
    await db.documents.delete_one({"_id": doc_id})


async def count_for_user(user_id: str) -> int:
    return await db.documents.count_documents({"user_id": user_id})
