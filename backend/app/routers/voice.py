import base64
import logging

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from app.core.limiter import limiter
from app.dependencies.auth import get_current_active_user
from app.services.ai_client import client as gemini_client

logger = logging.getLogger(__name__)

router = APIRouter(tags=["voice"])


@router.post("/voice/transcribe")
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
