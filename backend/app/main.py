import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import ALLOWED_ORIGINS
from app.core.limiter import limiter
from app.core.logging import configure_logging
from app.db.mongo import db, init_indexes
from app.routers import analytics, auth, chat, documents, misc, public, quiz, roadmap, voice
from app.services.scheduler_service import start_scheduler, stop_scheduler
from app.services.session_manager import active_sessions

configure_logging()
logger = logging.getLogger(__name__)


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


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all safety net: log the full traceback server-side, never leak
    raw internal exception text to the client. HTTPException (and
    RateLimitExceeded, registered above) has its own more-specific handler
    and is never routed through here — this only fires for genuinely
    unhandled errors."""
    logger.error("Unhandled exception on %s %s: %s", request.method, request.url.path, exc, exc_info=True)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# CORS middleware — set ALLOWED_ORIGINS env var to comma-separated list for production
# (validated at import time in app.core.config: refuses to start with localhost
# in ALLOWED_ORIGINS when ENVIRONMENT=production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Serve React static assets (JS/CSS/images) from the built dist folder
_DIST_ASSETS = Path(__file__).parent.parent.parent / "frontend" / "dist" / "assets"
if _DIST_ASSETS.exists():
    app.mount("/assets", StaticFiles(directory=str(_DIST_ASSETS)), name="assets")

app.include_router(public.router)
app.include_router(auth.router)
app.include_router(chat.router)
app.include_router(voice.router)
app.include_router(documents.router)
app.include_router(quiz.router)
app.include_router(roadmap.router)
app.include_router(analytics.router)
app.include_router(misc.router)
