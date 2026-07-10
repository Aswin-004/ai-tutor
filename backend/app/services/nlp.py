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
    logger.info("nlp: loaded en_core_web_sm")
except OSError:
    nlp = spacy.blank("en")
    logger.warning(
        "nlp: en_core_web_sm not found, using blank model. "
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


# ── Emotion detection ─────────────────────────────────────────────────────────

_FRUSTRATION_SIGNALS = {
    "dont get", "don't get", "doesn't make sense", "makes no sense",
    "i give up", "this is hard", "i dont understand", "don't understand",
    "still confused", "no idea", "stuck",
    "not getting it", "ugh", "why is this", "what even", "skip this",
    "this sucks", "too hard", "impossible", "never mind", "forget it",
}
_CONFIDENCE_SIGNALS = {
    "i think i get it", "oh i see", "that makes sense", "makes sense now",
    "got it", "i understand", "now i get", "oh wait", "i figured",
    "so basically", "so that means", "ah okay", "i see so",
}
_EXCITEMENT_SIGNALS = {
    "this is cool", "that's amazing", "wow", "oh wow", "so interesting",
    "can we do more", "tell me more", "i want to learn", "love this",
}
_DISENGAGED_SIGNALS = {
    "ok", "okay", "k", "sure", "fine", "yeah", "yep", "mm", "hmm", "whatever",
}


def detect_emotion(message: str) -> str:
    """Detect the student's emotional state from their message.

    Returns one of: frustrated | confused | confident | excited | disengaged | neutral

    Rules are checked in priority order — frustration beats confusion beats excitement.
    Message length is used as a secondary signal: very short messages suggest disengagement.
    """
    text = message.lower().strip()
    word_count = len(text.split())

    # Frustration — highest priority, needs immediate tone shift
    if any(sig in text for sig in _FRUSTRATION_SIGNALS):
        return "frustrated"

    # Confusion — similar to frustration but milder; try a different explanation
    confusion_words = {
        "confused", "confusing", "confuse", "unclear", "huh", "what?",
        "i don't follow", "dont follow", "lost me", "what do you mean",
        "so confused", "am confused", "getting confused",
    }
    if any(w in text for w in confusion_words):
        return "confused"

    # Confidence / breakthrough
    if any(sig in text for sig in _CONFIDENCE_SIGNALS):
        return "confident"

    # Excitement
    if any(sig in text for sig in _EXCITEMENT_SIGNALS) or text.count("!") >= 2:
        return "excited"

    # Disengaged — very short replies or known filler words
    if word_count <= 3 and text in _DISENGAGED_SIGNALS:
        return "disengaged"

    # Very short message (1-2 words) with no content = likely disengaged
    if word_count <= 2 and not any(sig in text for sig in _CONFIDENCE_SIGNALS):
        return "disengaged"

    return "neutral"


# Tone instructions injected into the Gemini prompt based on detected emotion.
EMOTION_TONE_GUIDE: dict[str, str] = {
    "frustrated": (
        "IMPORTANT — Student is frustrated right now. "
        "Do NOT repeat the same explanation. "
        "Acknowledge briefly ('That's a tough one, let's try a different angle'), "
        "then use a completely different analogy or real-world example. "
        "Keep the response SHORT — 3-4 sentences max. No walls of text."
    ),
    "confused": (
        "Student is confused. Slow down. "
        "Break your explanation into numbered steps. "
        "Use a concrete, everyday analogy before any technical terms. "
        "End with one simple check question to see if they followed."
    ),
    "confident": (
        "Student is getting it — they're in a good zone. "
        "You can go slightly deeper or introduce the next logical concept. "
        "Acknowledge their progress naturally ('Exactly right — now here's where it gets interesting')."
    ),
    "excited": (
        "Student is excited and engaged. Match their energy. "
        "Be enthusiastic, go a little deeper, connect to something even more interesting. "
        "Ask a follow-up question to keep the momentum going."
    ),
    "disengaged": (
        "Student seems disengaged or bored. "
        "Do NOT give a long response. "
        "Ask one short, interesting question or share one surprising fact related to the topic. "
        "Make it interactive — get them talking again."
    ),
}
