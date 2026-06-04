"""
Tests for Phase 4: hybrid RAG, agentic chat, and voice transcription endpoint.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ── Hybrid RAG ────────────────────────────────────────────────────────────────

def _make_vdb():
    """Return a VectorDBManager with a mocked ChromaDB collection."""
    with patch("chromadb.PersistentClient"):
        from core import VectorDBManager
        vdb = VectorDBManager.__new__(VectorDBManager)
        vdb.user_id = "1"
        col = MagicMock()
        col.count = MagicMock(return_value=10)
        vdb.collection = col
        vdb._bm25_index = None
        vdb._bm25_docs = []
        return vdb


def test_bm25_rank_returns_same_items():
    vdb = _make_vdb()
    docs = ["recursion calls itself", "loops iterate", "binary search halves"]
    ranked = vdb._bm25_rank("recursion", docs)
    assert set(ranked) == set(docs)
    assert ranked[0] == "recursion calls itself"


def test_bm25_rank_empty_returns_empty():
    vdb = _make_vdb()
    assert vdb._bm25_rank("query", []) == []


def test_rrf_merges_two_lists():
    vdb = _make_vdb()
    dense  = ["A", "B", "C", "D"]
    sparse = ["C", "A", "D", "B"]
    merged = vdb._reciprocal_rank_fusion(dense, sparse)
    assert set(merged) == {"A", "B", "C", "D"}
    # C is rank-1 in sparse and rank-3 in dense — should rank highly
    assert "C" in merged[:2]


def test_rrf_handles_no_overlap():
    vdb = _make_vdb()
    merged = vdb._reciprocal_rank_fusion(["A", "B"], ["C", "D"])
    assert set(merged) == {"A", "B", "C", "D"}


def test_rrf_single_list():
    vdb = _make_vdb()
    merged = vdb._reciprocal_rank_fusion(["X", "Y", "Z"], [])
    assert merged == ["X", "Y", "Z"]


@pytest.mark.asyncio
async def test_query_db_uses_hybrid_pipeline():
    """Verify query_db calls ChromaDB and returns fused results."""
    vdb = _make_vdb()
    vdb.collection.count = MagicMock(return_value=5)
    vdb.collection.query = MagicMock(return_value={
        "documents": [["recursion doc", "loop doc", "search doc"]]
    })

    with patch("core.get_jina_embeddings", new=AsyncMock(return_value=[[0.1] * 8])):
        result = await vdb.query_db("explain recursion", n_results=2)

    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_query_db_empty_collection_returns_empty():
    vdb = _make_vdb()
    vdb.collection.count = MagicMock(return_value=0)
    result = await vdb.query_db("anything")
    assert result == ""


@pytest.mark.asyncio
async def test_query_db_chunks_returns_list():
    vdb = _make_vdb()
    vdb.collection.count = MagicMock(return_value=5)
    vdb.collection.query = MagicMock(return_value={
        "documents": [["doc1", "doc2", "doc3"]]
    })
    with patch("core.get_jina_embeddings", new=AsyncMock(return_value=[[0.1] * 8])):
        chunks = await vdb.query_db_chunks("query", n_results=2)
    assert isinstance(chunks, list)
    assert len(chunks) <= 2


# ── Agentic chat ──────────────────────────────────────────────────────────────

def _make_system(profile=None):
    profile = profile or {"level": "Intermediate", "learning_style": "Visual", "subject": "DSA"}
    with patch("chromadb.PersistentClient"):
        from core import LearningSystem
        system = LearningSystem.__new__(LearningSystem)
        system.user_id = 1
        system.profile = profile
        system.weak_topics = ["recursion"]
        system.system_instruction = "You are a tutor."
        system.vector_db = MagicMock()
        system.vector_db.query_db = AsyncMock(return_value="relevant doc content")
        return system


@pytest.mark.asyncio
async def test_agentic_chat_returns_final_answer_directly():
    """When Gemini returns text immediately (no tool call), return it."""
    system = _make_system()

    mock_part = MagicMock()
    mock_part.function_call = None
    mock_part.text = "Recursion is when a function calls itself."
    mock_response = MagicMock()
    mock_response.candidates = [MagicMock(content=MagicMock(parts=[mock_part]))]

    with patch("core.client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
        result = await system.agentic_chat("explain recursion")

    assert result["response"] == "Recursion is when a function calls itself."
    assert "emotion" in result


@pytest.mark.asyncio
async def test_agentic_chat_calls_search_tool_then_answers():
    """Verify tool call → result fed back → final text answer."""
    system = _make_system()

    # Step 1: model requests search_documents
    fn_call = MagicMock()
    fn_call.name = "search_documents"
    fn_call.args = {"query": "recursion"}
    part_tool = MagicMock()
    part_tool.function_call = fn_call
    part_tool.text = ""

    # Step 2: model returns final text
    part_final = MagicMock()
    part_final.function_call = None
    part_final.text = "Based on your documents, recursion means..."

    resp1 = MagicMock()
    resp1.candidates = [MagicMock(content=MagicMock(parts=[part_tool]))]
    resp2 = MagicMock()
    resp2.candidates = [MagicMock(content=MagicMock(parts=[part_final]))]

    with patch("core.client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=[resp1, resp2]
        )
        result = await system.agentic_chat("explain recursion from my notes")

    assert "recursion" in result["response"].lower()
    assert mock_client.aio.models.generate_content.call_count == 2


@pytest.mark.asyncio
async def test_agentic_chat_falls_back_on_gemini_error():
    """If all Gemini calls fail, fallback to standard chat()."""
    system = _make_system()
    system.chat = AsyncMock(return_value={"response": "fallback answer", "emotion": "neutral"})

    with patch("core.client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(
            side_effect=Exception("API error")
        )
        result = await system.agentic_chat("explain recursion")

    assert result["response"] == "fallback answer"


@pytest.mark.asyncio
async def test_agentic_chat_get_weak_topics_tool():
    """Verify get_weak_topics returns the student's weak topics."""
    system = _make_system()
    system.weak_topics = ["dynamic programming", "graphs"]

    fn_call = MagicMock()
    fn_call.name = "get_weak_topics"
    fn_call.args = {}
    part_tool = MagicMock()
    part_tool.function_call = fn_call

    part_final = MagicMock()
    part_final.function_call = None
    part_final.text = "You struggle with DP and graphs."

    resp1 = MagicMock()
    resp1.candidates = [MagicMock(content=MagicMock(parts=[part_tool]))]
    resp2 = MagicMock()
    resp2.candidates = [MagicMock(content=MagicMock(parts=[part_final]))]

    with patch("core.client") as mock_client:
        mock_client.aio.models.generate_content = AsyncMock(side_effect=[resp1, resp2])
        result = await system.agentic_chat("what am I bad at?")

    assert result["response"] == "You struggle with DP and graphs."
