from app.db.mongo import db


async def insert_feedback(record: dict) -> None:
    await db.feedback.insert_one(record)


async def insert_explanation_failure(record: dict) -> None:
    await db.explanation_failures.insert_one(record)
