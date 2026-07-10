from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from app.services.session_manager import active_sessions

router = APIRouter()

_DIST_INDEX = Path(__file__).parent.parent.parent.parent / "frontend" / "dist" / "index.html"


@router.get("/", response_class=HTMLResponse)
async def serve_frontend():
    if _DIST_INDEX.exists():
        return HTMLResponse(content=_DIST_INDEX.read_text(encoding="utf-8"))
    return HTMLResponse(content="<h1>Dev mode — run <code>cd frontend && npm run build</code> or use <a href='http://localhost:5173'>http://localhost:5173</a></h1>")


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "active_sessions": len(active_sessions),
        "version": "2.0.0"
    }
