from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, status, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from typing import Dict, Literal
from datetime import datetime, timedelta
import asyncio
import shutil
import os
import uuid
import logging
from contextlib import asynccontextmanager
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from bson import ObjectId
from pypdf import PdfReader

from mongo import db, init_indexes
from auth import (
    UserCreate, UserLogin, UserResponse, UserProfileUpdate, Token,
    create_access_token, authenticate_user, create_user,
    get_user_by_email, get_user_by_username, update_user_profile,
    change_user_password, get_current_active_user,
    ACCESS_TOKEN_EXPIRE_MINUTES, mongo_user_to_response
)
from core import LearningSystem, UserMemoryManager
from analytics import (
    track,
    USER_SIGNED_UP, DOCUMENT_UPLOADED, QUESTION_ASKED,
    QUIZ_COMPLETED, ROADMAP_GENERATED,
)
from scheduler import start_scheduler, stop_scheduler
from decision_engine import decide_next_step
from video_resources import get_video_recommendations

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)

# Rate limiter — keyed by client IP
limiter = Limiter(key_func=get_remote_address)

# Active learning sessions (in-memory cache)
active_sessions: Dict[str, LearningSystem] = {}
# Tracks when each session was last accessed for TTL eviction
_session_last_access: Dict[str, datetime] = {}
_SESSION_TTL_HOURS = 4


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("AI Tutor API starting up")
    await init_indexes()
    start_scheduler(db)
    yield
    logger.info("AI Tutor API shutting down")
    stop_scheduler()
    active_sessions.clear()


app = FastAPI(
    title="AI Tutor API",
    description="An intelligent tutoring system with authentication and RAG capabilities",
    version="2.0.0",
    lifespan=lifespan
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware — set ALLOWED_ORIGINS env var to comma-separated list for production
_allowed_origins = os.getenv("ALLOWED_ORIGINS", "http://localhost:8000,http://localhost:3000")
ALLOWED_ORIGINS = [o.strip() for o in _allowed_origins.split(",") if o.strip()]
_IS_PRODUCTION = os.getenv("ENVIRONMENT", "development").lower() == "production"

if _IS_PRODUCTION and any("localhost" in o for o in ALLOWED_ORIGINS):
    raise ValueError("localhost must not be in ALLOWED_ORIGINS in production. Set ALLOWED_ORIGINS env var.")

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# Pydantic Models
class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=5000)


class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class QuizGenerateRequest(BaseModel):
    topic: str

class QuizSubmitRequest(BaseModel):
    topic: str
    score: int
    total_questions: int  # required — client must send actual question count


class FeedbackRequest(BaseModel):
    message: str = Field(..., max_length=2000)
    feedback_type: Literal["up", "down"]


class SubjectSwitch(BaseModel):
    subject: str

_VALID_SUBJECTS = {"general", "DSA", "ML", "Math"}

_EMPTY_SUBJECT: Dict = {
    "weak_topics": [],
    "strong_topics": [],
    "proficiency_score": 0,
    "engagement_score": 0,
    "cumulative_score": 0.0,
    "total_attempts": 0,
}


def _subject_data(user: dict, subject: str) -> dict:
    """Return subject-scoped stats with safe defaults for new subjects."""
    return dict(_EMPTY_SUBJECT, **user.get("subjects", {}).get(subject, {}))


def _evict_stale_sessions() -> None:
    """Remove sessions idle longer than _SESSION_TTL_HOURS."""
    cutoff = datetime.utcnow() - timedelta(hours=_SESSION_TTL_HOURS)
    stale = [uid for uid, ts in _session_last_access.items() if ts < cutoff]
    for uid in stale:
        active_sessions.pop(uid, None)
        _session_last_access.pop(uid, None)
    if stale:
        logger.info("evicted %d stale session(s)", len(stale))


