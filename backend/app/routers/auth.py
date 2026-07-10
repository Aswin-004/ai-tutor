import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.core.config import ACCESS_TOKEN_EXPIRE_MINUTES
from app.core.security import create_access_token
from app.core.limiter import limiter
from app.db.mongo import db
from app.dependencies.auth import get_current_active_user
from app.models.subject import default_subject_stats
from app.repositories import users as users_repo
from app.schemas.auth import (
    UserCreate, UserLogin, UserResponse, UserProfileUpdate, Token, PasswordChange,
)
from app.schemas.subject import SubjectSwitch
from app.services.analytics_service import track, USER_SIGNED_UP
from app.services.auth_service import (
    authenticate_user, create_user,
    get_user_by_email, get_user_by_username, update_user_profile,
    change_user_password, mongo_user_to_response,
)
from app.services.session_manager import evict_user_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate):
    if await get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    if await get_user_by_username(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    user = await create_user(user_data)

    access_token = create_access_token(
        data={"sub": str(user["_id"]), "username": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    await track(db, USER_SIGNED_UP, user_id=str(user["_id"]), properties={
        "username": user["username"],
    })

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=mongo_user_to_response(user)
    )


@router.post("/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, credentials: UserLogin):
    user = await authenticate_user(credentials.username, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user["_id"]), "username": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=mongo_user_to_response(user)
    )


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    return mongo_user_to_response(current_user)


@router.put("/profile", response_model=UserResponse)
async def update_profile(
    profile: UserProfileUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    updated_user = await update_user_profile(str(current_user["_id"]), profile)
    evict_user_session(str(current_user["_id"]))
    return mongo_user_to_response(updated_user)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_active_user)):
    evict_user_session(str(current_user["_id"]))
    return {"message": "Logged out successfully"}


@router.post("/change-password")
@limiter.limit("3/minute")
async def change_password(
    request: Request,
    body: PasswordChange,
    current_user: dict = Depends(get_current_active_user),
):
    success = await change_user_password(
        str(current_user["_id"]), body.current_password, body.new_password
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    evict_user_session(str(current_user["_id"]))
    return {"message": "Password changed successfully"}


@router.patch("/subject")
async def switch_subject(
    body: SubjectSwitch,
    current_user: dict = Depends(get_current_active_user),
):
    subject = body.subject.strip().lower()

    user_id = str(current_user["_id"])
    evict_user_session(user_id)

    now = datetime.utcnow()
    update: dict = {"$set": {"current_subject": subject, "last_active": now}}

    if subject not in current_user.get("subjects", {}):
        update["$set"][f"subjects.{subject}"] = default_subject_stats()

    await users_repo.apply_update(current_user["_id"], update)
    logger.info("user %s switched subject to %s", user_id, subject)
    return {"subject": subject}
