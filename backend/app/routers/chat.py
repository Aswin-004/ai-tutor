import asyncio
import logging
import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.limiter import limiter
from app.db.mongo import db
from app.dependencies.auth import get_current_active_user
from app.models.subject import subject_data
from app.repositories import chat as chat_repo
from app.repositories import quiz as quiz_repo
from app.repositories import users as users_repo
from app.schemas.chat import ChatRequest
from app.services.analytics_service import track, QUESTION_ASKED
from app.services.decision_engine import decide_next_step
from app.services.session_manager import get_learning_session
from app.services.video_resources import get_video_recommendations

logger = logging.getLogger(__name__)

router = APIRouter(tags=["chat"])


@router.post("/chat")
@limiter.limit("20/minute")
async def chat(
    request: Request,
    body: ChatRequest,
    current_user: dict = Depends(get_current_active_user),
):
    if not body.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    user_id = str(current_user["_id"])
    session = await get_learning_session(current_user)
    subject = current_user.get("current_subject", "general")
    s_data = subject_data(current_user, subject)
    logger.debug(
        "chat user_id=%s subject=%s weak_count=%d prof=%s",
        user_id, subject,
        len(s_data.get("weak_topics", [])),
        s_data.get("proficiency_score", 0),
    )

    recent = await chat_repo.find_recent(user_id, limit=6)
    recent = list(reversed(recent))
    server_history = [f"{m['role']}: {m['message']}" for m in recent]

    try:
        decision = decide_next_step(current_user, s_data)
    except Exception as de_err:
        logger.error("decision engine failed user_id=%s: %s", user_id, de_err)
        decision = {"next_topic": None, "difficulty": "basic", "strategy": "teach"}

    # Normalize to 0-1; thread subject so adaptive/corrective RAG can use it
    decision["proficiency_score"] = s_data.get("proficiency_score", 0) / 100.0
    decision["subject"] = subject

    logger.info(
        "decision user_id=%s topic=%r difficulty=%s strategy=%s tone=%s",
        user_id, decision.get("next_topic"), decision.get("difficulty"),
        decision.get("strategy"), decision.get("tone"),
    )

    try:
        # Infer topic first — needed by memory context below
        last_quiz = await quiz_repo.find_last(user_id)
        chat_topic = last_quiz["topic"] if last_quiz else None
        if not chat_topic:
            _stopwords = {
                "what", "when", "where", "which", "about", "please", "could", "would",
                "should", "explain", "tell", "help", "with", "this", "that", "have",
                "does", "from", "will", "just", "some", "also",
            }
            _words = [w.lower().strip("?.,!") for w in body.message.split()]
            _kw = [w for w in _words if len(w) > 4 and w not in _stopwords]
            chat_topic = _kw[0] if _kw else None

        # Build memory context (drop-off warning needs chat_topic defined above)
        memory_mgr = getattr(session, "memory_mgr", None)
        user_model = getattr(session, "user_model", {})
        memory_context = ""
        if memory_mgr:
            frustration_block = memory_mgr.frustration_summary(user_model)
            dropoff_block = memory_mgr.dropoff_warning(user_model, chat_topic)
            memory_context = "\n".join(filter(None, [frustration_block, dropoff_block]))

        # Agentic mode: env var AGENTIC_CHAT=1 enables tool-calling
        use_agentic = os.getenv("AGENTIC_CHAT", "0") == "1"

        chat_start = datetime.utcnow()
        if use_agentic:
            chat_result = await session.agentic_chat(
                body.message, server_history, decision=decision,
                memory_context=memory_context,
            )
        else:
            chat_result = await session.chat(
                body.message, server_history, decision=decision,
                memory_context=memory_context,
            )
        response = chat_result["response"]
        emotion = chat_result["emotion"]
        now = datetime.utcnow()
        response_time = (now - chat_start).total_seconds()

        try:
            await asyncio.gather(
                db.chat_history.insert_many([
                    {"user_id": user_id, "role": "user", "message": body.message, "created_at": now},
                    {"user_id": user_id, "role": "assistant", "message": response, "created_at": now},
                ]),
                db.learning_events.insert_one({
                    "user_id": user_id,
                    "type": "chat",
                    "topic": chat_topic,
                    "subject": subject,
                    "emotion": emotion,
                    "correctness": None,
                    "response_time": response_time,
                    "created_at": now,
                }),
                users_repo.apply_update(
                    current_user["_id"],
                    {"$inc": {"engagement_score": 1}, "$set": {"last_active": now}},
                ),
            )
        except Exception as gather_err:
            logger.error(
                "chat parallel write failed user_id=%s op=chat_persist: %s",
                user_id, gather_err,
            )

        # Update persistent user memory (fire-and-forget, never blocks the response)
        if memory_mgr:
            try:
                await memory_mgr.record_emotion(emotion, chat_topic, subject)

                # Rebuild style profile once enough messages exist (async, background)
                recent_msgs = await chat_repo.find_recent(user_id, limit=60)
                new_style = await memory_mgr.build_style_profile(list(reversed(recent_msgs)))
                if new_style and new_style != session.profile.get("style_profile"):
                    session.profile["style_profile"] = new_style
                    session.system_instruction = session._build_persona()
            except Exception as mem_err:
                logger.warning("user memory update failed user_id=%s: %s", user_id, mem_err)

        videos = get_video_recommendations(
            s_data.get("weak_topics", []),
            s_data.get("proficiency_score", 0) / 100.0,
        )

        await track(db, QUESTION_ASKED, user_id=user_id, properties={
            "subject": subject,
            "emotion": emotion,
            "topic": chat_topic,
            "response_time_s": round(response_time, 2),
        })

        return {"response": response, "emotion": emotion, "decision": decision, "videos": videos}
    except Exception as e:
        # Log the real exception server-side; never echo raw internal error
        # text back to the client (Sprint 2 Task 4 - was `detail=f"Error: {e}"`).
        logger.error("chat processing failed user_id=%s: %s", user_id, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing chat message")


@router.get("/chat/history")
async def get_chat_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    messages = await chat_repo.find_recent(user_id, limit=limit)
    messages = list(reversed(messages))

    return {
        "messages": [
            {
                "role": msg["role"],
                "message": msg["message"],
                "created_at": msg["created_at"].isoformat()
            }
            for msg in messages
        ]
    }


@router.delete("/chat/history")
async def clear_chat_history(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    await chat_repo.delete_all(user_id)
    return {"message": "Chat history cleared"}
