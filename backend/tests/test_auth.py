"""
Unit tests for auth — pure functions only (no DB calls).
All tests run without MongoDB; they cover password hashing, JWT
encode/decode, Pydantic validators, and the response mapper.
"""
import pytest
from datetime import datetime, timedelta
from bson import ObjectId

from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)
from app.services.auth_service import mongo_user_to_response
from app.schemas.auth import UserCreate


# ── Password hashing ─────────────────────────────────────────────────────────

def test_password_hash_roundtrip():
    hashed = get_password_hash("mysecurepassword")
    assert verify_password("mysecurepassword", hashed)


def test_wrong_password_rejected():
    hashed = get_password_hash("correct")
    assert not verify_password("wrong", hashed)


def test_hash_is_not_plaintext():
    pw = "plaintext123"
    assert get_password_hash(pw) != pw


def test_verify_handles_garbage_hash():
    assert not verify_password("any", "not-a-bcrypt-hash")


# ── JWT encode / decode ───────────────────────────────────────────────────────

def test_create_and_decode_token():
    oid = str(ObjectId())
    token = create_access_token({"sub": oid, "username": "alice"})
    data = decode_access_token(token)
    assert data is not None
    assert data.user_id == oid
    assert data.username == "alice"


def test_expired_token_returns_none():
    oid = str(ObjectId())
    token = create_access_token({"sub": oid}, expires_delta=timedelta(seconds=-1))
    assert decode_access_token(token) is None


def test_tampered_token_returns_none():
    assert decode_access_token("not.a.real.token") is None


def test_token_missing_sub_returns_none():
    # encode a token with no 'sub' field
    token = create_access_token({"username": "alice"})
    assert decode_access_token(token) is None


def test_token_with_non_objectid_sub_returns_none():
    # 'sub' present but not a valid ObjectId
    token = create_access_token({"sub": "not-an-objectid"})
    assert decode_access_token(token) is None


# ── UserCreate validators ─────────────────────────────────────────────────────

def test_username_too_short_raises():
    with pytest.raises(Exception, match="3 characters"):
        UserCreate(email="a@b.com", username="ab", password="password123")


def test_username_too_long_raises():
    with pytest.raises(Exception):
        UserCreate(email="a@b.com", username="a" * 51, password="password123")


def test_username_with_at_sign_raises():
    with pytest.raises(Exception, match="alphanumeric"):
        UserCreate(email="a@b.com", username="user@name", password="password123")


def test_password_too_short_raises():
    with pytest.raises(Exception, match="8 characters"):
        UserCreate(email="a@b.com", username="alice", password="short")


def test_username_normalised_to_lowercase():
    u = UserCreate(email="a@b.com", username="ALICE", password="password123")
    assert u.username == "alice"


def test_valid_username_with_underscore_and_hyphen():
    u = UserCreate(email="a@b.com", username="alice_bob-99", password="password123")
    assert u.username == "alice_bob-99"


def test_invalid_email_raises():
    with pytest.raises(Exception):
        UserCreate(email="not-an-email", username="alice", password="password123")


# ── mongo_user_to_response ───────────────────────────────────────────────────

def test_mongo_user_to_response_maps_all_fields():
    oid = ObjectId()
    now = datetime.utcnow()
    user = {
        "_id": oid,
        "email": "test@example.com",
        "username": "testuser",
        "full_name": "Test User",
        "level": "Intermediate",
        "learning_style": "Visual",
        "goals": "Ace the exam",
        "is_active": True,
        "created_at": now,
    }
    resp = mongo_user_to_response(user)
    assert resp.id == str(oid)
    assert resp.email == "test@example.com"
    assert resp.username == "testuser"
    assert resp.full_name == "Test User"
    assert resp.is_active is True
    assert resp.created_at == now


def test_mongo_user_to_response_optional_fields_none():
    oid = ObjectId()
    user = {
        "_id": oid,
        "email": "x@x.com",
        "username": "xuser",
        "is_active": True,
        "created_at": datetime.utcnow(),
    }
    resp = mongo_user_to_response(user)
    assert resp.full_name is None
    assert resp.level is None
