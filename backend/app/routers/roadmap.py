import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.limiter import limiter
from app.db.mongo import db
from app.dependencies.auth import get_current_active_user
from app.repositories import users as users_repo
from app.services.analytics_service import track, ROADMAP_GENERATED
from app.services.session_manager import get_learning_session

logger = logging.getLogger(__name__)

router = APIRouter(tags=["roadmap"])


@router.post("/generate_roadmap")
@limiter.limit("10/minute")
async def generate_roadmap(request: Request, current_user: dict = Depends(get_current_active_user)):
    session = await get_learning_session(current_user)
    subject = current_user.get("current_subject", "general")

    try:
        roadmap = await session.generate_roadmap()

        # Store roadmap scoped to the active subject so each subject
        # gets its own learning path.
        await users_repo.apply_update(
            current_user["_id"],
            {"$set": {f"subjects.{subject}.roadmap": roadmap}},
        )

        await track(db, ROADMAP_GENERATED, user_id=str(current_user["_id"]), properties={
            "subject": subject,
            "steps": len(roadmap),
        })

        logger.info("Roadmap generated for user %s subject=%s", str(current_user["_id"]), subject)
        return {"roadmap": roadmap}
    except Exception as e:
        # Log the real exception server-side; never echo raw internal error
        # text back to the client (Sprint 2 Task 4 - was
        # `detail=f"Error generating roadmap: {e}"`).
        logger.error("Roadmap generation failed for user %s: %s", str(current_user["_id"]), e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error generating roadmap")


@router.get("/roadmap")
async def get_roadmap(current_user: dict = Depends(get_current_active_user)):
    subject = current_user.get("current_subject", "general")
    user_doc = await users_repo.find_by_object_id(current_user["_id"])
    if not user_doc:
        return {"roadmap": None}

    # Subject-scoped roadmap first; fall back to legacy root-level roadmap
    # for existing users who generated a roadmap before this change.
    roadmap = (
        user_doc.get("subjects", {}).get(subject, {}).get("roadmap")
        or user_doc.get("roadmap")
    )
    return {"roadmap": roadmap or None}
