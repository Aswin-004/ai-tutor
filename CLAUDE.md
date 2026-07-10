# AI Tutor — Project Guide

## Project Overview

An AI-powered tutoring system: FastAPI backend + React frontend. Provides personalized learning via RAG (Retrieval-Augmented Generation), adaptive quizzes, and learning roadmaps. Users upload PDFs; the system embeds them into ChromaDB and answers questions with context from those documents.

## Architecture

Backend is a modular FastAPI app (`backend/app/`), not a flat file — see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full breakdown (module responsibilities, request lifecycle, RAG flow). Quick orientation:

```
backend/app/
├── main.py            FastAPI instance, lifespan, CORS, router registration, global exception handler
├── core/               config.py, security.py, logging.py, limiter.py
├── db/                 mongo.py — Motor client + indexes
├── models/              subject.py — shared Mongo document-shape factory
├── schemas/             Pydantic request/response models
├── repositories/         thin per-collection Mongo query functions
├── services/             LearningSystem (RAG), decision engine, session cache, Gemini client, NLP, scheduler
├── dependencies/         FastAPI Depends() — auth
├── routers/              route handlers (public, auth, chat, voice, documents, quiz, roadmap, analytics, misc)
└── utils/                PDF text extraction, filename sanitization

frontend/
├── src/pages/           one file per route (+ *.test.tsx for Auth/Chat/Quiz/Roadmap/Profile)
├── src/components/      Sidebar, Skeleton, PageTransition
├── src/store/auth.tsx   token/user Context
└── src/lib/             api.ts fetch wrapper, queryClient.ts

backend/chroma_db/      ChromaDB persistent vector storage (gitignored, one collection per user)
```

**External services:**
- **Jina AI** — text embeddings (via HTTP, not SDK)
- **Google Gemini 2.5 Flash** — LLM for chat, quiz, roadmap generation, voice transcription
- **MongoDB** — user data, chat history, quiz scores, documents metadata, feedback

## Running the Project

```bash
# Backend setup (one-time), from backend/
cd backend
python -m venv ../.venv          # or use an existing venv at repo root
..\.venv\Scripts\activate        # Windows
pip install -r requirements.txt

# Frontend setup (one-time), from frontend/
cd frontend
npm install
```

**Terminal 1 — MongoDB** (start manually each session):
```
"C:\Program Files\MongoDB\Server\8.2\bin\mongod.exe" --dbpath "$HOME\mongodb-data" --port 27017
```
Or as admin: `net start MongoDB`

**Terminal 2 — Backend** (from `backend/`):
```bash
uvicorn app.main:app --reload
```
Note: the entry point is `app.main:app`, not `app:app` — `app` is a package (`backend/app/`), not a single file, since Sprint 2's modularization.

**Terminal 3 — Frontend** (from `frontend/`):
```bash
npm run dev
```

- Frontend (dev): http://localhost:5173 (Vite proxies API calls to :8000)
- Frontend (prod build, served by FastAPI): http://localhost:8000/
- Swagger docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Environment Variables

Create a `.env` file in `backend/`:

```
JINA_API_KEY=...
GOOGLE_API_KEY=...
SECRET_KEY=...                        # JWT signing key, must be >= 32 chars
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
MONGO_URL=mongodb://localhost:27017
MONGO_DB_NAME=ai_tutor
ALLOWED_ORIGINS=http://localhost:8000,http://localhost:3000,http://localhost:5173
```

All of these are loaded and validated once, at import time, in `app/core/config.py` — the app refuses to start if `SECRET_KEY`/`JINA_API_KEY`/`GOOGLE_API_KEY` are missing, or if `ALLOWED_ORIGINS` contains `localhost` while `ENVIRONMENT=production`.

## Key Concepts

### RAG Pipeline (`app/services/vector_db.py`, `app/services/learning_system.py`)
1. PDF text extracted with `pypdf` (`app/utils/pdf.py`)
2. Chunked (paragraph-aware, ~900 chars) and embedded via Jina AI (HTTP POST)
3. Stored in ChromaDB (one collection per user — not per subject workspace)
4. On query: hybrid retrieval — dense cosine similarity (ChromaDB) + sparse BM25, merged via Reciprocal Rank Fusion — then Gemini prompt assembly, shaped by tutor mode (direct-teaching / contextual-RAG / hybrid)

