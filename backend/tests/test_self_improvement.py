"""
Tests for Phase 3: analytics tracker, feedback loop, quiz-explanation
quality link, and nightly scheduler logic.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call
from datetime import datetime, timedelta
from bson import ObjectId


# ── analytics.track ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_track_inserts_event():
    from app.services.analytics_service import track, QUESTION_ASKED
    db = MagicMock()
    db.analytics_events = MagicMock()
    db.analytics_events.insert_one = AsyncMock()

    await track(db, QUESTION_ASKED, user_id="u1", properties={"subject": "DSA"})

    db.analytics_events.insert_one.assert_called_once()
    doc = db.analytics_events.insert_one.call_args[0][0]
    assert doc["event"] == QUESTION_ASKED
    assert doc["user_id"] == "u1"
    assert doc["properties"]["subject"] == "DSA"
    assert "created_at" in doc


@pytest.mark.asyncio
async def test_track_never_raises_on_db_error():
    from app.services.analytics_service import track, USER_SIGNED_UP
    db = MagicMock()
    db.analytics_events = MagicMock()
    db.analytics_events.insert_one = AsyncMock(side_effect=Exception("DB down"))

    # Should not raise
    await track(db, USER_SIGNED_UP, user_id="u1")


@pytest.mark.asyncio
async def test_track_works_without_properties():
    from app.services.analytics_service import track, ROADMAP_GENERATED
    db = MagicMock()
    db.analytics_events = MagicMock()
    db.analytics_events.insert_one = AsyncMock()

    await track(db, ROADMAP_GENERATED, user_id="u1")
    doc = db.analytics_events.insert_one.call_args[0][0]
    assert doc["properties"] == {}


# ── Nightly scheduler logic ───────────────────────────────────────────────────

def _make_db_for_scheduler(users=None, events=None, analytics=None):
    db = MagicMock()

    # users collection
    db.users.find = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=users or []))
    )
    db.users.update_one = AsyncMock()

    # learning_events
    db.learning_events.find = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=events or []))
    )

    # analytics_events (for roadmap age)
    db.analytics_events.find_one = AsyncMock(return_value=analytics)

    return db


@pytest.mark.asyncio
async def test_nightly_no_active_users_does_nothing():
    from app.services.scheduler_service import _run_improvement_pass
    db = _make_db_for_scheduler(users=[])
    await _run_improvement_pass(db)
    db.users.update_one.assert_not_called()


@pytest.mark.asyncio
async def test_nightly_high_frustration_sets_easier_difficulty():
    from app.services.scheduler_service import _run_improvement_pass
    oid = ObjectId()
    user = {"_id": oid, "last_active": datetime.utcnow(), "current_subject": "DSA",
            "subjects": {"DSA": {}}}
    # 8 frustrated out of 10 = 80%
    events = [
        {"emotion": "frustrated", "type": "chat", "created_at": datetime.utcnow()}
    ] * 8 + [
        {"emotion": "neutral", "type": "chat", "created_at": datetime.utcnow()}
    ] * 2

    db = _make_db_for_scheduler(users=[user], events=events)
    await _run_improvement_pass(db)

    db.users.update_one.assert_called_once()
    update_args = db.users.update_one.call_args[0][1]
    assert update_args["$set"]["auto_difficulty_override"] == "easier"


@pytest.mark.asyncio
async def test_nightly_low_frustration_clears_override():
    from app.services.scheduler_service import _run_improvement_pass
    oid = ObjectId()
    user = {
        "_id": oid, "last_active": datetime.utcnow(),
        "current_subject": "DSA", "subjects": {"DSA": {}},
        "auto_difficulty_override": "easier",  # was set before
    }
    # Only 1 frustrated out of 20 = 5% → clear override
    events = [
        {"emotion": "frustrated", "type": "chat", "created_at": datetime.utcnow()}
    ] + [
        {"emotion": "neutral", "type": "chat", "created_at": datetime.utcnow()}
    ] * 19

    db = _make_db_for_scheduler(users=[user], events=events)
    await _run_improvement_pass(db)

    update_args = db.users.update_one.call_args[0][1]
    assert update_args["$set"]["auto_difficulty_override"] is None


@pytest.mark.asyncio
async def test_nightly_stale_roadmap_flagged():
    from app.services.scheduler_service import _run_improvement_pass
    oid = ObjectId()
    user = {
        "_id": oid, "last_active": datetime.utcnow(),
        "current_subject": "DSA",
        "subjects": {"DSA": {"roadmap": [{"module": "Intro"}]}},
    }
    old_event = {
        "event": "roadmap_generated",
        "created_at": datetime.utcnow() - timedelta(days=20),
    }
    db = _make_db_for_scheduler(users=[user], events=[], analytics=old_event)
    await _run_improvement_pass(db)

    update_args = db.users.update_one.call_args[0][1]
    assert update_args["$set"]["subjects.DSA.roadmap_stale"] is True


@pytest.mark.asyncio
async def test_nightly_fresh_roadmap_not_flagged():
    from app.services.scheduler_service import _run_improvement_pass
    oid = ObjectId()
    user = {
        "_id": oid, "last_active": datetime.utcnow(),
        "current_subject": "DSA",
        "subjects": {"DSA": {"roadmap": [{"module": "Intro"}]}},
    }
    recent_event = {
        "event": "roadmap_generated",
        "created_at": datetime.utcnow() - timedelta(days=3),
    }
    db = _make_db_for_scheduler(users=[user], events=[], analytics=recent_event)
    await _run_improvement_pass(db)

    # No stale flag — update_one may still be called for other reasons but
    # roadmap_stale should not be set to True
    if db.users.update_one.called:
        update_args = db.users.update_one.call_args[0][1]
        assert update_args["$set"].get("subjects.DSA.roadmap_stale") is not True


@pytest.mark.asyncio
async def test_nightly_error_in_one_user_does_not_stop_others():
    from app.services.scheduler_service import _run_improvement_pass
    oid1, oid2 = ObjectId(), ObjectId()
    users = [
        {"_id": oid1, "last_active": datetime.utcnow(), "current_subject": "DSA",
         "subjects": {"DSA": {}}},
        {"_id": oid2, "last_active": datetime.utcnow(), "current_subject": "ML",
         "subjects": {"ML": {}}},
    ]
    db = _make_db_for_scheduler(users=users, events=[])
    # Make the first user's learning_events query fail
    call_count = 0
    original = db.learning_events.find

    def side_effect(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise Exception("simulated DB error")
        return original(*args, **kwargs)

    db.learning_events.find = side_effect

    # Should not raise even though user 1 errored
    await _run_improvement_pass(db)


# ── Scheduler start/stop ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_start_scheduler_returns_running_scheduler():
    from app.services.scheduler_service import start_scheduler, stop_scheduler
    db = MagicMock()
    sched = start_scheduler(db)
    assert sched.running
    stop_scheduler()


@pytest.mark.asyncio
async def test_stop_scheduler_is_idempotent():
    from app.services.scheduler_service import stop_scheduler
    stop_scheduler()  # already stopped — should not raise
    stop_scheduler()
