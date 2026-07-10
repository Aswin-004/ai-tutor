import os
import re
import json
import logging
import httpx
from enum import Enum

logger = logging.getLogger(__name__)
import chromadb
import numpy as np
from sklearn.cluster import KMeans
from typing import List, Dict, Optional, Tuple
from google import genai
from dotenv import load_dotenv
from nlp_utils import (
    preprocess_query, extract_topics, classify_intent,
    detect_math_query, detect_emotion, EMOTION_TONE_GUIDE,
)
from ai_service import safe_generate, AI_FALLBACK

load_dotenv()

JINA_API_KEY = os.getenv("JINA_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_NAME = "gemini-2.5-flash"

if not JINA_API_KEY or not GOOGLE_API_KEY:
    raise ValueError("Missing API Keys in .env file")

client = genai.Client(api_key=GOOGLE_API_KEY)

_MATH_SUBJECTS = {
    "math", "mathematics", "calculus", "algebra", "geometry",
    "trigonometry", "statistics", "probability", "linear algebra",
    "number theory", "differential equations",
}
_MATH_KEYWORDS = {
    "equation", "integral", "derivative", "matrix", "polynomial",
    "limit", "series", "vector", "proof", "theorem", "fraction",
    "summation", "eigenvalue", "determinant", "gradient",
}


class TutorMode(str, Enum):
    """Controls how the tutor balances direct teaching vs. document retrieval."""
    DIRECT_TEACHING = "DIRECT_TEACHING"   # teach from expertise; RAG is secondary
    CONTEXTUAL_RAG  = "CONTEXTUAL_RAG"    # document-anchored; for revision/reference
    HYBRID          = "HYBRID"            # teach first, use docs to personalize examples


# Per-subject teaching style injected into the prompt when the subject matches.
_SUBJECT_STYLE_GUIDE: Dict[str, str] = {
    "math": (
        "Show complete step-by-step solutions with LaTeX equations. "
        "Derive formulas from first principles. Never skip intermediate steps."
    ),
    "mathematics": (
        "Show complete step-by-step solutions with LaTeX equations. "
        "Derive formulas from first principles. Never skip intermediate steps."
    ),
    "calculus": (
        "Derive from first principles; show limits, derivatives, and integrals step-by-step in LaTeX."
    ),
    "algebra": (
        "Show each algebraic manipulation step-by-step. Highlight which rule or property is applied."
    ),
    "statistics": (
        "Define variables, state the formula, compute step-by-step, then interpret the result."
    ),
    "probability": (
        "Define the sample space, apply probability rules step-by-step, verify with a concrete example."
    ),
    "dsa": (
        "Lead with intuition, trace through a concrete dry-run example, "
        "then state time and space complexity."
    ),
    "data structures": (
        "Lead with intuition, trace through a concrete dry-run example, "
        "then state time and space complexity."
    ),
    "algorithms": (
        "Explain the core idea, trace a worked example step-by-step, "
        "then state Big-O time and space complexity."
    ),
    "ml": (
        "Explain the intuition first, show the underlying math/equations, "
        "then connect to a practical workflow or real-world example."
    ),
    "machine learning": (
        "Explain the intuition first, show the underlying math/equations, "
        "then connect to a practical workflow or real-world example."
    ),
    "deep learning": (
        "Explain the architecture and training intuition, show relevant equations, "
        "give a concrete layer-by-layer worked example."
    ),
    "ai": (
        "Explain the algorithm intuitively, connect to real-world applications, "
        "show math where relevant."
    ),
    "artificial intelligence": (
        "Explain the algorithm intuitively, connect to real-world applications, "
        "show math where relevant."
    ),
}


def _is_math_context(subject: str, query: str) -> bool:
    """Return True when the active subject or query is mathematical in nature."""
    text = (subject + " " + query).lower()
    return any(kw in text for kw in _MATH_SUBJECTS | _MATH_KEYWORDS)


def format_math_prompt(base_prompt: str) -> str:
    """Append math-specific output format instructions to a prompt."""
    return base_prompt + """

---

MATH RESPONSE FORMAT (required for this query):
- Use LaTeX for ALL mathematical expressions — never plain-text equations.
  Inline math:  \\(expression\\)   e.g. \\(x^2 + y^2 = r^2\\)
  Block/display math: $$expression$$   e.g. $$x = \\frac{-b \\pm \\sqrt{b^2-4ac}}{2a}$$
- Structure your response with these labelled sections when relevant:
  **Concept:** Brief conceptual explanation
  **Formula:** Key formula(s) as LaTeX display math
  **Step-by-Step Solution:**
  Step 1: description → $$expression$$
  Step 2: description → $$expression$$
  **Substitution:** $$values plugged in$$
  **Simplification:** $$simplified expression$$
  **Final Answer:** $$result$$
- LaTeX reference:
  Fraction: \\frac{numerator}{denominator}
  Square root: \\sqrt{expression}
  Power/subscript: x^{n}, x_{i}
  Integral: \\int_{a}^{b} f(x)\\,dx
  Summation: \\sum_{i=1}^{n} a_i
  Limit: \\lim_{x \\to 0} f(x)
  Matrix: \\begin{pmatrix} a & b \\\\ c & d \\end{pmatrix}
- Always show complete step-by-step working — never skip intermediate steps."""


_DIAGRAM_SUBJECTS = {
    "dsa", "data structures", "algorithms",
    "machine learning", "ml", "deep learning",
    "ai", "artificial intelligence",
    "system design", "computer science", "cs", "networking",
}
_DIAGRAM_REQUEST_KEYWORDS = {
    "diagram", "flowchart", "visualize", "visualise", "draw", "illustrate",
}
_DIAGRAM_CONTEXT_KEYWORDS = {
    "algorithm", "pipeline", "architecture", "traversal", "workflow",
    "lifecycle", "process", "step by step", "how does", "how it works",
    "tree", "bfs", "dfs", "sorting", "recursion", "neural network",
    "training", "microservices", "request flow", "data flow",
    "inference", "preprocessing", "deployment flow", "state machine",
    "sequence diagram", "layers", "backpropagation", "decision tree",
}


def should_generate_diagram(subject: str, query: str) -> bool:
    """Return True when a Mermaid diagram would add educational value to the response."""
    sub = subject.lower()
    text = query.lower()

    if any(kw in text for kw in _DIAGRAM_REQUEST_KEYWORDS):
        return True

    if any(s in sub for s in _DIAGRAM_SUBJECTS):
        return True

    if any(kw in text for kw in _DIAGRAM_CONTEXT_KEYWORDS):
        return True

    return False


def format_diagram_prompt(base_prompt: str) -> str:
    """Append Mermaid diagram generation instructions to a prompt."""
    return base_prompt + """

---

DIAGRAM GENERATION GUIDELINES (apply when a visual would aid understanding):
- When explaining algorithms, data structures, workflows, pipelines, or architectures, include one Mermaid diagram.
- Wrap the diagram in a fenced code block with "mermaid" as the language identifier:
  ```mermaid
  graph TD
      A[Start] --> B{Decision?}
      B -->|Yes| C[Result A]
      B -->|No| D[Result B]
  ```
- Diagram type guide:
  - DSA (sorting, traversal, trees): `graph TD` or `graph LR`
  - Sequences/interactions: `sequenceDiagram`
  - ML pipelines / data flows: `graph LR`
  - System/service architecture: `graph TD`
  - State machines: `stateDiagram-v2`
  - Concept maps: `mindmap`
- Rules:
  - Maximum 10-12 nodes — keep it readable and concise.
  - Use descriptive labels (avoid unexplained abbreviations).
  - Place the diagram AFTER the text explanation.
  - Include ONLY ONE diagram per response.
  - Use valid Mermaid syntax; avoid unsupported node shapes.
  - If a diagram would NOT meaningfully improve understanding, omit it."""


def _resolve_tutor_mode(
    subject: str,
    query: str,
    intent: str,
    has_context: bool,
) -> TutorMode:
    """Choose the appropriate tutoring mode for this request.

    Rules (in priority order):
    1. Math subject or math-like query → always teach directly; use docs only for examples.
    2. No uploaded documents → must teach from knowledge.
    3. Revision/comparison intent → the student is asking about their uploaded material.
    4. Everything else with documents → hybrid: teach + personalise with docs.
    """
    sub = subject.lower()

    is_math_sub = any(s in sub for s in _MATH_SUBJECTS)
    if is_math_sub or detect_math_query(query):
        return TutorMode.HYBRID if has_context else TutorMode.DIRECT_TEACHING

    if not has_context:
        return TutorMode.DIRECT_TEACHING

    if intent in ("revision", "comparison"):
        return TutorMode.CONTEXTUAL_RAG

    return TutorMode.HYBRID


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


class LearningSystem:
    """Main AI tutoring system with RAG capabilities."""

    def __init__(self, user_id: int, profile: Dict):
        self.user_id = user_id
        self.profile = profile
        self.vector_db = VectorDBManager(user_id)
        self.weak_topics = []
        self.system_instruction = self._build_persona()

    def update_weak_topics(self, quiz_data: List[Dict]) -> List[str]:
        """Analyze quiz data using K-Means clustering to find weak topics."""
        if not quiz_data:
            self.weak_topics = []
            self.system_instruction = self._build_persona()
            return self.weak_topics

        topic_scores: Dict[str, List[float]] = {}
        for q in quiz_data:
            topic_scores.setdefault(q["topic"], []).append(q["score"])

        avg_scores = {topic: sum(scores) / len(scores) for topic, scores in topic_scores.items()}
        topics = list(avg_scores.keys())
        scores = np.array(list(avg_scores.values())).reshape(-1, 1)

        if len(topics) < 3:
            self.weak_topics = [t for t, s in avg_scores.items() if s < 60]
        else:
            n_clusters = min(3, len(topics))
            # KMeans on < 50 topics takes ~microseconds; sync is acceptable here.
            kmeans = KMeans(n_clusters=n_clusters, n_init="auto", random_state=42)
            kmeans.fit(scores)
            min_cluster_idx = np.argmin(kmeans.cluster_centers_)
            self.weak_topics = [topics[i] for i, label in enumerate(kmeans.labels_) if label == min_cluster_idx]

        self.system_instruction = self._build_persona()
        return self.weak_topics

    def _build_persona(self) -> str:
        """Build the AI tutor's persona based on student profile."""
        name = self.profile.get("full_name") or self.profile.get("username", "Student")
        subject = self.profile.get("subject", "General")
        level = self.profile.get("level", "Intermediate")
        style = self.profile.get("learning_style", "Visual")
        goals = self.profile.get("goals", "Learn effectively")

        weak_topics_str = ""
        if self.weak_topics:
            weak_topics_str = (
                f"KNOWN WEAKNESSES: The student struggles with these topics: "
                f"{', '.join(self.weak_topics)}. "
                f"Explain these topics with extra patience, simple analogies, and foundational reviews.\n"
            )

        style_profile = self.profile.get("style_profile", "")
        style_profile_block = (
            f"\nHOW THIS STUDENT COMMUNICATES:\n{style_profile}\n"
            "Match their vocabulary level and energy in every response.\n"
            if style_profile else ""
        )

        return f"""You are a friendly and expert AI Tutor specialized in {subject}.

STUDENT PROFILE:
- Name: {name}
- Subject: {subject}
- Level: {level}
- Learning Style: {style}
- Goals: {goals}

{weak_topics_str}{style_profile_block}TEACHING GUIDELINES:
1. Adapt explanations to the student's {level} level
2. Use {style.lower()} learning techniques (diagrams descriptions, examples, analogies)
3. Be encouraging and supportive
4. Break complex topics into digestible parts
5. Use the provided reference material when available to enrich examples and terminology
6. If you don't know something, admit it honestly
7. Ask clarifying questions when needed
8. Provide practical examples and exercises when appropriate
9. NEVER say a topic is "outside the syllabus", "not covered in the material", or "outside our scope" — you are an expert tutor with broad knowledge; always teach directly.
10. Uploaded documents are supplementary context — your expert knowledge is always the primary teaching source.
11. If retrieval context is weak or absent, teach from your knowledge without mentioning the absence.

Always address the student by name ({name}) to make the interaction personal."""

    async def generate_roadmap(self) -> List[Dict]:
        """Generate a personalized learning roadmap."""
        context = await self.vector_db.query_db("course overview syllabus topics", n_results=5)

        level = self.profile.get("level", "Intermediate")
        step_count = {"Beginner": 5, "Intermediate": 7, "Advanced": 9}.get(level, 7)

        style = self.profile.get("learning_style", "Visual")
        style_hints = {
            "Visual":     "Use diagram descriptions, visual analogies, and multimedia references (videos, infographics).",
            "Practical":  "Emphasise hands-on projects, coding exercises, and real-world applications.",
            "Reading":    "Reference articles, notes, and written explanations as primary resources.",
        }.get(style, "Use clear explanations with varied examples.")

        weak_topics_prompt = ""
        if self.weak_topics:
            weak_topics_prompt = (
                f"NOTE: The student currently struggles with these topics: {', '.join(self.weak_topics)}. "
                f"Prioritize foundational review and extra time for these areas.\n"
            )

        prompt = f"""You are a Curriculum Designer creating a personalized learning path.

STUDENT PROFILE:
{json.dumps(self.profile, indent=2)}

LEARNING STYLE GUIDANCE: {style_hints}

{weak_topics_prompt}
AVAILABLE COURSE MATERIAL:
{context[:5000] if context else "No specific material uploaded yet. Create a general roadmap based on the subject."}

TASK: Create a structured {step_count}-step learning roadmap for this student (exactly {step_count} steps, matched to their {level} level).

OUTPUT FORMAT (JSON array only, no markdown):
[
    {{
        "title": "Module Title",
        "description": "Specific topic description",
        "objectives": ["objective 1", "objective 2"],
        "time": "Estimated time (e.g., 2 hours)",
        "difficulty": "Beginner | Intermediate | Advanced",
        "activities": ["activity 1", "activity 2"]
    }}
]

Respond with ONLY the JSON array, no additional text or markdown formatting."""

        text = await safe_generate(client, MODEL_NAME, prompt)
        if text == AI_FALLBACK:
            raise RuntimeError("AI service unavailable; cannot generate roadmap. Please try again.")

        text = text.replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Gemini returned invalid JSON for roadmap: {e}") from e

        if isinstance(data, dict):
            for value in data.values():
                if isinstance(value, list):
                    data = value
                    break

        if not isinstance(data, list):
            raise RuntimeError("Gemini roadmap response was not a JSON array")

        # Assign a reliable sequential step number ourselves — trusting the model
        # to number steps correctly is unnecessary risk when enumerate() is free.
        # Also normalize legacy "module"/"topic" keys so an older-shaped response
        # (or a stray non-conforming one) still renders correctly.
        for i, step in enumerate(data, start=1):
            step["step"] = i
            if "title" not in step and "module" in step:
                step["title"] = step.pop("module")
            if "description" not in step and "topic" in step:
                step["description"] = step.pop("topic")

        return data

    # ------------------------------------------------------------------
    # chat() helpers
    # ------------------------------------------------------------------

    async def _resolve_rag_context(
        self,
        query: str,
        clean_query: str,
        topics: List[str],
        intent: str,
        decision: Optional[Dict],
    ) -> str:
        """Retrieve and rank document chunks relevant to the query.

        Uses ChromaDB cosine similarity (primary sort) plus a lightweight
        keyword-overlap boost (tiebreaker).  No LLM call — fully deterministic.
        """
        # Adaptive k: more chunks for complex or high-proficiency queries
        k = 3
        if intent == "problem":
            k = 5
        elif intent == "comparison":
            k = 6
        proficiency = (decision or {}).get("proficiency_score", 0)
        if proficiency > 0.7:
            k = max(k, 6)

        # Topic-aware search query scoped to the active subject
        subject = (decision or {}).get("subject", "general")
        topic_str = " ".join(topics)
        if self.weak_topics:
            focus_topic = self.weak_topics[0]
            search_query = f"{subject} {focus_topic} {topic_str} {clean_query}"
        else:
            focus_topic = None
            search_query = f"{subject} {topic_str} {clean_query}"

        logger.info(
            "adaptive_rag: intent=%s k=%d topic=%s search_query=%r",
            intent, k, focus_topic, search_query,
        )

        # Retrieve expanded pool; ChromaDB returns results in cosine-similarity order
        raw_chunks = await self.vector_db.query_db_chunks(search_query, n_results=k + 3)

        if not raw_chunks:
            return ""

        # Keyword-overlap boost: stable-sort preserves cosine order for ties
        if len(raw_chunks) > k:
            query_words = set(query.lower().split())
            reranked = sorted(
                raw_chunks,
                key=lambda c: len(query_words & set(c.lower().split())),
                reverse=True,
            )
            selected = reranked[:k]
        else:
            selected = raw_chunks

        logger.info(
            "rag_context: selected %d/%d chunks (cosine + keyword, no LLM)",
            len(selected), len(raw_chunks),
        )
        return "\n\n---\n\n".join(selected)

    def _build_prompt(
        self,
        query: str,
        context: str,
        history: List[str],
        decision: Optional[Dict],
        *,
        mode: TutorMode = TutorMode.HYBRID,
        emotion: str = "neutral",
        memory_context: str = "",
    ) -> str:
        """Assemble the full Gemini prompt, shaped by tutor mode and subject."""
        subject = self.profile.get("subject", "General")
        proficiency = (decision or {}).get("proficiency_score", 0)

        if proficiency < 0.4:
            difficulty_instruction = "Explain in very simple terms with step-by-step clarity."
        elif proficiency < 0.7:
            difficulty_instruction = "Explain clearly with examples."
        else:
            difficulty_instruction = "Provide a concise explanation with deeper insights."

        history_str = "\n".join(history[-6:]) if history else ""

        # ── Adaptive tutoring block (unchanged logic) ──────────────────────
        adaptive_block = ""
        if decision:
            topic = decision.get("next_topic")
            difficulty = decision.get("difficulty", "basic")
            strategy = decision.get("strategy", "teach")
            strategy_guide = {
                "teach":     "Explain clearly with simple language, step-by-step breakdowns, and beginner-friendly analogies.",
                "revise":    "Summarize key points and reinforce understanding with brief examples.",
                "challenge": "Ask probing questions to test the student's depth of understanding.",
            }.get(strategy, "")
            focus_prefix = (
                f"Focus on improving the student's understanding of: {topic}\n"
                if strategy != "challenge" and topic else ""
            )
            tone = decision.get("tone", "neutral")
            tone_instruction = {
                "supportive": "Be encouraging, simple, and patient.",
                "challenging": "Challenge the user with deeper questions.",
                "re-engage":  "Briefly recap and gently bring the user back.",
            }.get(tone, "Maintain a clear teaching style.")
            adaptive_block = (
                f"\n---\n\nADAPTIVE TUTORING:\n"
                f"{focus_prefix}"
                f"Topic: {topic or 'General'} | Difficulty: {difficulty} | Strategy: {strategy}\n"
                f"{strategy_guide}\n"
                f"(Use the student's question as context, but steer toward the above approach.)"
                f"\nTone: {tone}\n{tone_instruction}\n"
            )

        # ── Long-term memory context ────────────────────────────────────────
        memory_block = f"\nLONG-TERM MEMORY:\n{memory_context}\n" if memory_context else ""

        # ── Emotion-aware tone override ─────────────────────────────────────
        emotion_block = ""
        if emotion and emotion != "neutral":
            tone_guide = EMOTION_TONE_GUIDE.get(emotion, "")
            if tone_guide:
                emotion_block = f"\nEMOTION DETECTED — {emotion.upper()}:\n{tone_guide}\n"

        # ── Subject style guide ─────────────────────────────────────────────
        style_hint = _SUBJECT_STYLE_GUIDE.get(subject.lower(), "")
        style_block = f"\nSUBJECT STYLE ({subject}): {style_hint}\n" if style_hint else ""

        # ── Mode-specific framing ───────────────────────────────────────────
        if mode == TutorMode.DIRECT_TEACHING:
            mode_header = (
                "TEACHING MODE: Direct instruction\n"
                "Teach this concept completely from your expert knowledge. "
                "Do not deflect or redirect. Your expertise covers all topics in this subject."
            )
            context_section = (
                f"SUPPLEMENTARY MATERIAL (use only to personalise examples — not a constraint):\n{context}"
                if context else
                "No uploaded documents — teach entirely from expert knowledge."
            )
            closing = (
                f"Provide a complete, direct educational answer. "
                f"Never say this topic is outside the syllabus or uploaded material. "
                f"You are an expert tutor for {subject}."
            )

        elif mode == TutorMode.CONTEXTUAL_RAG:
            mode_header = (
                "TEACHING MODE: Document-guided instruction\n"
                "The student is asking about their uploaded study material. "
                "Anchor your answer to the reference documents, and supplement with expert knowledge where needed."
            )
            context_section = (
                f"REFERENCE MATERIAL FROM UPLOADED DOCUMENTS:\n{context}"
                if context else
                "No uploaded documents found — use your expert knowledge instead."
            )
            closing = (
                "Answer using the reference material as your primary source. "
                "Fill any gaps with your expert knowledge. Never refuse to answer."
            )

        else:  # HYBRID (default)
            mode_header = (
                "TEACHING MODE: Educational-first, document-enhanced\n"
                "Teach this concept directly and completely from your expertise. "
                "Use the uploaded material to personalise examples, terminology, and context — "
                "but it does NOT limit what you can teach."
            )
            context_section = (
                f"REFERENCE MATERIAL (for personalising examples and terminology):\n{context}"
                if context else
                "No uploaded documents — teach from expert knowledge."
            )
            closing = (
                f"Teach the concept completely. Use reference material to align examples with the student's course. "
                f"Never deflect, never say the topic is out of scope. "
                f"You are an expert tutor with full knowledge of {subject}."
            )

        prompt = f"""{self.system_instruction}
DIFFICULTY GUIDANCE: {difficulty_instruction}{memory_block}{emotion_block}{style_block}{adaptive_block}
{mode_header}

---

{context_section}

---

CONVERSATION HISTORY:
{history_str if history_str else "This is the start of the conversation."}

---

STUDENT'S QUESTION: {query}

---

{closing}"""
        if _is_math_context(subject, query):
            prompt = format_math_prompt(prompt)
        if should_generate_diagram(subject, query):
            prompt = format_diagram_prompt(prompt)
        return prompt

    async def _generate_response(self, prompt: str) -> str:
        """Call safe_generate and return the model text or the fallback string."""
        return await safe_generate(client, MODEL_NAME, prompt)

    async def chat(self, query: str, history: List[str] = None, decision: Optional[Dict] = None, memory_context: str = "") -> dict:
        """Process a chat message with adaptive RAG context.

        Returns a dict with 'response' (str) and 'emotion' (str) so callers
        can store the detected emotion alongside the message.
        """
        clean_query = preprocess_query(query)
        topics = extract_topics(query)
        intent = classify_intent(query)
        emotion = detect_emotion(query)

        logger.info(
            "NLP intent=%s emotion=%s topics=%s clean_query=%s",
            intent, emotion, topics, clean_query,
        )

        context = await self._resolve_rag_context(query, clean_query, topics, intent, decision)

        mode = _resolve_tutor_mode(
            subject=self.profile.get("subject", ""),
            query=query,
            intent=intent,
            has_context=bool(context),
        )
        logger.info("tutor_mode=%s has_context=%s", mode.value, bool(context))

        prompt = self._build_prompt(
            query, context, history or [], decision,
            mode=mode, emotion=emotion, memory_context=memory_context,
        )
        response = await self._generate_response(prompt)
        return {"response": response, "emotion": emotion}

    async def agentic_chat(
        self,
        query: str,
        history: List[str] = None,
        decision: Optional[Dict] = None,
        memory_context: str = "",
    ) -> dict:
        """Agentic chat using Gemini native function-calling.

        Gemini decides which tools to call before answering:
          - search_documents(query)  — retrieves relevant chunks from ChromaDB
          - get_weak_topics()        — returns the student's current weak areas
          - get_quiz_summary()       — returns recent quiz performance

        Falls back to standard chat() if tool-calling fails.
        Returns same shape as chat(): {response, emotion}
        """
        from google.genai import types as genai_types

        emotion = detect_emotion(query)

        tool_declarations = [
            genai_types.FunctionDeclaration(
                name="search_documents",
                description=(
                    "Search the student's uploaded study materials for relevant content. "
                    "Use this when the question relates to uploaded documents or specific course material."
                ),
                parameters=genai_types.Schema(
                    type="OBJECT",
                    properties={
                        "query": genai_types.Schema(
                            type="STRING",
                            description="What to search for in the documents",
                        )
                    },
                    required=["query"],
                ),
            ),
            genai_types.FunctionDeclaration(
                name="get_weak_topics",
                description=(
                    "Get the list of topics this student is currently struggling with. "
                    "Use this to tailor explanations toward known weak areas."
                ),
                parameters=genai_types.Schema(type="OBJECT", properties={}),
            ),
            genai_types.FunctionDeclaration(
                name="get_quiz_summary",
                description=(
                    "Get a short summary of the student's recent quiz performance. "
                    "Use this when the student asks about their progress or when you need "
                    "to calibrate difficulty."
                ),
                parameters=genai_types.Schema(type="OBJECT", properties={}),
            ),
        ]

        tools = [genai_types.Tool(function_declarations=tool_declarations)]

        # ── Build initial system + user message ────────────────────────────
        emotion_block = ""
        if emotion != "neutral":
            tone_guide = EMOTION_TONE_GUIDE.get(emotion, "")
            if tone_guide:
                emotion_block = f"\nEMOTION — {emotion.upper()}: {tone_guide}\n"

        memory_block = f"\nLONG-TERM MEMORY:\n{memory_context}\n" if memory_context else ""
        history_str = "\n".join((history or [])[-6:])

        system_prompt = (
            f"{self.system_instruction}"
            f"{memory_block}{emotion_block}\n"
            "You have tools available. Use them when they would genuinely improve your answer. "
            "Do not call tools for simple greetings or questions you can answer from expertise alone."
        )

        messages = [
            {"role": "user", "parts": [{"text": f"{system_prompt}\n\n"
                                                  f"CONVERSATION:\n{history_str}\n\n"
                                                  f"STUDENT: {query}"}]}
        ]

        # ── Agentic loop — max 3 tool calls ────────────────────────────────
        for step in range(3):
            try:
                response = await client.aio.models.generate_content(
                    model=MODEL_NAME,
                    contents=messages,
                    config=genai_types.GenerateContentConfig(
                        tools=tools,
                        tool_config=genai_types.ToolConfig(
                            function_calling_config=genai_types.FunctionCallingConfig(
                                mode="AUTO"
                            )
                        ),
                    ),
                )
            except Exception as exc:
                logger.warning("agentic_chat: tool call failed step=%d — %s", step, exc)
                break

            part = response.candidates[0].content.parts[0] if response.candidates else None
            if part is None:
                break

            # Check for function call
            fn = getattr(part, "function_call", None)
            if fn is None:
                # Final answer
                final_text = getattr(part, "text", "").strip()
                if final_text:
                    logger.info("agentic_chat: completed in %d step(s)", step + 1)
                    return {"response": final_text, "emotion": emotion}
                break

            # Execute the tool
            logger.info("agentic_chat: step=%d calling tool=%s", step, fn.name)
            tool_result = ""
            if fn.name == "search_documents":
                search_q = fn.args.get("query", query)
                tool_result = await self.vector_db.query_db(search_q, n_results=5)
                tool_result = tool_result or "No relevant documents found."
            elif fn.name == "get_weak_topics":
                tool_result = (
                    f"Weak topics: {', '.join(self.weak_topics)}"
                    if self.weak_topics else "No weak topics identified yet."
                )
            elif fn.name == "get_quiz_summary":
                tool_result = (
                    f"Student has {len(self.weak_topics)} identified weak area(s): "
                    f"{', '.join(self.weak_topics) or 'none'}. "
                    f"Proficiency level: {self.profile.get('level', 'Intermediate')}."
                )

            # Feed result back to the model
            messages.append({"role": "model", "parts": [part]})
            messages.append({
                "role": "user",
                "parts": [{
                    "function_response": {
                        "name": fn.name,
                        "response": {"result": tool_result},
                    }
                }],
            })

        # ── Fallback to standard chat ───────────────────────────────────────
        logger.warning("agentic_chat: falling back to standard chat()")
        return await self.chat(query, history, decision, memory_context)

    async def generate_quiz(self, topic: str) -> List[Dict]:
        """Generate a dynamic multiple-choice quiz using Gemini."""
        context = await self.vector_db.query_db(topic, n_results=3)

        prompt = f"""You are an expert AI Tutor. Create a 3-question multiple-choice quiz on the topic: "{topic}".

Level: {self.profile.get('level', 'Intermediate')}

REFERENCE MATERIAL:
{context if context else "Use your general knowledge."}

Format the output EXACTLY as a JSON array of objects, with no extra text or markdown format:
[
  {{
    "question": "Question text here",
    "options": ["Option A", "Option B", "Option C", "Option D"],
    "correct_answer": "Option A",
    "explanation": "One or two sentences explaining why this is the correct answer."
  }},
  ...
]"""

        text = await safe_generate(client, MODEL_NAME, prompt)
        if text == AI_FALLBACK:
            raise RuntimeError("AI service unavailable; cannot generate quiz. Please try again.")

        text = text.replace("```json", "").replace("```", "").strip()
        try:
            quiz = json.loads(text)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Gemini returned invalid JSON for quiz: {e}") from e

        # Normalize: some model responses may still use the legacy "answer" key —
        # accept it so a stray non-conforming response doesn't break scoring.
        for q in quiz:
            if "correct_answer" not in q and "answer" in q:
                q["correct_answer"] = q.pop("answer")
            q.setdefault("explanation", "")

        return quiz

    def get_profile(self) -> Dict:
        """Return the student profile."""
        return self.profile

    def get_db_stats(self) -> Dict:
        """Get vector database statistics."""
        return self.vector_db.get_stats()


class UserMemoryManager:
    """Builds and maintains a persistent model of how a specific student learns.

    Stored in MongoDB `user_models` collection — one document per user,
    updated incrementally so it never resets between sessions.
    """

    def __init__(self, user_id: str, db):
        self.user_id = user_id
        self.db = db

    async def load(self) -> Dict:
        """Return the current user model, or an empty scaffold if first visit."""
        doc = await self.db.user_models.find_one({"user_id": self.user_id})
        return doc or {}

    async def record_emotion(self, emotion: str, topic: Optional[str], subject: str) -> None:
        """Append one emotion data point and keep a rolling window of the last 20."""
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$push": {
                    "recent_emotions": {
                        "$each": [{"emotion": emotion, "topic": topic, "subject": subject}],
                        "$slice": -20,
                    }
                },
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def record_session(self, subject: str, duration_minutes: float) -> None:
        """Update session statistics used to estimate attention span."""
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$inc": {"total_sessions": 1},
                "$push": {
                    "session_durations": {
                        "$each": [round(duration_minutes, 1)],
                        "$slice": -10,
                    }
                },
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def record_dropoff(self, topic: str, subject: str) -> None:
        """Mark a topic the student abandoned mid-session."""
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$addToSet": {"dropoff_topics": {"topic": topic, "subject": subject}},
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def update_style_profile(self, style_text: str) -> None:
        """Persist the Gemini-generated communication style summary."""
        from datetime import datetime
        await self.db.user_models.update_one(
            {"user_id": self.user_id},
            {
                "$set": {
                    "style_profile": style_text,
                    "style_updated_at": datetime.utcnow(),
                },
                "$setOnInsert": {"user_id": self.user_id},
            },
            upsert=True,
        )

    async def build_style_profile(self, messages: list) -> str:
        """Ask Gemini to describe this student's communication style.

        Only runs when >= 20 messages are available and the profile is either
        missing or older than 7 days.  Returns the cached profile otherwise.
        """
        from datetime import datetime, timedelta

        if len(messages) < 20:
            return ""

        doc = await self.load()
        last_updated = doc.get("style_updated_at")
        if last_updated and (datetime.utcnow() - last_updated).days < 7:
            return doc.get("style_profile", "")

        # Scan ALL passed messages for user turns so alternating conversation
        # history doesn't starve the sample (bug: [:20] slice + role filter
        # could yield < 10 user messages from a 30-msg window).
        sample = [m["message"] for m in messages if m.get("role") == "user"]
        if len(sample) < 8:
            return ""

        prompt = (
            "Analyze these messages from one student and describe their "
            "communication style in exactly 3 short bullet points.\n"
            "Focus on: tone (formal/casual), vocabulary level, how they "
            "express confusion or excitement.\n\n"
            "Messages:\n" + "\n".join(f"- {m}" for m in sample[:15]) +
            "\n\nOutput 3 bullet points only. No intro sentence."
        )

        style = await safe_generate(client, MODEL_NAME, prompt)
        if style and style != AI_FALLBACK:
            await self.update_style_profile(style)
            return style
        return ""

    def frustration_summary(self, model: Dict) -> str:
        """Return a short prompt block describing the student's frustration pattern."""
        emotions = model.get("recent_emotions", [])
        if not emotions:
            return ""

        frustrated = [e for e in emotions if e.get("emotion") == "frustrated"]
        if not frustrated:
            return ""

        topics = [e["topic"] for e in frustrated if e.get("topic")]
        rate = len(frustrated) / len(emotions)

        lines = [f"STUDENT MEMORY — frustration rate: {rate:.0%} of recent messages"]
        if topics:
            from collections import Counter
            top = [t for t, _ in Counter(topics).most_common(3)]
            lines.append(f"Struggles most with: {', '.join(top)}")
        if rate > 0.5:
            lines.append("Approach carefully — this student frustrates easily. Keep responses short and simple.")
        return "\n".join(lines)

    def dropoff_warning(self, model: Dict, current_topic: Optional[str]) -> str:
        """Warn Gemini if the current topic previously caused the student to give up."""
        if not current_topic:
            return ""
        dropoffs = [d["topic"] for d in model.get("dropoff_topics", [])]
        if current_topic.lower() in [d.lower() for d in dropoffs]:
            return (
                f"⚠️ MEMORY: Student previously abandoned this topic ({current_topic}). "
                "Start from the very basics. Use a different approach than last time."
            )
        return ""


__all__ = ["LearningSystem", "VectorDBManager", "UserMemoryManager"]
