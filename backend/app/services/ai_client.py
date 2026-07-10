"""Shared Gemini client + resilient async generation wrapper.

Provides a single entry point — safe_generate() — that handles:
  • True async via client.aio (no run_in_executor / thread-pool blocking)
  • Exponential back-off on transient / rate-limit / 503 errors
  • Per-call timeout via asyncio.wait_for
  • A graceful fallback string when all attempts are exhausted
"""

import asyncio
import logging
from typing import Optional

from google import genai

from app.core.config import GOOGLE_API_KEY

logger = logging.getLogger(__name__)

MODEL_NAME = "gemini-2.5-flash"

client = genai.Client(api_key=GOOGLE_API_KEY)

AI_FALLBACK = "I'm sorry, the AI service is temporarily overloaded. Please try again in a moment."

# Substrings that indicate a transient/retryable server-side failure.
_RETRYABLE_SIGNALS = (
    "503",
    "500",
    "429",
    "unavailable",
    "overloaded",
    "quota",
    "rate limit",
    "rate_limit",
    "internal",
    "deadline",
    "timeout",
)


def _is_retryable(exc: Exception) -> bool:
    """Return True when the exception looks like a transient server error."""
    msg = str(exc).lower()
    return any(signal in msg for signal in _RETRYABLE_SIGNALS)


async def safe_generate(
    client: genai.Client,
    model: str,
    contents: str,
    *,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: float = 45.0,
) -> str:
    """Call Gemini with retries, exponential back-off, and a fallback on failure.

    Parameters
    ----------
    client:      An initialised google.genai.Client instance.
    model:       Model name, e.g. "gemini-2.5-flash".
    contents:    The prompt string.
    max_retries: Total attempts before giving up (default 3).
    base_delay:  Seconds for the first back-off window; doubles each retry.
    timeout:     Per-attempt wall-clock limit in seconds.

    Returns
    -------
    The model's response text on success, or AI_FALLBACK if all attempts fail.
    """
    last_exc: Optional[Exception] = None

    for attempt in range(max_retries):
        try:
            response = await asyncio.wait_for(
                client.aio.models.generate_content(model=model, contents=contents),
                timeout=timeout,
            )
            if attempt > 0:
                logger.info(
                    "safe_generate: recovered on attempt %d/%d",
                    attempt + 1,
                    max_retries,
                )
            return response.text.strip()

        except asyncio.TimeoutError as exc:
            last_exc = exc
            logger.warning(
                "safe_generate: timeout (%.0fs) on attempt %d/%d",
                timeout,
                attempt + 1,
                max_retries,
            )

        except Exception as exc:
            last_exc = exc
            if not _is_retryable(exc):
                logger.error(
                    "safe_generate: non-retryable error on attempt %d/%d — %s: %s",
                    attempt + 1,
                    max_retries,
                    type(exc).__name__,
                    exc,
                )
                break
            logger.warning(
                "safe_generate: retryable error on attempt %d/%d — %s: %s",
                attempt + 1,
                max_retries,
                type(exc).__name__,
                exc,
            )

        if attempt < max_retries - 1:
            delay = base_delay * (2 ** attempt)
            logger.info(
                "safe_generate: back-off %.2fs before attempt %d/%d",
                delay,
                attempt + 2,
                max_retries,
            )
            await asyncio.sleep(delay)

    logger.error(
        "safe_generate: all %d attempts exhausted — last_error=%s: %s",
        max_retries,
        type(last_exc).__name__,
        last_exc,
    )
    return AI_FALLBACK
