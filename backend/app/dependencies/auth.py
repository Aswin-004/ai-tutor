import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.core.security import decode_access_token
from app.models.subject import default_subject_stats
from app.repositories import users as users_repo

logger = logging.getLogger(__name__)

# Bearer token security
security = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if credentials is None:
        logger.warning("Auth failed: no credentials provided")
        raise credentials_exception

    token = credentials.credentials
    token_data = decode_access_token(token)

    if token_data is None:
        logger.warning("Auth failed: token decode returned None")
        raise credentials_exception

    user = await users_repo.find_by_id(token_data.user_id)

    if user is None:
        logger.warning("Auth failed: user %s not found", token_data.user_id)
        raise credentials_exception

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is disabled"
        )

    # Backward-compat defaults for fields added after initial release
    user.setdefault("strong_topics", [])
    user.setdefault("current_topic", None)
    user.setdefault("proficiency_score", 0)
    user.setdefault("engagement_score", 0)
    user.setdefault("cumulative_score", 0.0)
    user.setdefault("total_attempts", 0)
    user.setdefault("last_active", None)
    # Multi-subject state — existing users get an empty dict; new users start fresh
    user.setdefault("subjects", {})
    user.setdefault("current_subject", "general")
    # Ensure the active subject slot always exists so callers never get a KeyError
    _subject = user["current_subject"]
    if _subject not in user["subjects"]:
        user["subjects"][_subject] = default_subject_stats()

    logger.debug("Auth successful: %s", user["username"])
    return user


async def get_current_active_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    if not current_user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user"
        )
    return current_user
