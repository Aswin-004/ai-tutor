import os
import motor.motor_asyncio
from dotenv import load_dotenv

load_dotenv()

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "ai_tutor")

client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client[DB_NAME]


async def init_indexes():
    await db.users.create_index("email", unique=True)
    await db.users.create_index("username", unique=True)
    await db.chat_history.create_index("user_id")
    await db.quiz_performance.create_index("user_id")
    await db.documents.create_index("user_id")
    await db.feedback.create_index("user_id")
    await db.learning_events.create_index("user_id")
    await db.learning_events.create_index("created_at")
    await db.user_models.create_index("user_id", unique=True)
    await db.analytics_events.create_index("user_id")
    await db.analytics_events.create_index("event")
    await db.analytics_events.create_index("created_at")
    await db.explanation_failures.create_index("user_id")
    await db.explanation_failures.create_index("topic")
