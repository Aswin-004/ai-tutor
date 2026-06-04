import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from fastapi import Depends, HTTPException, status

logger = logging.getLogger(__name__)
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError, jwt
import bcrypt
from bson import ObjectId
from pydantic import BaseModel, EmailStr, field_validator
from dotenv import load_dotenv

from mongo import db

load_dotenv()

# Configuration
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY:
    raise ValueError("SECRET_KEY environment variable must be set — refusing to start without it")
ALGORITHM = os.getenv("ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))

# Bearer token security
security = HTTPBearer(auto_error=False)


# ==================== PASSWORD HASHING (Direct bcrypt) ====================

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(
            plain_password.encode('utf-8'),
            hashed_password.encode('utf-8')
        )
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


def get_password_hash(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')


# ==================== PYDANTIC SCHEMAS ====================

class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    full_name: Optional[str] = None

    @field_validator('username')
    @classmethod
    def username_validation(cls, v):
        if len(v) < 3:
            raise ValueError('Username must be at least 3 characters')
        if len(v) > 50:
            raise ValueError('Username must be less than 50 characters')
        if not v.replace('_', '').replace('-', '').isalnum():
            raise ValueError('Username must be alphanumeric (underscore and hyphen allowed)')
        return v.lower()

    @field_validator('password')
    @classmethod
    def password_validation(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        return v


class UserLogin(BaseModel):
    username: str
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    username: str
    full_name: Optional[str] = None
    subject: Optional[str] = None
    level: Optional[str] = None
    learning_style: Optional[str] = None
    goals: Optional[str] = None
    is_active: bool
    created_at: datetime


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    subject: Optional[str] = None
    level: Optional[str] = None
    learning_style: Optional[str] = None
    goals: Optional[str] = None


class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse


class TokenData(BaseModel):
    user_id: Optional[str] = None
    username: Optional[str] = None


# ==================== RESPONSE HELPER ====================

def mongo_user_to_response(user: dict) -> UserResponse:
    return UserResponse(
        id=str(user["_id"]),
        email=user["email"],
        username=user["username"],
        full_name=user.get("full_name"),
        subject=user.get("subject"),
        level=user.get("level"),
        learning_style=user.get("learning_style"),
        goals=user.get("goals"),
        is_active=user.get("is_active", True),
        created_at=user.get("created_at", datetime.utcnow()),
    )


# ==================== TOKEN FUNCTIONS ====================

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()

    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})

    if "sub" in to_encode:
        to_encode["sub"] = str(to_encode["sub"])

    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[TokenData]:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        user_id_str = payload.get("sub")
        username = payload.get("username")

        if user_id_str is None:
            logger.warning("Token decode failed: no 'sub' in payload")
            return None

        try:
            ObjectId(user_id_str)
        except Exception:
            logger.warning("Token decode failed: 'sub' is not a valid ObjectId: %s", user_id_str)
            return None

        return TokenData(user_id=user_id_str, username=username)

    except JWTError as e:
        logger.warning("JWT decode error: %s", e)
        return None
    except Exception as e:
        logger.error("Token decode error: %s", e)
        return None


# ==================== USER FUNCTIONS ====================

async def get_user_by_email(email: str) -> Optional[dict]:
    return await db.users.find_one({"email": email.lower()})


async def get_user_by_username(username: str) -> Optional[dict]:
    return await db.users.find_one({"username": username.lower()})


async def get_user_by_id(user_id: str) -> Optional[dict]:
    try:
        return await db.users.find_one({"_id": ObjectId(user_id)})
    except Exception:
        return None


async def create_user(user: UserCreate) -> dict:
    hashed_password = get_password_hash(user.password)
    now = datetime.utcnow()
    _empty_subject_slot = {
        "weak_topics": [],
        "strong_topics": [],
        "proficiency_score": 0,
        "engagement_score": 0,
        "cumulative_score": 0.0,
        "total_attempts": 0,
    }
    user_doc = {
        "email": user.email.lower(),
        "username": user.username.lower(),
        "hashed_password": hashed_password,
        "full_name": user.full_name,
        "subject": None,
        "level": None,
        "learning_style": None,
        "goals": None,
        "weak_topics": [],
        "strong_topics": [],
        "current_topic": None,
        "proficiency_score": 0,
        "engagement_score": 0,
        "current_subject": "general",
        "subjects": {"general": dict(_empty_subject_slot)},
        "last_active": now,
        "roadmap": None,
        "is_active": True,
        "is_verified": False,
        "created_at": now,
        "updated_at": now,
        "last_login": None,
    }
    result = await db.users.insert_one(user_doc)
    return await db.users.find_one({"_id": result.inserted_id})


async def authenticate_user(username: str, password: str) -> Optional[dict]:
    user = await get_user_by_username(username)
    if not user:
        user = await get_user_by_email(username)

    if not user:
        return None

    if not verify_password(password, user["hashed_password"]):
        return None

    await db.users.update_one(
        {"_id": user["_id"]},
        {"$set": {"last_login": datetime.utcnow()}}
    )
    return user


async def change_user_password(user_id: str, current_password: str, new_password: str) -> bool:
    user = await get_user_by_id(user_id)
    if not user:
        return False
    if not verify_password(current_password, user["hashed_password"]):
        return False
    new_hash = get_password_hash(new_password)
    await db.users.update_one(
        {"_id": ObjectId(user_id)},
        {"$set": {"hashed_password": new_hash, "updated_at": datetime.utcnow()}},
    )
    return True


async def update_user_profile(user_id: str, profile: UserProfileUpdate) -> Optional[dict]:
    update_data = {k: v for k, v in profile.model_dump(exclude_unset=True).items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.utcnow()
        await db.users.update_one(
            {"_id": ObjectId(user_id)},
            {"$set": update_data}
        )
    return await get_user_by_id(user_id)


# ==================== AUTH DEPENDENCIES ====================

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

    user = await get_user_by_id(token_data.user_id)

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
        user["subjects"][_subject] = {
            "weak_topics": [],
            "strong_topics": [],
            "proficiency_score": 0,
            "engagement_score": 0,
        }

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
