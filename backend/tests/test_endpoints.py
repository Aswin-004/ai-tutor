"""
Integration tests for the FastAPI app.

Uses httpx.AsyncClient + ASGITransport so tests run in-process.
MongoDB and external APIs are patched before the app module is imported,
so no real connections are ever made.
"""
import pytest
import sys
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from bson import ObjectId
from httpx import AsyncClient, ASGITransport


# ── Shared mock DB factory ────────────────────────────────────────────────────

def _make_col():
    """Return a fully-mocked Motor collection."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    col.update_one = AsyncMock()
    col.delete_one = AsyncMock()
    col.delete_many = AsyncMock()
    col.count_documents = AsyncMock(return_value=0)
    col.create_index = AsyncMock()
    col.find = MagicMock(
        return_value=MagicMock(
            sort=MagicMock(
                return_value=MagicMock(
                    limit=MagicMock(
                        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
                    ),
                    to_list=AsyncMock(return_value=[]),
                )
            ),
            to_list=AsyncMock(return_value=[]),
        )
    )
    return col


@pytest.fixture(scope="module")
def mock_db():
    db = MagicMock()
    for name in ("users", "chat_history", "quiz_performance", "documents",
                 "feedback", "learning_events", "user_models"):
        setattr(db, name, _make_col())
    return db


@pytest.fixture(scope="module")
def app_client(mock_db):
    """Import and return the FastAPI app with all external I/O mocked."""
    # Remove any previously cached app import so patches take effect cleanly
    for mod in list(sys.modules.keys()):
        if mod == "app" or mod.startswith("app.") or mod in ("mongo", "core", "auth"):
            sys.modules.pop(mod, None)

    with patch("motor.motor_asyncio.AsyncIOMotorClient", return_value=MagicMock()), \
         patch("chromadb.PersistentClient"), \
         patch("mongo.init_indexes", new=AsyncMock()):
        import mongo
        mongo.db = mock_db

        import app.main as app_module
        app_module.db = mock_db

        yield app_module.app


# ── /health ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(app_client):
    async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as c:
        r = await c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "healthy"


# ── / (frontend) ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root_serves_html(app_client):
    async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as c:
        r = await c.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


# ── POST /auth/register ───────────────────────────────────────────────────────

def _fake_user(username="alice", email="alice@example.com"):
    oid = ObjectId()
    return {
        "_id": oid, "email": email, "username": username,
        "full_name": None, "subject": None, "level": None,
        "learning_style": None, "goals": None,
        "weak_topics": [], "strong_topics": [], "current_topic": None,
        "proficiency_score": 0, "engagement_score": 0,
        "current_subject": "general", "subjects": {"general": {}},
        "last_active": datetime.utcnow(), "roadmap": None,
        "is_active": True, "is_verified": False,
        "created_at": datetime.utcnow(), "updated_at": datetime.utcnow(),
        "last_login": None, "hashed_password": "$2b$12$fakehash",
    }


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(app_client, mock_db):
    mock_db.users.find_one = AsyncMock(return_value=_fake_user())
    async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as c:
        r = await c.post("/auth/register", json={
            "email": "alice@example.com",
            "username": "newuser",
            "password": "securepassword123",
        })
    assert r.status_code == 400
    assert "already registered" in r.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_invalid_email_rejected(app_client):
    async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as c:
        r = await c.post("/auth/register", json={
            "email": "not-an-email",
            "username": "alice",
            "password": "securepassword123",
        })
    assert r.status_code == 422


# ── POST /auth/login ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_wrong_credentials(app_client, mock_db):
    mock_db.users.find_one = AsyncMock(return_value=None)
    async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as c:
        r = await c.post("/auth/login", json={"username": "nobody", "password": "wrong"})
    assert r.status_code == 401


# ── Protected endpoints without token ────────────────────────────────────────

@pytest.mark.asyncio
async def test_protected_endpoint_without_token(app_client):
    async with AsyncClient(transport=ASGITransport(app=app_client), base_url="http://test") as c:
        r = await c.get("/stats")
    assert r.status_code in (401, 403)