# Helper function to get or create learning session
async def get_learning_session(user: dict) -> LearningSystem:
    user_id = str(user["_id"])
    _evict_stale_sessions()
    if user_id not in active_sessions:
        profile = {
            "username": user["username"],
            "full_name": user.get("full_name"),
            "subject": user.get("subject") or "General",
            "level": user.get("level") or "Intermediate",
            "learning_style": user.get("learning_style") or "Visual",
            "goals": user.get("goals") or "Learn effectively",
        }

        # Load persistent user memory and enrich profile
        memory_mgr = UserMemoryManager(user_id, db)
        user_model = await memory_mgr.load()

        if user_model.get("style_profile"):
            profile["style_profile"] = user_model["style_profile"]

        session = LearningSystem(user_id, profile)
        session.memory_mgr = memory_mgr
        session.user_model = user_model

        subject = user.get("current_subject", "general")
        subject_data = _subject_data(user, subject)
        weak_topics = subject_data.get("weak_topics") or user.get("weak_topics")
        if weak_topics:
            session.weak_topics = weak_topics
            session.system_instruction = session._build_persona()
        else:
            all_perf = await db.quiz_performance.find({"user_id": user_id}).to_list(None)
            quiz_data = [
                {"topic": p["topic"], "score": (p["score"] / p["total_questions"]) * 100}
                for p in all_perf if p.get("total_questions", 0) > 0
            ]
            session.update_weak_topics(quiz_data)

        active_sessions[user_id] = session
    _session_last_access[user_id] = datetime.utcnow()
    return active_sessions[user_id]


# ==================== PUBLIC ENDPOINTS ====================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    try:
        with open("index.html", "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    except FileNotFoundError:
        return HTMLResponse(content="<h1>Frontend not found</h1>")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "version": "2.0.0"
    }


# ==================== AUTH ENDPOINTS ====================

