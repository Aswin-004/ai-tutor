from datetime import datetime
from typing import Optional

from app.core.security import get_password_hash, verify_password
from app.models.subject import default_subject_stats
from app.repositories import users as users_repo
from app.schemas.auth import UserCreate, UserProfileUpdate, UserResponse


# ==================== RESPONSE HELPER ====================

def mongo_user_to_response(user: dict) -> UserResponse:
    raw_subjects = list(user.get("subjects", {}).keys())
    subjects_list = raw_subjects if raw_subjects else ["general"]
    current_sub = user.get("current_subject", "general")
    if current_sub and current_sub not in subjects_list:
        subjects_list.insert(0, current_sub)
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        username=user["username"],
        full_name=user.get("full_name"),
        level=user.get("level"),
        learning_style=user.get("learning_style"),
        goals=user.get("goals"),
        is_active=user.get("is_active", True),
        created_at=user.get("created_at", datetime.utcnow()),
        subjects_list=subjects_list,
        current_subject=current_sub,
    )


# ==================== USER FUNCTIONS ====================

async def get_user_by_email(email: str) -> Optional[dict]:
    return await users_repo.find_by_email(email)


async def get_user_by_username(username: str) -> Optional[dict]:
    return await users_repo.find_by_username(username)


async def get_user_by_id(user_id: str) -> Optional[dict]:
    return await users_repo.find_by_id(user_id)


async def create_user(user: UserCreate) -> dict:
    hashed_password = get_password_hash(user.password)
    now = datetime.utcnow()
    user_doc = {
        "email": user.email.lower(),
        "username": user.username.lower(),
        "hashed_password": hashed_password,
        "full_name": user.full_name,
        "level": None,
        "learning_style": None,
        "goals": None,
        "weak_topics": [],
        "strong_topics": [],
        "current_topic": None,
        "proficiency_score": 0,
        "engagement_score": 0,
        "current_subject": "general",
        "subjects": {"general": default_subject_stats()},
        "last_active": now,
        "roadmap": None,
        "is_active": True,
        "is_verified": False,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    }
    return await users_repo.insert_user(user_doc)


async def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = await users_repo.find_by_username(username)
    if not user:
        user = await users_repo.find_by_email(username)

    if not user:
        return None

    if not verify_password(password, user["hashed_password"]):
        return None

    await users_repo.set_last_login(user["_id"])
    return user


async def change_user_password(user_id: str, current_password: str, new_password: str) -> bool:
    user = await users_repo.find_by_id(user_id)
    if not user:
        return False
    if not verify_password(current_password, user["hashed_password"]):
        return False
    new_hash = get_password_hash(new_password)
    await users_repo.update_by_id(
        user_id, {"hashed_password": new_hash, "updated_at": datetime.utcnow()}
    )
    return True


async def update_user_profile(user_id: str, profile: UserProfileUpdate) -> Optional[dict]:
    update_data = {k: v for k, v in profile.model_dump(exclude_unset=True).items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        await users_repo.update_by_id(user_id, update_data)
    return await users_repo.find_by_id(user_id)
