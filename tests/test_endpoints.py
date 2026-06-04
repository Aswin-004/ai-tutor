"""
Integration tests for the FastAPI app.

Uses httpx.AsyncClient + ASGITransport so tests run in-process.
MongoDB and external APIs are patched at the module level so no real
connections are made.  Only the happy path and key error cases are covered.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime
from bson import ObjectId
from httpx import AsyncClient, ASGITransport


# ── App fixture ──────────────────────────────────────────────────────────────

@pytest.fixture()
def mock_db():
    """Return a MagicMock that covers all collection accesses in mongo.db."""
    db = MagicMock()

    # All collection methods are async
    for col in ("users", "chat_history", "quiz_performance", "documents",
                "feedback", "learning_events"):
        col_mock = MagicMock()
        col_mock.find_one = AsyncMock(return_value=None)
        col_mock.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
        col_mock.update_one = AsyncMock()
        col_mock.delete_one = AsyncMock()
        col_mock.delete_many = AsyncMock()
        col_mock.count_documents = AsyncMock(return_value=0)
        col_mock.create_index = AsyncMock()
        col_mock.find = MagicMock(
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
        setattr(db, col, col_mock)

    return db


@pytest.fixture()
def app_with_mocks(mock_db):
    """Import the FastAPI app with MongoDB and ChromaDB patched out."""
    with patch("mongo.db", mock_db), \
         patch("chromadb.PersistentClient"), \
         patch("mongo.init_indexes", new=AsyncMock()):
        import importlib
        import app as app_module
        importlib.reload(app_module)  # re-bind patched mongo.db
        yield app_module.app


# ── /health ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_health_check(app_with_mocks):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "healthy"
    assert "version" in body


# ── / (frontend) ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_root_serves_html(app_with_mocks):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


# ── POST /auth/register ───────────────────────────────────────────────────────

def _fake_user_doc(username="alice", email="alice@example.com"):
    oid = ObjectId()
    return {
        "_id": oid,
        "email": email,
        "username": username,
        "full_name": None,
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
        "subjects": {"general": {}},
        "last_active": datetime.utcnow(),
        "roadmap": None,
        "is_active": True,
        "is_verified": False,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
        "last_login": None,
        "hashed_password": "$2b$12$fakehash",
    }


@pytest.mark.asyncio
async def test_register_success(app_with_mocks, mock_db):
    user_doc = _fake_user_doc()
    # No existing user → no conflict
    mock_db.users.find_one = AsyncMock(side_effect=[None, None, user_doc])
    mock_db.users.insert_one = AsyncMock(return_value=MagicMock(inserted_id=user_doc["_id"]))

    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.post("/auth/register", json={
            "email": "alice@example.com",
            "username": "alice",
            "password": "securepassword123",
        })
    assert response.status_code == 201
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_register_duplicate_email_rejected(app_with_mocks, mock_db):
    existing = _fake_user_doc()
    mock_db.users.find_one = AsyncMock(return_value=existing)

    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.post("/auth/register", json={
            "email": "alice@example.com",
            "username": "newuser",
            "password": "securepassword123",
        })
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_register_invalid_email_rejected(app_with_mocks):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.post("/auth/register", json={
            "email": "not-an-email",
            "username": "alice",
            "password": "securepassword123",
        })
    assert response.status_code == 422


# ── POST /auth/login ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_login_wrong_credentials(app_with_mocks, mock_db):
    mock_db.users.find_one = AsyncMock(return_value=None)

    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.post("/auth/login", json={
            "username": "nobody",
            "password": "wrong",
        })
    assert response.status_code == 401


# ── Protected endpoints without token ────────────────────────────────────────

@pytest.mark.asyncio
async def test_protected_endpoint_without_token(app_with_mocks):
    async with AsyncClient(
        transport=ASGITransport(app=app_with_mocks), base_url="http://test"
    ) as client:
        response = await client.get("/stats")
    assert response.status_code == 403