@app.post("/auth/register", response_model=Token, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def register(request: Request, user_data: UserCreate):
    if await get_user_by_email(user_data.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    if await get_user_by_username(user_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken"
        )

    user = await create_user(user_data)

    access_token = create_access_token(
        data={"sub": str(user["_id"]), "username": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    await track(db, USER_SIGNED_UP, user_id=str(user["_id"]), properties={
        "username": user["username"],
    })

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=mongo_user_to_response(user)
    )


@app.post("/auth/login", response_model=Token)
@limiter.limit("5/minute")
async def login(request: Request, credentials: UserLogin):
    user = await authenticate_user(credentials.username, credentials.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": str(user["_id"]), "username": user["username"]},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        user=mongo_user_to_response(user)
    )


@app.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: dict = Depends(get_current_active_user)):
    return mongo_user_to_response(current_user)


@app.put("/auth/profile", response_model=UserResponse)
async def update_profile(
    profile: UserProfileUpdate,
    current_user: dict = Depends(get_current_active_user),
):
    updated_user = await update_user_profile(str(current_user["_id"]), profile)

    user_id = str(current_user["_id"])
    if user_id in active_sessions:
        del active_sessions[user_id]
        _session_last_access.pop(user_id, None)

    return mongo_user_to_response(updated_user)


@app.post("/auth/logout")
async def logout(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    if user_id in active_sessions:
        del active_sessions[user_id]
        _session_last_access.pop(user_id, None)
    return {"message": "Logged out successfully"}


@app.post("/auth/change-password")
@limiter.limit("3/minute")
async def change_password(
    request: Request,
    body: PasswordChange,
    current_user: dict = Depends(get_current_active_user),
):
    success = await change_user_password(
        str(current_user["_id"]), body.current_password, body.new_password
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect",
        )
    user_id = str(current_user["_id"])
    if user_id in active_sessions:
        del active_sessions[user_id]
        _session_last_access.pop(user_id, None)
    return {"message": "Password changed successfully"}


# ==================== PROTECTED TUTOR ENDPOINTS ====================

@app.post("/upload_pdf")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    session = await get_learning_session(current_user)

    # Sanitise filename — strip path components to prevent traversal attacks
    safe_filename = os.path.basename(file.filename or "upload.pdf")
    if not safe_filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")

    contents = await file.read()
    file_size = len(contents)

    if file_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File size exceeds 10MB limit")

    await file.seek(0)

    file_location = f"temp_{uuid.uuid4()}.pdf"

    try:
        with open(file_location, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        reader = PdfReader(file_location)
        text_parts = []

        for i, page in enumerate(reader.pages):
            try:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(f"[Page {i+1}]\n{page_text}")
            except Exception as e:
                logger.warning("Could not extract page %d: %s", i + 1, e)

        if not text_parts:
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from PDF"
            )

        full_text = "\n\n".join(text_parts)

        result = await session.vector_db.add_document(full_text, safe_filename)

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        await db.documents.insert_one({
            "user_id": str(current_user["_id"]),
            "filename": safe_filename,
            "file_size": file_size,
            "chunks_count": result.get("chunks_added", 0),
            "uploaded_at": datetime.utcnow(),
        })

        await track(db, DOCUMENT_UPLOADED, user_id=str(current_user["_id"]), properties={
            "filename": safe_filename,
            "pages": len(reader.pages),
            "chunks": result.get("chunks_added", 0),
            "file_size_kb": round(file_size / 1024, 1),
        })

        return {
            "status": "success",
            "filename": safe_filename,
            "pages_processed": len(reader.pages),
            "chunks_added": result.get("chunks_added", 0)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing PDF: {str(e)}")
    finally:
        if os.path.exists(file_location):
            os.remove(file_location)


@app.get("/documents")
async def get_documents(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    docs = await db.documents.find({"user_id": user_id}).sort("uploaded_at", -1).to_list(None)

    return {
        "documents": [
            {
                "id": str(doc["_id"]),
                "filename": doc["filename"],
                "file_size": doc.get("file_size"),
                "chunks_count": doc.get("chunks_count", 0),
                "uploaded_at": doc["uploaded_at"].isoformat()
            }
            for doc in docs
        ]
    }


@app.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    try:
        oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc = await db.documents.find_one({"_id": oid, "user_id": str(current_user["_id"])})

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    session = await get_learning_session(current_user)
    removed = session.vector_db.delete_document(doc["filename"])

    await db.documents.delete_one({"_id": oid})

    return {"message": "Document deleted", "chunks_removed": removed}


@app.post("/generate_roadmap")
@limiter.limit("10/minute")
async def generate_roadmap(request: Request, current_user: dict = Depends(get_current_active_user)):
    session = await get_learning_session(current_user)
    subject = current_user.get("current_subject", "general")

    try:
        roadmap = await session.generate_roadmap()

        # Store roadmap scoped to the active subject so each subject
        # gets its own learning path.
        await db.users.update_one(
            {"_id": current_user["_id"]},
            {"$set": {f"subjects.{subject}.roadmap": roadmap}},
        )

        await track(db, ROADMAP_GENERATED, user_id=str(current_user["_id"]), properties={
            "subject": subject,
            "steps": len(roadmap),
        })

        logger.info("Roadmap generated for user %s subject=%s", str(current_user["_id"]), subject)
        return {"roadmap": roadmap}
    except Exception as e:
        logger.error("Roadmap generation failed for user %s: %s", str(current_user["_id"]), e)
        raise HTTPException(status_code=500, detail=f"Error generating roadmap: {str(e)}")


@app.post("/chat")
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
    subject_data = _subject_data(current_user, subject)
    logger.info(
        "[SUBJECT DEBUG] chat user_id=%s subject=%s weak=%s prof=%s",
        user_id, subject,
        subject_data.get("weak_topics", []),
        subject_data.get("proficiency_score", 0),
    )

    recent = await db.chat_history.find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(6).to_list(None)
    recent = list(reversed(recent))
    server_history = [f"{m['role']}: {m['message']}" for m in recent]

    try:
        decision = decide_next_step(current_user, subject_data)
    except Exception as de_err:
        logger.error("decision engine failed user_id=%s: %s", user_id, de_err)
        decision = {"next_topic": None, "difficulty": "basic", "strategy": "teach"}

    # Normalize to 0-1; thread subject so adaptive/corrective RAG can use it
    decision["proficiency_score"] = subject_data.get("proficiency_score", 0) / 100.0
    decision["subject"] = subject

    logger.info(
        "decision user_id=%s topic=%r difficulty=%s strategy=%s tone=%s",
        user_id, decision.get("next_topic"), decision.get("difficulty"),
        decision.get("strategy"), decision.get("tone"),
    )

    try:
        # Infer topic first — needed by memory context below
        last_quiz = await db.quiz_performance.find_one(
            {"user_id": user_id}, sort=[("created_at", -1)]
        )
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
                db.users.update_one(
                    {"_id": current_user["_id"]},
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
                recent_msgs = await db.chat_history.find(
                    {"user_id": user_id}
                ).sort("created_at", -1).limit(60).to_list(None)
                new_style = await memory_mgr.build_style_profile(list(reversed(recent_msgs)))
                if new_style and new_style != session.profile.get("style_profile"):
                    session.profile["style_profile"] = new_style
                    session.system_instruction = session._build_persona()
            except Exception as mem_err:
                logger.warning("user memory update failed user_id=%s: %s", user_id, mem_err)

        videos = get_video_recommendations(
            subject_data.get("weak_topics", []),
            subject_data.get("proficiency_score", 0) / 100.0,
        )

        await track(db, QUESTION_ASKED, user_id=user_id, properties={
            "subject": subject,
            "emotion": emotion,
            "topic": chat_topic,
            "response_time_s": round(response_time, 2),
        })

        return {"response": response, "emotion": emotion, "decision": decision, "videos": videos}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")


@app.get("/chat/history")
async def get_chat_history(
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    messages = await db.chat_history.find(
        {"user_id": user_id}
    ).sort("created_at", -1).limit(limit).to_list(None)

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


@app.delete("/chat/history")
async def clear_chat_history(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    await db.chat_history.delete_many({"user_id": user_id})
    return {"message": "Chat history cleared"}


@app.get("/stats")
async def get_user_stats(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    docs_count = await db.documents.count_documents({"user_id": user_id})
    messages_count = await db.chat_history.count_documents({"user_id": user_id})

    session = await get_learning_session(current_user)
    db_stats = session.get_db_stats()

    return {
        "documents_count": docs_count,
        "messages_count": messages_count,
        "chunks_count": db_stats.get("total_chunks", 0)
    }


# ==================== QUIZ ENDPOINTS ====================

@app.post("/quiz/generate")
@limiter.limit("10/minute")
async def generate_quiz_endpoint(
    request: Request,
    body: QuizGenerateRequest,
    current_user: dict = Depends(get_current_active_user),
):
    session = await get_learning_session(current_user)
    quiz = await session.generate_quiz(body.topic)
    if not quiz:
        raise HTTPException(status_code=500, detail="Failed to generate quiz")
    return {"quiz": quiz, "total_questions": len(quiz)}


@app.post("/quiz/submit")
@limiter.limit("10/minute")
async def submit_quiz(
    request: Request,
    body: QuizSubmitRequest,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])

    if body.total_questions <= 0:
        raise HTTPException(status_code=400, detail="total_questions must be > 0")
    if body.score < 0 or body.score > body.total_questions:
        raise HTTPException(
            status_code=400,
            detail=f"score must be between 0 and {body.total_questions}",
        )

    subject = current_user.get("current_subject", "general")
    subject_data = _subject_data(current_user, subject)
    logger.info(
        "[SUBJECT DEBUG] quiz_submit user_id=%s subject=%s weak=%s prof=%s",
        user_id, subject,
        subject_data.get("weak_topics", []),
        subject_data.get("proficiency_score", 0),
    )

    await db.quiz_performance.insert_one({
        "user_id": user_id,
        "topic": body.topic,
        "score": body.score,
        "total_questions": body.total_questions,
        "subject": subject,
        "created_at": datetime.utcnow(),
    })

    session = await get_learning_session(current_user)
    # Filter by subject so weak_topics are never mixed across domains
    all_perf = await db.quiz_performance.find(
        {"user_id": user_id, "subject": subject}
    ).to_list(None)
    quiz_data = [
        {"topic": p["topic"], "score": (p["score"] / p["total_questions"]) * 100}
        for p in all_perf if p.get("total_questions", 0) > 0
    ]

    weak_topics = session.update_weak_topics(quiz_data)

    correctness = body.score / body.total_questions if body.total_questions > 0 else 0

    # O(1) incremental proficiency — scoped per subject
    prev_cumulative = subject_data.get("cumulative_score", 0.0)
    prev_attempts = subject_data.get("total_attempts", 0)
    new_cumulative = prev_cumulative + correctness
    new_attempts = prev_attempts + 1
    proficiency_score = round((new_cumulative / new_attempts) * 100, 1)

    now = datetime.utcnow()
    update_op: dict = {
        "$set": {
            f"subjects.{subject}.weak_topics": weak_topics,
            f"subjects.{subject}.proficiency_score": proficiency_score,
            "last_active": now,
        },
        "$inc": {
            f"subjects.{subject}.engagement_score": 1,
            f"subjects.{subject}.cumulative_score": correctness,
            f"subjects.{subject}.total_attempts": 1,
        },
    }
    if correctness > 0.70:
        update_op["$addToSet"] = {f"subjects.{subject}.strong_topics": body.topic}

    try:
        await asyncio.gather(
            db.users.update_one({"_id": current_user["_id"]}, update_op),
            db.learning_events.insert_one({
                "user_id": user_id,
                "type": "quiz",
                "topic": body.topic,
                "subject": subject,
                "correctness": correctness,
                "response_time": None,
                "created_at": now,
            }),
        )
    except Exception as gather_err:
        logger.error(
            "quiz parallel write failed user_id=%s op=quiz_submit: %s",
            user_id, gather_err,
        )

    await track(db, QUIZ_COMPLETED, user_id=user_id, properties={
        "topic": body.topic,
        "subject": subject,
        "score_pct": round(correctness * 100, 1),
        "proficiency_after": proficiency_score,
    })

    # Score < 40% means the preceding explanation didn't land — record it
    if correctness < 0.4:
        last_explanation = await db.chat_history.find_one(
            {"user_id": user_id, "role": "assistant"},
            sort=[("created_at", -1)],
        )
        if last_explanation:
            await db.explanation_failures.insert_one({
                "user_id": user_id,
                "topic": body.topic,
                "subject": subject,
                "explanation": last_explanation["message"][:500],
                "score_pct": round(correctness * 100, 1),
                "source": "quiz",
                "created_at": now,
            })
            logger.info(
                "explanation_failure recorded user=%s topic=%s score=%.0f%%",
                user_id, body.topic, correctness * 100,
            )

    return {"message": "Quiz submitted", "weak_topics": weak_topics}


@app.get("/quiz/weak_topics")
async def get_weak_topics(current_user: dict = Depends(get_current_active_user)):
    session = await get_learning_session(current_user)
    return {"weak_topics": session.weak_topics}


@app.get("/roadmap")
async def get_roadmap(current_user: dict = Depends(get_current_active_user)):
    subject = current_user.get("current_subject", "general")
    user_doc = await db.users.find_one({"_id": current_user["_id"]})
    if not user_doc:
        return {"roadmap": None}

    # Subject-scoped roadmap first; fall back to legacy root-level roadmap
    # for existing users who generated a roadmap before this change.
    roadmap = (
        user_doc.get("subjects", {}).get(subject, {}).get("roadmap")
        or user_doc.get("roadmap")
    )
    return {"roadmap": roadmap or None}


@app.patch("/auth/subject")
async def switch_subject(
    body: SubjectSwitch,
    current_user: dict = Depends(get_current_active_user),
):
    subject = body.subject.strip()
    if subject not in _VALID_SUBJECTS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid subject. Allowed: {', '.join(sorted(_VALID_SUBJECTS))}",
        )

    user_id = str(current_user["_id"])
    if user_id in active_sessions:
        del active_sessions[user_id]
        _session_last_access.pop(user_id, None)

    now = datetime.utcnow()
    update: dict = {"$set": {"current_subject": subject, "last_active": now}}

    if subject not in current_user.get("subjects", {}):
        update["$set"][f"subjects.{subject}"] = {
            "weak_topics": [],
            "strong_topics": [],
            "proficiency_score": 0,
            "engagement_score": 0,
            "cumulative_score": 0.0,
            "total_attempts": 0,
        }

    await db.users.update_one({"_id": current_user["_id"]}, update)
    logger.info("user %s switched subject to %s", user_id, subject)
    return {"subject": subject}


@app.post("/feedback", status_code=status.HTTP_201_CREATED)
async def submit_feedback(
    body: FeedbackRequest,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    subject = current_user.get("current_subject", "general")

    # Fetch the last AI response and the emotion at that time so failures
    # can be analyzed to find patterns in what doesn't work.
    last_ai_msg = await db.chat_history.find_one(
        {"user_id": user_id, "role": "assistant"},
        sort=[("created_at", -1)],
    )
    last_event = await db.learning_events.find_one(
        {"user_id": user_id, "type": "chat"},
        sort=[("created_at", -1)],
    )

    await db.feedback.insert_one({
        "user_id": user_id,
        "message": body.message,
        "feedback_type": body.feedback_type,
        "last_ai_response": last_ai_msg["message"] if last_ai_msg else None,
        "topic": last_event["topic"] if last_event else None,
        "emotion_at_time": last_event["emotion"] if last_event else None,
        "subject": subject,
        "created_at": datetime.utcnow(),
    })

    # If thumbs down — store as a failed explanation for the nightly analyzer
    if body.feedback_type == "down" and last_ai_msg:
        await db.explanation_failures.insert_one({
            "user_id": user_id,
            "topic": last_event["topic"] if last_event else None,
            "subject": subject,
            "explanation": last_ai_msg["message"][:500],
            "emotion_at_time": last_event["emotion"] if last_event else None,
            "created_at": datetime.utcnow(),
        })

    logger.info("Feedback '%s' recorded for user %s", body.feedback_type, user_id)
    return {"message": "Feedback recorded"}


@app.post("/voice/transcribe")
@limiter.limit("10/minute")
async def transcribe_voice(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    """Transcribe a voice recording and detect emotional tone using Gemini.

    Accepts: audio/webm, audio/wav, audio/mp4, audio/ogg (browser MediaRecorder formats).
    Returns: { transcript, tone, emotion }
    """
    ALLOWED_AUDIO = {"audio/webm", "audio/wav", "audio/mp4", "audio/ogg", "audio/mpeg"}
    content_type = file.content_type or ""
    if not any(content_type.startswith(t) for t in ALLOWED_AUDIO):
        raise HTTPException(status_code=400, detail="Unsupported audio format")

    audio_bytes = await file.read()
    if len(audio_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Audio file too large (max 5MB)")
    if len(audio_bytes) < 100:
        raise HTTPException(status_code=400, detail="Audio file too small")

    import base64
    from google.genai import types as genai_types
    from core import client as gemini_client

    audio_b64 = base64.b64encode(audio_bytes).decode()

    prompt = (
        "Listen to this audio and do TWO things:\n"
        "1. Transcribe exactly what was said.\n"
        "2. Describe the speaker's tone in one word: "
        "confident / hesitant / frustrated / excited / neutral\n\n"
        "Respond in this exact format:\n"
        "TRANSCRIPT: <what was said>\n"
        "TONE: <one word>"
    )

    try:
        response = await gemini_client.aio.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                {"role": "user", "parts": [
                    {"inline_data": {"mime_type": content_type, "data": audio_b64}},
                    {"text": prompt},
                ]}
            ],
        )
        raw = response.text.strip()
    except Exception as exc:
        logger.error("voice transcription failed: %s", exc)
        raise HTTPException(status_code=500, detail="Transcription failed")

    # Parse structured response
    transcript, tone = "", "neutral"
    for line in raw.splitlines():
        if line.startswith("TRANSCRIPT:"):
            transcript = line.replace("TRANSCRIPT:", "").strip()
        elif line.startswith("TONE:"):
            tone = line.replace("TONE:", "").strip().lower()

    if not transcript:
        raise HTTPException(status_code=422, detail="Could not transcribe audio")

    # Map Gemini tone → our emotion labels
    tone_to_emotion = {
        "frustrated": "frustrated", "hesitant": "confused",
        "confident": "confident",   "excited": "excited",
        "neutral": "neutral",
    }
    emotion = tone_to_emotion.get(tone, "neutral")

    logger.info(
        "voice: user=%s tone=%s emotion=%s transcript_len=%d",
        str(current_user["_id"]), tone, emotion, len(transcript),
    )
    return {"transcript": transcript, "tone": tone, "emotion": emotion}


@app.post("/heartbeat")
async def heartbeat(current_user: dict = Depends(get_current_active_user)):
    user_id = str(current_user["_id"])
    subject = current_user.get("current_subject", "general")
    now = datetime.utcnow()
    try:
        await asyncio.gather(
            db.users.update_one(
                {"_id": current_user["_id"]},
                {
                    "$set": {"last_active": now},
                    "$inc": {f"subjects.{subject}.engagement_score": 1},
                },
            ),
            db.learning_events.insert_one({
                "type": "heartbeat",
                "user_id": user_id,
                "subject": subject,
                "created_at": now,
            }),
        )
    except Exception as e:
        logger.error("heartbeat write failed user_id=%s: %s", user_id, e)
    logger.info("heartbeat user=%s subject=%s", user_id, subject)
    return {"status": "ok"}


@app.get("/analytics/overview")
async def analytics_overview(
    subject: str = "general",
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    subject_data = _subject_data(current_user, subject)

    proficiency_score = round(subject_data.get("proficiency_score", 0))
    engagement_score = int(subject_data.get("engagement_score", 0))
    weak_topics = subject_data.get("weak_topics", [])

    quizzes_attempted = await db.quiz_performance.count_documents(
        {"user_id": user_id, "subject": subject}
    )

    recent_quizzes = await db.quiz_performance.find(
        {"user_id": user_id, "subject": subject}
    ).sort("created_at", -1).limit(5).to_list(None)

    recent_scores = [
        round((q["score"] / q["total_questions"]) * 100)
        for q in reversed(recent_quizzes)
        if q.get("total_questions", 0) > 0
    ]

    now = datetime.utcnow()
    day_buckets = {
        (now - timedelta(days=4 - i)).strftime("%b %d"): 0
        for i in range(5)
    }

    recent_events = await db.learning_events.find({
        "user_id": user_id,
        "subject": subject,
        "created_at": {"$gte": now - timedelta(days=5)},
    }).to_list(None)

    for ev in recent_events:
        day_key = ev["created_at"].strftime("%b %d")
        if day_key in day_buckets:
            day_buckets[day_key] += 1

    return {
        "proficiency_score": proficiency_score,
        "engagement_score": engagement_score,
        "weak_topics": weak_topics,
        "quizzes_attempted": quizzes_attempted,
        "recent_scores": recent_scores or [0],
        "recent_activity": list(day_buckets.values()),
    }


@app.get("/quiz/history")
async def get_quiz_history(
    subject: str = None,
    current_user: dict = Depends(get_current_active_user),
):
    user_id = str(current_user["_id"])
    active_subject = subject or current_user.get("current_subject", "general")
    performances = await db.quiz_performance.find(
        {"user_id": user_id, "subject": active_subject}
    ).sort("created_at", -1).to_list(None)

    return {
        "history": [
            {
                "id": str(p["_id"]),
                "topic": p["topic"],
                "subject": p.get("subject", active_subject),
                "score": p["score"],
                "total_questions": p["total_questions"],
                "percentage": round((p["score"] / p["total_questions"]) * 100) if p.get("total_questions", 0) > 0 else 0,
                "created_at": p["created_at"].isoformat()
            }
            for p in performances
        ]
    }
