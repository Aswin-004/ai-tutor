"""
Unit tests for UserMemoryManager and the memory-aware prompt pipeline.

All MongoDB calls are mocked — no real DB needed.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta


# ── UserMemoryManager ─────────────────────────────────────────────────────────

def _make_db():
    """Return a minimal mock for the MongoDB `user_models` collection."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.update_one = AsyncMock()
    db = MagicMock()
    db.user_models = col
    db.chat_history = MagicMock()
    db.chat_history.find = MagicMock(
        return_value=MagicMock(
            sort=MagicMock(
                return_value=MagicMock(
                    limit=MagicMock(
                        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
                    )
                )
            )
        )
    )
    return db


@pytest.mark.asyncio
async def test_load_returns_empty_dict_for_new_user():
    from core import UserMemoryManager
    db = _make_db()
    mgr = UserMemoryManager("user1", db)
    result = await mgr.load()
    assert result == {}


@pytest.mark.asyncio
async def test_load_returns_existing_model():
    from core import UserMemoryManager
    db = _make_db()
    db.user_models.find_one = AsyncMock(return_value={
        "user_id": "user1",
        "style_profile": "Casual tone, uses short sentences.",
    })
    mgr = UserMemoryManager("user1", db)
    result = await mgr.load()
    assert result["style_profile"] == "Casual tone, uses short sentences."


@pytest.mark.asyncio
async def test_record_emotion_calls_update_one():
    from core import UserMemoryManager
    db = _make_db()
    mgr = UserMemoryManager("user1", db)
    await mgr.record_emotion("frustrated", "recursion", "DSA")
    db.user_models.update_one.assert_called_once()
    call_args = db.user_models.update_one.call_args
    assert call_args[1]["upsert"] is True


@pytest.mark.asyncio
async def test_record_dropoff_uses_add_to_set():
    from core import UserMemoryManager
    db = _make_db()
    mgr = UserMemoryManager("user1", db)
    await mgr.record_dropoff("linked lists", "DSA")
    call_args = db.user_models.update_one.call_args
    update = call_args[0][1]
    assert "$addToSet" in update


@pytest.mark.asyncio
async def test_build_style_profile_skips_when_too_few_messages():
    from core import UserMemoryManager
    db = _make_db()
    mgr = UserMemoryManager("user1", db)
    result = await mgr.build_style_profile([{"role": "user", "message": "hi"}] * 5)
    assert result == ""


@pytest.mark.asyncio
async def test_build_style_profile_uses_cached_when_fresh():
    from core import UserMemoryManager
    db = _make_db()
    db.user_models.find_one = AsyncMock(return_value={
        "user_id": "user1",
        "style_profile": "Uses informal language.",
        "style_updated_at": datetime.utcnow(),  # just updated
    })
    mgr = UserMemoryManager("user1", db)
    messages = [{"role": "user", "message": f"msg {i}"} for i in range(25)]
    result = await mgr.build_style_profile(messages)
    assert result == "Uses informal language."


@pytest.mark.asyncio
async def test_build_style_profile_regenerates_when_stale():
    from core import UserMemoryManager
    db = _make_db()
    db.user_models.find_one = AsyncMock(return_value={
        "user_id": "user1",
        "style_profile": "Old profile.",
        "style_updated_at": datetime.utcnow() - timedelta(days=10),
    })
    mgr = UserMemoryManager("user1", db)
    messages = [{"role": "user", "message": f"explain topic {i}"} for i in range(25)]

    with patch("core.safe_generate", new=AsyncMock(return_value="• Casual\n• Short\n• Direct")):
        result = await mgr.build_style_profile(messages)

    assert result == "• Casual\n• Short\n• Direct"
    db.user_models.update_one.assert_called()


# ── frustration_summary ───────────────────────────────────────────────────────

def test_frustration_summary_empty_model():
    from core import UserMemoryManager
    mgr = UserMemoryManager("u", MagicMock())
    assert mgr.frustration_summary({}) == ""


def test_frustration_summary_no_frustration():
    from core import UserMemoryManager
    mgr = UserMemoryManager("u", MagicMock())
    model = {"recent_emotions": [{"emotion": "neutral", "topic": "x", "subject": "DSA"}] * 5}
    assert mgr.frustration_summary(model) == ""


def test_frustration_summary_high_rate():
    from core import UserMemoryManager
    mgr = UserMemoryManager("u", MagicMock())
    model = {
        "recent_emotions": [
            {"emotion": "frustrated", "topic": "recursion", "subject": "DSA"}
        ] * 12 + [
            {"emotion": "neutral", "topic": "arrays", "subject": "DSA"}
        ] * 8
    }
    summary = mgr.frustration_summary(model)
    assert "recursion" in summary
    assert "frustration rate" in summary


# ── dropoff_warning ───────────────────────────────────────────────────────────

def test_dropoff_warning_no_match():
    from core import UserMemoryManager
    mgr = UserMemoryManager("u", MagicMock())
    model = {"dropoff_topics": [{"topic": "linked lists", "subject": "DSA"}]}
    assert mgr.dropoff_warning(model, "recursion") == ""


def test_dropoff_warning_match():
    from core import UserMemoryManager
    mgr = UserMemoryManager("u", MagicMock())
    model = {"dropoff_topics": [{"topic": "linked lists", "subject": "DSA"}]}
    warning = mgr.dropoff_warning(model, "linked lists")
    assert "abandoned" in warning.lower()
    assert "linked lists" in warning


def test_dropoff_warning_case_insensitive():
    from core import UserMemoryManager
    mgr = UserMemoryManager("u", MagicMock())
    model = {"dropoff_topics": [{"topic": "Linked Lists", "subject": "DSA"}]}
    warning = mgr.dropoff_warning(model, "linked lists")
    assert warning != ""


# ── Memory context in prompt pipeline ────────────────────────────────────────

@pytest.mark.asyncio
async def test_chat_passes_memory_context_to_prompt():
    import json
    from core import LearningSystem
    captured = []

    async def capture(client, model, prompt):
        captured.append(prompt)
        return json.dumps([])

    profile = {"level": "Intermediate", "learning_style": "Visual", "subject": "DSA"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(side_effect=capture)), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=1, profile=profile)
        system.vector_db.collection.count.return_value = 0
        await system.chat(
            "explain recursion",
            memory_context="Student previously abandoned recursion.",
        )

    assert "Student previously abandoned recursion." in captured[0]
