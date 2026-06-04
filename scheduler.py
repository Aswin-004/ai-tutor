"""
Nightly self-improvement job.

Runs at 02:00 every night via APScheduler.
For every user active in the last 7 days it:

  1. Rebuilds weak topics from the latest quiz performance
  2. Adjusts difficulty target if frustration rate is high
  3. Marks stale roadmaps for regeneration
  4. Logs a summary so you can see what changed

Attach to the FastAPI lifespan so it starts and stops with the server.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


async def _run_improvement_pass(db) -> None:
    """Core nightly job — runs once per active user."""
    now = datetime.utcnow()
    cutoff = now - timedelta(days=7)

    active_users = await db.users.find(
        {"last_active": {"$gte": cutoff}}
    ).to_list(None)

    if not active_users:
        logger.info("nightly: no active users, nothing to do")
        return

    logger.info("nightly: processing %d active users", len(active_users))
    updated = 0

    for user in active_users:
        user_id = str(user["_id"])
        subject = user.get("current_subject", "general")

        try:
            changes: dict = {}

            # ── 1. Frustration rate check ──────────────────────────────────
            recent_events = await db.learning_events.find({
                "user_id": user_id,
                "type": "chat",
                "created_at": {"$gte": cutoff},
            }).to_list(None)

            if recent_events:
                frustrated = sum(
                    1 for e in recent_events
                    if e.get("emotion") == "frustrated"
                )
                rate = frustrated / len(recent_events)

                if rate > 0.5:
                    changes["auto_difficulty_override"] = "easier"
                    logger.info(
                        "nightly: user=%s frustration=%.0f%% → setting easier difficulty",
                        user_id, rate * 100,
                    )
                elif rate < 0.1 and user.get("auto_difficulty_override") == "easier":
                    changes["auto_difficulty_override"] = None
            elif user.get("auto_difficulty_override") == "easier":
                # No chat events this week — student is no longer actively struggling;
                # clear the override so difficulty resets naturally on next session.
                changes["auto_difficulty_override"] = None

            # ── 2. Stale roadmap check ─────────────────────────────────────
            subject_data = user.get("subjects", {}).get(subject, {})
            roadmap = subject_data.get("roadmap")
            roadmap_age_days = None

            if roadmap:
                last_roadmap_event = await db.analytics_events.find_one(
                    {"user_id": user_id, "event": "roadmap_generated"},
                    sort=[("created_at", -1)],
                )
                if last_roadmap_event:
                    age = (now - last_roadmap_event["created_at"]).days
                    roadmap_age_days = age
                    if age > 14:
                        changes[f"subjects.{subject}.roadmap_stale"] = True
                        logger.info(
                            "nightly: user=%s roadmap is %d days old → flagged stale",
                            user_id, age,
                        )

            # ── 3. Persist changes ─────────────────────────────────────────
            if changes:
                await db.users.update_one(
                    {"_id": user["_id"]},
                    {"$set": {**changes, "nightly_updated_at": now}},
                )
                updated += 1

        except Exception as exc:
            logger.error("nightly: error processing user=%s — %s", user_id, exc)

    logger.info("nightly: complete — %d/%d users updated", updated, len(active_users))


def start_scheduler(db) -> AsyncIOScheduler:
    """Create and start the APScheduler. Call once from FastAPI lifespan."""
    global _scheduler
    _scheduler = AsyncIOScheduler(timezone="UTC")
    _scheduler.add_job(
        _run_improvement_pass,
        trigger="cron",
        hour=2,
        minute=0,
        args=[db],
        id="nightly_improvement",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    _scheduler.start()
    logger.info("scheduler: nightly improvement job scheduled at 02:00 UTC")
    return _scheduler


def stop_scheduler() -> None:
    """Shut down the scheduler gracefully. Call from FastAPI lifespan shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("scheduler: stopped")