### Session Caching (`app/services/session_manager.py`)
`active_sessions` dict caches `LearningSystem` instances per user (TTL-evicted after 4h idle) to avoid re-initialising ChromaDB on every request. Shared across the chat/documents/quiz/roadmap/stats routers.

### Adaptive Learning (`app/services/decision_engine.py`)
Computes a learning strategy from proficiency score, session engagement, and time-since-last-activity. `LearningSystem` uses this to adjust chat difficulty/tone and quiz/roadmap focus.

### Weak Topic Detection
K-Means clustering (`scikit-learn`) on per-topic quiz scores identifies weak areas, which are highlighted in roadmaps and targeted by subsequent quizzes.

### Multi-Subject Workspaces
Users can create any number of named subject workspaces (no hardcoded list). Each workspace has its own weak topics, proficiency score, roadmap, and document context is currently shared across all of them (see docs/ARCHITECTURE.md's "Known Architectural Constraints"). The AI tutor's persona is driven by the *active* workspace (`current_subject`) — set once per session in `session_manager.get_learning_session()`.

## MongoDB Collections

| Collection | Contents |
|---|---|
| `users` | Accounts, profiles, `subjects: {name: {...}}` embedded subdocument (weak_topics, proficiency, roadmap per workspace) |
| `chat_history` | Conversation messages per user |
| `quiz_performance` | Quiz results and metrics |
| `documents` | Uploaded PDF metadata |
| `feedback` | User ratings on responses |
| `learning_events` | Activity log (chat/quiz/heartbeat) for engagement tracking and the analytics dashboard |
| `user_models` | Long-term per-user memory: recent emotions, dropoff topics, communication style profile |
| `analytics_events` | Product analytics event stream (signup, upload, question asked, quiz completed, roadmap generated) |
| `explanation_failures` | Low-scoring quiz / thumbs-down chat responses, for future quality analysis |

## API Rate Limits

| Endpoint group | Limit |
|---|---|
| Auth (register/login) | 5 req/min per IP |
| Auth (change-password) | 3 req/min per IP |
| Quiz generation/submit, roadmap generation, PDF upload, voice transcription | 10 req/min per IP (5/min for upload) |
| Chat | 20 req/min per IP |

## Dependencies

**Backend** — see `backend/requirements.txt`:
- `fastapi`, `uvicorn` — web server
- `motor`, `pymongo` — async MongoDB
- `chromadb` — vector database
- `google-genai` — Gemini API
- `httpx` — async HTTP (Jina calls)
- `pypdf` — PDF parsing
- `scikit-learn` — K-Means for weak topic detection
- `python-jose`, `bcrypt` — JWT + password hashing
- `slowapi` — rate limiting
- `apscheduler` — nightly self-improvement job
- `rank-bm25` — sparse retrieval for hybrid RAG
- `spacy` — query preprocessing / emotion detection

**Frontend** — see `frontend/package.json`:
- `react`, `react-router-dom`, `@tanstack/react-query` — core app
- `framer-motion` — page transitions and micro-interactions (used on every page)
- `recharts` — analytics charts
- `vitest`, `@testing-library/react` — testing (added Sprint 2)

## Testing

**Backend**: pytest + pytest-asyncio, 100 tests, fully mocked (no real Mongo/ChromaDB/Gemini calls).
```bash
cd backend
pytest -v
```

**Frontend**: Vitest + React Testing Library, 17 tests covering Auth/Chat/Quiz/Roadmap/Profile.
```bash
cd frontend
npm test
```

CI (`.github/workflows/ci.yml`) runs both suites plus a frontend production build on every push/PR.

## Development Notes

- All database operations are async (`async/await` throughout); do not introduce blocking I/O on the request path.
- ChromaDB collections are named by user ID (`user_{id}`), not by subject. Deleting a user should also delete their ChromaDB collection to avoid orphaned data.
- CORS is configured via the `ALLOWED_ORIGINS` env var (see above), validated in `app/core/config.py`.
- Every simple single-collection Mongo query goes through `app/repositories/`. Multi-collection writes bundled via `asyncio.gather()` (e.g. `/chat` persisting to `chat_history` + `learning_events` + `users` simultaneously) and the analytics day-bucket aggregation stay inline in their router — that's orchestration, not reusable data access.
- Uncaught exceptions never leak raw text to API clients — a global handler in `app/main.py` logs the full traceback server-side and returns a generic `{"detail": "Internal server error"}`.
