"""PDF text extraction and filename sanitization helpers."""

import logging
import os
from typing import Optional

from pypdf import PdfReader

logger = logging.getLogger(__name__)


def sanitize_filename(filename: Optional[str]) -> str:
    """Strip path components to prevent traversal attacks; default when missing."""
    return os.path.basename(filename or "upload.pdf")


def extract_text_from_pdf(reader: PdfReader) -> str:
    """Extract text from every page, tagging each with a [Page N] marker.

    Pages that fail to extract are skipped (logged, not fatal) so a
    partially-corrupt PDF still yields whatever text is recoverable.
    Returns an empty string if no page yielded any text.
    """
    text_parts = []
    for i, page in enumerate(reader.pages):
        try:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(f"[Page {i+1}]\n{page_text}")
        except Exception as e:
            logger.warning("Could not extract page %d: %s", i + 1, e)
    return "\n\n".join(text_parts)
