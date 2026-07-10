import logging
import os
import shutil
import uuid
from datetime import datetime

from bson import ObjectId
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pypdf import PdfReader

from app.core.limiter import limiter
from app.db.mongo import db
from app.dependencies.auth import get_current_active_user
from app.repositories import documents as documents_repo
from app.services.analytics_service import track, DOCUMENT_UPLOADED
from app.services.session_manager import get_learning_session
from app.utils.pdf import extract_text_from_pdf, sanitize_filename

logger = logging.getLogger(__name__)

router = APIRouter(tags=["documents"])


@router.post("/upload_pdf")
@limiter.limit("5/minute")
async def upload_pdf(
    request: Request,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_active_user),
):
    session = await get_learning_session(current_user)

    safe_filename = sanitize_filename(file.filename)
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
        full_text = extract_text_from_pdf(reader)

        if not full_text:
            raise HTTPException(
                status_code=400,
                detail="Could not extract text from PDF"
            )

        result = await session.vector_db.add_document(full_text, safe_filename)

        if result["status"] == "error":
            raise HTTPException(status_code=500, detail=result["message"])

        await documents_repo.insert_document({
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
    except MemoryError:
        logger.error("PDF processing OOM: %s (size=%d)", safe_filename, file_size)
        raise HTTPException(status_code=413, detail="PDF too large to process")
    except Exception as e:
        logger.error("PDF processing failed: %s — %s", safe_filename, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Error processing PDF")
    finally:
        if os.path.exists(file_location):
            os.remove(file_location)


@router.get("/documents")
async def get_documents(
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_active_user),
):
    limit = min(limit, 100)   # cap at 100 regardless of client request
    user_id = str(current_user["_id"])
    docs = await documents_repo.find_for_user(user_id, skip, limit)

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


@router.delete("/documents/{doc_id}")
async def delete_document(
    doc_id: str,
    current_user: dict = Depends(get_current_active_user),
):
    try:
        oid = ObjectId(doc_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid document ID")

    doc = await documents_repo.find_owned(oid, str(current_user["_id"]))

    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    session = await get_learning_session(current_user)
    removed = session.vector_db.delete_document(doc["filename"])

    await documents_repo.delete_by_id(oid)

    return {"message": "Document deleted", "chunks_removed": removed}
