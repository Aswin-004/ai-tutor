"""
Unit tests for core.py — pure helper functions and mocked async methods.

Pure functions (no I/O): _chunk_text, _parse_pages, _is_math_context,
    should_generate_diagram, _resolve_tutor_mode.

Async with mocks: LearningSystem.generate_roadmap — mocks out Gemini
    (safe_generate) and ChromaDB so no real API calls are made.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from core import (
    _chunk_text,
    _parse_pages,
    _is_math_context,
    should_generate_diagram,
    _resolve_tutor_mode,
    TutorMode,
    LearningSystem,
)


# ── _parse_pages ─────────────────────────────────────────────────────────────

def test_parse_pages_with_markers():
    text = "[Page 1]\nFirst page\n\n[Page 2]\nSecond page"
    pages = _parse_pages(text)
    assert len(pages) == 2
    assert pages[0] == (1, "First page")
    assert pages[1] == (2, "Second page")


def test_parse_pages_no_markers_returns_single():
    text = "Plain text without page markers"
    pages = _parse_pages(text)
    assert len(pages) == 1
    assert pages[0][0] == 1
    assert pages[0][1] == text.strip()


def test_parse_pages_skips_empty_pages():
    text = "[Page 1]\n\n[Page 2]\nContent here"
    pages = _parse_pages(text)
    # Page 1 is empty → skipped
    assert all(content for _, content in pages)


# ── _chunk_text ───────────────────────────────────────────────────────────────

def test_chunk_text_respects_max_size():
    # Single paragraph under limit — should come back as-is
    para = "Short paragraph."
    chunks = _chunk_text(para, max_size=900)
    assert chunks == [para]


def test_chunk_text_merges_small_paragraphs():
    text = "A.\n\nB.\n\nC."
    chunks = _chunk_text(text, max_size=900)
    assert len(chunks) == 1
    assert "A." in chunks[0]


def test_chunk_text_hard_splits_oversized_paragraph():
    long_para = "x" * 1800
    chunks = _chunk_text(long_para, max_size=900)
    assert len(chunks) == 2
    for c in chunks:
        assert len(c) <= 900


def test_chunk_text_empty_returns_empty():
    assert _chunk_text("") == []


def test_chunk_text_multiple_large_paragraphs():
    text = "\n\n".join(["word " * 200] * 3)
    chunks = _chunk_text(text, max_size=900)
    for c in chunks:
        assert len(c) <= 900


# ── _is_math_context ─────────────────────────────────────────────────────────

def test_is_math_context_math_subject():
    assert _is_math_context("calculus", "explain derivatives")


def test_is_math_context_math_keyword_in_query():
    assert _is_math_context("general", "solve this integral")


def test_is_math_context_matrix_keyword():
    assert _is_math_context("linear algebra", "find the determinant")


def test_is_math_context_not_math():
    assert not _is_math_context("history", "explain the French Revolution")


# ── should_generate_diagram ──────────────────────────────────────────────────

def test_diagram_explicit_request_keyword():
    assert should_generate_diagram("general", "draw a flowchart for this process")


def test_diagram_dsa_subject():
    assert should_generate_diagram("dsa", "explain BFS traversal")


def test_diagram_algorithmic_context_keyword():
    assert should_generate_diagram("programming", "show the recursion tree")


def test_diagram_not_needed_for_simple_question():
    assert not should_generate_diagram("history", "who was Napoleon?")


# ── _resolve_tutor_mode ───────────────────────────────────────────────────────

def test_mode_math_no_context_is_direct():
    mode = _resolve_tutor_mode("calculus", "solve x+1=0", "question", has_context=False)
    assert mode == TutorMode.DIRECT_TEACHING


def test_mode_math_with_context_is_hybrid():
    mode = _resolve_tutor_mode("math", "explain integrals", "question", has_context=True)
    assert mode == TutorMode.HYBRID


def test_mode_no_context_non_math_is_direct():
    mode = _resolve_tutor_mode("history", "who was Napoleon", "question", has_context=False)
    assert mode == TutorMode.DIRECT_TEACHING


def test_mode_revision_intent_is_contextual_rag():
    mode = _resolve_tutor_mode("programming", "revise sorting algorithms", "revision", has_context=True)
    assert mode == TutorMode.CONTEXTUAL_RAG


def test_mode_comparison_intent_is_contextual_rag():
    mode = _resolve_tutor_mode("ml", "compare these two models", "comparison", has_context=True)
    assert mode == TutorMode.CONTEXTUAL_RAG


def test_mode_default_with_context_is_hybrid():
    mode = _resolve_tutor_mode("programming", "explain recursion", "question", has_context=True)
    assert mode == TutorMode.HYBRID


# ── LearningSystem.generate_roadmap ──────────────────────────────────────────

def _make_roadmap_json(n: int = 1) -> str:
    return json.dumps([
        {
            "module": f"Module {i}",
            "topic": f"Topic {i}",
            "objectives": ["obj"],
            "time": "1 hour",
            "difficulty": "Beginner",
            "activities": ["act"],
        }
        for i in range(n)
    ])


@pytest.mark.asyncio
async def test_generate_roadmap_returns_list():
    profile = {"level": "Beginner", "learning_style": "Visual", "subject": "Python"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(return_value=_make_roadmap_json(5))), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=1, profile=profile)
        result = await system.generate_roadmap()
    assert isinstance(result, list)
    assert result[0]["module"] == "Module 0"


@pytest.mark.asyncio
async def test_generate_roadmap_beginner_gets_5_steps_in_prompt():
    captured = []

    async def capture(client, model, prompt):
        captured.append(prompt)
        return _make_roadmap_json(5)

    profile = {"level": "Beginner", "learning_style": "Visual", "subject": "Python"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(side_effect=capture)), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=2, profile=profile)
        await system.generate_roadmap()

    assert "5-step" in captured[0]


@pytest.mark.asyncio
async def test_generate_roadmap_advanced_gets_9_steps_in_prompt():
    captured = []

    async def capture(client, model, prompt):
        captured.append(prompt)
        return _make_roadmap_json(9)

    profile = {"level": "Advanced", "learning_style": "Reading", "subject": "ML"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(side_effect=capture)), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=3, profile=profile)
        await system.generate_roadmap()

    assert "9-step" in captured[0]


@pytest.mark.asyncio
async def test_generate_roadmap_practical_style_in_prompt():
    captured = []

    async def capture(client, model, prompt):
        captured.append(prompt)
        return _make_roadmap_json(7)

    profile = {"level": "Intermediate", "learning_style": "Practical", "subject": "DSA"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(side_effect=capture)), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=4, profile=profile)
        await system.generate_roadmap()

    assert "hands-on projects" in captured[0].lower() or "practical" in captured[0].lower()


@pytest.mark.asyncio
async def test_generate_roadmap_includes_weak_topics_in_prompt():
    captured = []

    async def capture(client, model, prompt):
        captured.append(prompt)
        return _make_roadmap_json(7)

    profile = {"level": "Intermediate", "learning_style": "Visual", "subject": "ML"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(side_effect=capture)), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=5, profile=profile)
        system.weak_topics = ["backpropagation", "gradient descent"]
        await system.generate_roadmap()

    assert "backpropagation" in captured[0]


@pytest.mark.asyncio
async def test_generate_roadmap_raises_on_ai_fallback():
    from ai_service import AI_FALLBACK

    profile = {"level": "Intermediate", "learning_style": "Visual", "subject": "Python"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(return_value=AI_FALLBACK)), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=6, profile=profile)
        with pytest.raises(RuntimeError, match="AI service unavailable"):
            await system.generate_roadmap()


@pytest.mark.asyncio
async def test_generate_roadmap_raises_on_invalid_json():
    profile = {"level": "Intermediate", "learning_style": "Visual", "subject": "Python"}
    with patch("chromadb.PersistentClient"), \
         patch("core.safe_generate", new=AsyncMock(return_value="not json at all")), \
         patch("core.get_jina_embeddings", new=AsyncMock(return_value=[])):
        system = LearningSystem(user_id=7, profile=profile)
        with pytest.raises(RuntimeError, match="invalid JSON"):
            await system.generate_roadmap()
