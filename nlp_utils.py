"""Lightweight NLP preprocessing utilities for RAG query enhancement.

No transformer models or heavy ML — pure spaCy rule-based processing.
Falls back gracefully when the small English model is not installed.
"""

from __future__ import annotations

import logging
import re
from typing import List

import spacy

logger = logging.getLogger(__name__)

_FILLER_WORDS = {"please", "can", "could", "would", "tell", "about"}

# Detect math-like queries: operators, known functions, LaTeX signals, solving verbs
_MATH_EXPR_RE = re.compile(
    r'[+\-*/%^]'                                      # arithmetic operators
    r'|\b(sin|cos|tan|cot|sec|csc|log|ln|sqrt|lim|inf|det|div|curl)\b'
    r'|\$\$?|\\frac|\\int|\\sum|\\prod|\\lim',        # LaTeX markers
    re.IGNORECASE,
)
_MATH_PROBLEM_VERBS = {
    "solve", "simplify", "differentiate", "integrate", "calculate",
    "evaluate", "prove", "derive", "compute", "expand", "factor",
    "minimize", "maximize", "find the", "what is the value",
}


def detect_math_query(text: str) -> bool:
    """Return True when the query looks like a direct math problem or calculation."""
    if _MATH_EXPR_RE.search(text):
        return True
    t = text.lower()
    return any(v in t for v in _MATH_PROBLEM_VERBS)


try:
    nlp = spacy.load("en_core_web_sm")
    logger.info("nlp_utils: loaded en_core_web_sm")
except OSError:
    nlp = spacy.blank("en")
    logger.warning(
        "nlp_utils: en_core_web_sm not found, using blank model. "
        "Run: python -m spacy download en_core_web_sm"
    )


def preprocess_query(text: str) -> str:
    """Return a cleaned query string suitable for vector retrieval.

    Steps: lowercase → strip stopwords → strip filler words → keep nouns
    and technical terms (NOUN, PROPN, NUM, ADJ); fall back to all
    non-stop alphabetic tokens if nothing else survives.
    """
    doc = nlp(text.lower())

    # Keep tokens that are content words and not filler
    _KEEP_POS = {"NOUN", "PROPN", "NUM", "ADJ"}
    kept: List[str] = []
    for token in doc:
        if token.is_stop or token.text in _FILLER_WORDS:
            continue
        if not token.is_alpha or len(token.text) < 2:
            continue
        if token.pos_ in _KEEP_POS:
            kept.append(token.text)

    # Fallback: any non-stop alphabetic token
    if not kept:
        kept = [
            token.text
            for token in doc
            if not token.is_stop
            and token.is_alpha
            and len(token.text) > 1
            and token.text not in _FILLER_WORDS
        ]

    return " ".join(kept)


def extract_topics(text: str) -> List[str]:
    """Extract up to 3 key topics from the query using noun chunks and NER.

    Falls back to the longest noun phrase, then to joined non-stop tokens.
    """
    doc = nlp(text)
    seen: set[str] = set()
    topics: List[str] = []

    def _add(candidate: str) -> None:
        normalised = candidate.lower().strip()
        if len(normalised) > 2 and normalised not in seen:
            seen.add(normalised)
            topics.append(normalised)

    for chunk in doc.noun_chunks:
        _add(chunk.text)

    for ent in doc.ents:
        _add(ent.text)

    if not topics:
        # Fallback 1: longest noun chunk
        chunks = [chunk.text for chunk in doc.noun_chunks]
        if chunks:
            _add(max(chunks, key=len))

    if not topics:
        # Fallback 2: join non-stop content tokens into a single pseudo-topic
        non_stop = [
            t.text.lower()
            for t in doc
            if not t.is_stop and t.is_alpha and len(t.text) > 2
        ]
        if non_stop:
            topics.append(" ".join(non_stop[:4]))

    return topics[:3]


def classify_intent(text: str) -> str:
    """Classify query intent without any ML model.

    Returns one of: concept | problem | revision | comparison
    """
    t = text.lower()

    if any(x in t for x in ("what is", "explain", "define")):
        return "concept"
    if any(x in t for x in ("solve", "implement", "example", "code")):
        return "problem"
    if any(x in t for x in ("revise", "summary", "notes")):
        return "revision"
    if any(x in t for x in ("compare", "difference", " vs ")):
        return "comparison"

    return "concept"
