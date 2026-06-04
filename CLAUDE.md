# AI Tutor — Project Guide

## Project Overview

An AI-powered tutoring system built with FastAPI. Provides personalized learning via RAG (Retrieval-Augmented Generation), adaptive quizzes, and learning roadmaps. Users upload PDFs; the system embeds them into ChromaDB and answers questions with context from those documents.

## Architecture

```
app.py              — FastAPI entry point; all HTTP routes
auth.py             — User registration, login, JWT token issuance
core.py             — LearningSystem class: RAG pipeline, embeddings, quiz/roadmap generation
decision_engine.py  — Adaptive strategy: adjusts difficulty based on proficiency/engagement
mongo.py            — Motor async MongoDB client + index setup
video_resources.py  — Static topic → YouTube URL mapping
index.html          — Single-page frontend (vanilla JS, embedded, served by FastAPI)
js/three-auth-bg.js — Three.js WebGL animation for the auth screen
chroma_db/          — ChromaDB persistent vector storage (one collection per user)
```

**External services:**
- **Jina AI** — text embeddings (via HTTP, not SDK)
- **Google Gemini 2.5 Flash** — LLM for chat, quiz, roadmap generation
- **MongoDB** — user data, chat history, quiz scores, documents metadata, feedback

## Running the Project

```bash
# Setup (one-time)
python -m venv venv
venv\Scripts\activate          # Windows
pip install -r requirements.txt

# Start the server
uvicorn app:app --reload
```

- Frontend: http://localhost:8000/
- Swagger docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

## Environment Variables

Create a `.env` file in the project root:

```
JINA_API_KEY=...
GOOGLE_API_KEY=...
SECRET_KEY=...                        # JWT signing key
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
MONGO_URL=mongodb://localhost:27017
MONGO_DB_NAME=ai_tutor
```

## Key Concepts

### RAG Pipeline (`core.py`)
1. PDF text extracted with `pypdf`
2. Chunked and embedded via Jina AI (HTTP POST)
3. Stored in ChromaDB (per-user collection)
4. On query: embed query → cosine similarity search → top-k chunks → Gemini prompt

### Session Caching
`active_sessions` dict in `app.py` caches `LearningSystem` instances per user to avoid re-initialising ChromaDB on every request.

### Adaptive Learning
`decision_engine.py` computes a learning strategy from proficiency score, session engagement, and time-since-last-activity. `core.py` uses this to adjust quiz difficulty and roadmap focus.

### Weak Topic Detection
K-Means clustering (`scikit-learn`) on per-topic quiz scores identifies weak areas, which are highlighted in roadmaps and targeted by subsequent quizzes.

## MongoDB Collections

| Collection | Contents |
|---|---|
| `users` | Accounts, profiles, subjects, topic scores, proficiency |
| `chat_history` | Conversation messages per user |
| `quiz_performance` | Quiz results and metrics |
| `documents` | Uploaded PDF metadata |
| `feedback` | User ratings on responses |
| `learning_events` | Activity log for engagement tracking |

## API Rate Limits

| Endpoint group | Limit |
|---|---|
| Auth (register/login) | 5 req/min per IP |
| Quiz generation | 10 req/min per IP |
| Chat | 20 req/min per IP |

## Dependencies

See `requirements.txt`. Core libraries:
- `fastapi`, `uvicorn` — web server
- `motor`, `pymongo` — async MongoDB
- `chromadb` — vector database
- `google-genai` — Gemini API
- `httpx` — async HTTP (Jina calls)
- `pypdf` — PDF parsing
- `scikit-learn` — K-Means for weak topic detection
- `python-jose`, `bcrypt` — JWT + password hashing
- `slowapi` — rate limiting

## No Tests

The project currently has no automated tests. When adding features, consider adding pytest tests for:
- Auth flows (`auth.py`)
- Embedding and retrieval logic (`core.py`)
- Endpoint integration tests via `httpx.AsyncClient`

## Development Notes

- All database operations are async (`async/await` throughout); do not introduce blocking I/O on the request path.
- ChromaDB collections are named by user ID. Deleting a user should also delete their ChromaDB collection to avoid orphaned data.
- The frontend is fully embedded in `index.html` (82 KB). There is no build step; edit the file directly.
- CORS is configured for `localhost:8000` and `localhost:3000`. Update `app.py` if deploying to a different origin.
