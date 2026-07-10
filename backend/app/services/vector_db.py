"""ChromaDB-backed vector store: chunking, Jina embeddings, and hybrid
(dense cosine + BM25 sparse, merged via Reciprocal Rank Fusion) retrieval.
"""

import re
import logging
from typing import Dict, List, Optional, Tuple

import chromadb
import httpx

from app.core.config import JINA_API_KEY

logger = logging.getLogger(__name__)


async def get_jina_embeddings(texts: List[str], task: str) -> List[List[float]]:
    """Get embeddings from Jina AI API (non-blocking)."""
    url = "https://api.jina.ai/v1/embeddings"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {JINA_API_KEY}"
    }
    data = {
        "model": "jina-embeddings-v3",
        "task": task,
        "input": texts
    }

    try:
        async with httpx.AsyncClient(timeout=30) as http_client:
            response = await http_client.post(url, headers=headers, json=data)
            response.raise_for_status()
            return [item["embedding"] for item in response.json()["data"]]
    except httpx.HTTPError as e:
        logger.error("Jina API error: %s", e)
        return []


def _parse_pages(text: str) -> List[Tuple[int, str]]:
    """Split text on [Page N] markers produced by the PDF extractor.
    Returns list of (page_number, page_text) tuples.
    Falls back to [(1, text)] when no markers are present."""
    parts = re.split(r'\[Page (\d+)\]\n?', text)
    # parts = [pre_content, page_num_str, content, page_num_str, content, ...]
    pages: List[Tuple[int, str]] = []
    i = 1
    while i < len(parts) - 1:
        try:
            page_num = int(parts[i])
            page_text = parts[i + 1].strip()
            if page_text:
                pages.append((page_num, page_text))
        except (ValueError, IndexError):
            pass
        i += 2
    return pages if pages else [(1, text.strip())]


def _chunk_text(text: str, max_size: int = 900) -> List[str]:
    """Split text on paragraph boundaries; merge small paragraphs; hard-split oversized ones."""
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: List[str] = []
    current = ""

    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + 2 + len(para) <= max_size:
            current = current + "\n\n" + para
        else:
            chunks.append(current)
            current = para

    if current:
        chunks.append(current)

    # Hard-split any chunk that still exceeds max_size (e.g. single dense paragraph)
    final: List[str] = []
    for chunk in chunks:
        if len(chunk) <= max_size:
            final.append(chunk)
        else:
            for i in range(0, len(chunk), max_size):
                part = chunk[i:i + max_size].strip()
                if part:
                    final.append(part)

    return final


