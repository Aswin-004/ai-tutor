"""UserMemoryManager: persistent per-student learning-style/emotion model."""

from typing import Dict, Optional

from app.services.ai_client import client, safe_generate, AI_FALLBACK, MODEL_NAME


class UserMemoryManager:
    """Builds and maintains a persistent model of how a specific student learns.

    Stored in MongoDB `user_models` collection — one document per user,
    updated incrementally so it never resets between sessions.
    """

    def __init__(self, user_id: str, db):
        self.user_id = user_id
        self.db = db

    async def load(self) -> Dict:
        """Return the current user model, or an empty scaffold if first visit."""
        doc = await self.db.user_models.find_one({"user_id": self.user_id})
        return doc or {}

    async def record_emotion(self, emotion: str, topic: Optional[str], subject: str) -> None:
        """Append one emotion data point and keep a rolling window of the last 20."""
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$push": {
                    "recent_emotions": {
                        "$each": [{"emotion": emotion, "topic": topic, "subject": subject}],
                        "$slice": -20,
                    }
                },
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def record_session(self, subject: str, duration_minutes: float) -> None:
        """Update session statistics used to estimate attention span."""
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$inc": {"total_sessions": 1},
                "$push": {
                    "session_durations": {
                        "$each": [round(duration_minutes, 1)],
                        "$slice": -10,
                    }
                },
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def record_dropoff(self, topic: str, subject: str) -> None:
        """Mark a topic the student abandoned mid-session."""
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$addToSet": {"dropoff_topics": {"topic": topic, "subject": subject}},
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def update_style_profile(self, style_text: str) -> None:
        """Persist the Gemini-generated communication style summary."""
        from datetime import datetime
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$set": {
                    "style_profile": style_text,
                    "style_updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def build_style_profile(self, messages: list) -> str:
        """Ask Gemini to describe this student's communication style.

        Only runs when >= 20 messages are available and the profile is either
        missing or older than 7 days.  Returns the cached profile otherwise.
        """
        from datetime import datetime, timedelta

        if len(messages) < 20:
            return ""

        doc = await self.load()
        last_updated = doc.get("style_updated_at")
        if last_updated and (datetime.utcnow() - last_updated).days < 7:
            return doc.get("style_profile", "")

        # Scan ALL passed messages for user turns so alternating conversation
        # history doesn't starve the sample (bug: [:20] slice + role filter
        # could yield < 10 user messages from a 30-msg window).
        sample = [m["message"] for m in messages if m.get("role") == "user"]
        if len(sample) < 8:
            return ""

        prompt = (
            "Analyze these messages from one student and describe their "
            "communication style in exactly 3 short bullet points.\n"
            "Focus on: tone (formal/casual), vocabulary level, how they "
            "express confusion or excitement.\n\n"
            "Messages:\n" + "\n".join(f"- {m}" for m in sample[:15]) +
            "\n\nOutput 3 bullet points only. No intro sentence."
        )

        style = await safe_generate(client, MODEL_NAME, prompt)
        if style and style != AI_FALLBACK:
            await self.update_style_profile(style)
            return style
        return ""

    def frustration_summary(self, model: Dict) -> str:
        """Return a short prompt block describing the student's frustration pattern."""
        emotions = model.get("recent_emotions", [])
        if not emotions:
            return ""

        frustrated = [e for e in emotions if e.get("emotion") == "frustrated"]
        if not frustrated:
            return ""

        topics = [e["topic"] for e in frustrated if e.get("topic")]
        rate = len(frustrated) / len(emotions)

        lines = [f"STUDENT MEMORY — frustration rate: {rate:.0%} of recent messages"]
        if topics:
            from collections import Counter
            top = [t for t, _ in Counter(topics).most_common(3)]
            lines.append(f"Struggles most with: {', '.join(top)}")
        if rate > 0.5:
            lines.append("Approach carefully — this student frustrates easily. Keep responses short and simple.")
        return "\n".join(lines)

    def dropoff_warning(self, model: Dict, current_topic: Optional[str]) -> str:
        """Warn Gemini if the current topic previously caused the student to give up."""
        if not current_topic:
            return ""
        dropoffs = [d["topic"] for d in model.get("dropoff_topics", [])]
        if current_topic.lower() in [d.lower() for d in dropoffs]:
            return (
                f"⚠️ MEMORY: Student previously abandoned this topic ({current_topic}). "
                "Start from the very basics. Use a different approach than last time."
            )
        return ""
