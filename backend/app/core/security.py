import logging
from datetime import datetime, timedelta
from typing import Optional

import bcrypt
from bson import ObjectId
from jose import JWTError, jwt

from app.core.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.schemas.auth import TokenData

logger = logging.getLogger(__name__)


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