class VectorDBManager:
    """Manages ChromaDB vector database for document storage and retrieval."""

    def __init__(self, user_id: int):
        self.user_id = str(user_id)
        self.chroma_client = chromadb.PersistentClient(path="./chroma_db")
        collection_name = f"user_{self.user_id}"
        self.collection = self.chroma_client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"}
        )
        # BM25 index cache — invalidated when documents are added or removed
        self._bm25_index = None
        self._bm25_docs: List[str] = []

    async def add_document(self, text: str, source: str) -> Dict:
        """Chunk and embed a document into the vector database."""
        text = text.strip()
        if not text:
            return {"status": "error", "message": "Empty document", "chunks_added": 0}

        # Split into pages first so each chunk carries its page number
        pages = _parse_pages(text)
        page_chunks: List[Tuple[str, int]] = []
        for page_num, page_text in pages:
            for chunk in _chunk_text(page_text):
                page_chunks.append((chunk, page_num))

        if not page_chunks:
            return {"status": "error", "message": "No valid chunks created", "chunks_added": 0}

        chunks = [c for c, _ in page_chunks]

        logger.info("Embedding %d chunks via Jina", len(chunks))
        embeddings = await get_jina_embeddings(chunks, task="retrieval.passage")

        if not embeddings:
            return {"status": "error", "message": "Failed to generate embeddings", "chunks_added": 0}

        ids = [f"{source}_{self.user_id}_{i}" for i in range(len(chunks))]
        metadatas = [
            {
                "source": source,
                "filename": source,
                "user_id": self.user_id,
                "chunk_index": i,
                "page_number": page_num,
            }
            for i, (_, page_num) in enumerate(page_chunks)
        ]

        self.collection.upsert(
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
            ids=ids
        )
        self._invalidate_bm25()

        return {"status": "success", "chunks_added": len(chunks)}

    def _invalidate_bm25(self) -> None:
        """Clear cached BM25 index when the collection changes."""
        self._bm25_index = None
        self._bm25_docs = []

    def _bm25_rank(self, query: str, candidates: List[str]) -> List[str]:
        """Rank candidates by BM25 score. Uses a cached index when possible."""
        try:
            from rank_bm25 import BM25Okapi
        except ImportError:
            return candidates

        if not candidates:
            return candidates

        # Rebuild index only when the candidate set has changed
        if self._bm25_index is None or self._bm25_docs != candidates:
            tokenized = [doc.lower().split() for doc in candidates]
            self._bm25_index = BM25Okapi(tokenized)
            self._bm25_docs = candidates[:]

        scores = self._bm25_index.get_scores(query.lower().split())
        ranked = sorted(zip(candidates, scores), key=lambda x: x[1], reverse=True)
        return [doc for doc, _ in ranked]

    def _reciprocal_rank_fusion(
        self,
        dense_list: List[str],
        sparse_list: List[str],
        k: int = 60,
    ) -> List[str]:
        """Merge two ranked lists using Reciprocal Rank Fusion (RRF).

        Each document gets score = Σ 1/(rank + k) across both lists.
        Higher score = more relevant in the merged ranking.
        """
        scores: dict = {}
        for rank, doc in enumerate(dense_list):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (rank + k)
        for rank, doc in enumerate(sparse_list):
            scores[doc] = scores.get(doc, 0.0) + 1.0 / (rank + k)
        return sorted(scores, key=lambda d: scores[d], reverse=True)

    async def query_db(self, query: str, n_results: Optional[int] = None) -> str:
        """Hybrid retrieval: cosine similarity (dense) + BM25 (sparse), merged via RRF.

        n_results=None → auto-select: 3 for short queries, 6 for long ones.
        Pass an explicit int to override (e.g. 5 for roadmap generation).
        """
        col_size = self.collection.count()   # called once per query
        if col_size == 0:
            return ""

        if n_results is None:
            n_results = 3 if len(query) < 50 else 6

        pool = min(n_results * 3, col_size)

        query_embeddings = await get_jina_embeddings([query], task="retrieval.query")
        if not query_embeddings:
            return ""

        # Dense retrieval — cosine similarity via ChromaDB
        results = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=pool,
        )
        if not (results and results["documents"] and results["documents"][0]):
            return ""

        dense_ranked = results["documents"][0]

        # Sparse retrieval — BM25 over the same dense pool
        sparse_ranked = self._bm25_rank(query, dense_ranked)

        # Merge with RRF and take top-k
        fused = self._reciprocal_rank_fusion(dense_ranked, sparse_ranked)
        selected = fused[:n_results]

        logger.info(
            "hybrid_rag: dense=%d sparse=%d fused=%d selected=%d",
            len(dense_ranked), len(sparse_ranked), len(fused), len(selected),
        )
        return "\n\n---\n\n".join(selected)

    async def query_db_chunks(self, query: str, n_results: int) -> List[str]:
        """Hybrid chunk retrieval — returns top-n chunks via RRF.

        n_results is required; the caller decides the pool size.
        """
        col_size = self.collection.count()   # called once per query
        if col_size == 0:
            return []

        pool = min(n_results + 3, col_size)
        query_embeddings = await get_jina_embeddings([query], task="retrieval.query")
        if not query_embeddings:
            return []

        results = self.collection.query(
            query_embeddings=query_embeddings,
            n_results=pool,
        )
        if not (results and results["documents"] and results["documents"][0]):
            return []

        dense_ranked = results["documents"][0]
        sparse_ranked = self._bm25_rank(query, dense_ranked)
        fused = self._reciprocal_rank_fusion(dense_ranked, sparse_ranked)
        return fused[:n_results]

    def delete_document(self, filename: str) -> int:
        """Delete all vector chunks belonging to a document. Returns count removed."""
        try:
            existing = self.collection.get(where={"source": filename})
            ids_to_delete = existing.get("ids", [])
            if ids_to_delete:
                self.collection.delete(ids=ids_to_delete)
                self._invalidate_bm25()
            return len(ids_to_delete)
        except Exception as e:
            logger.error("VectorDB delete error: %s", e)
            return 0

    def get_stats(self) -> Dict:
        """Get database statistics."""
        return {
            "total_chunks": self.collection.count(),
            "collection_name": self.collection.name
        }

    def clear(self):
        """Clear all documents from the collection."""
        if self.collection.count() > 0:
            all_ids = self.collection.get()["ids"]
            if all_ids:
                self.collection.delete(ids=all_ids)
