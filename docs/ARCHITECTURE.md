# AI Tutor — Architecture

This document describes the system after Sprint 2's backend modularization. For day-to-day setup and commands, see the root [CLAUDE.md](../CLAUDE.md).

## Folder Overview

```
backend/
├── app/
│   ├── main.py              FastAPI instance, lifespan, CORS, static mount, router registration,
│   │                        global exception handler
│   ├── core/                config.py, security.py, logging.py, limiter.py — cross-cutting infra
│   ├── db/                  mongo.py — Motor client + index setup
│   ├── models/               subject.py — shared Mongo document-shape factory (not a runtime ORM;
│   │                        MongoDB via Motor is schemaless)
│   ├── schemas/              Pydantic request/response models, one file per feature area
│   ├── repositories/         thin per-collection Mongo query functions
│   ├── services/             business logic: RAG pipeline, decision engine, session cache, etc.
│   ├── dependencies/         FastAPI Depends() functions (auth)
│   ├── routers/               route handlers, one file per feature area
│   └── utils/                stateless helpers (PDF text extraction, filename sanitization)
├── tests/                    pytest suite (100 tests), mirrors the app/ structure by concern
├── chroma_db/                ChromaDB persistent vector storage (gitignored, one collection per user)
└── requirements.txt

frontend/
├── src/
│   ├── pages/                one file per route + a co-located *.test.tsx for the 5 tested pages
│   ├── components/           shared UI (Sidebar, Skeleton, PageTransition)
│   ├── layouts/               DashboardLayout
│   ├── store/                 auth.tsx — React Context for token/user
│   ├── lib/                   api.ts (fetch wrapper), queryClient.ts, cn.ts
│   ├── test-utils.tsx         renderWithProviders() — MemoryRouter + QueryClientProvider + AuthProvider
│   └── setupTests.ts           jest-dom matchers + jsdom polyfills (scrollIntoView, ResizeObserver, matchMedia)
└── vite.config.ts             dev proxy to backend:8000, Vitest `test` config
```

## Module Responsibilities

| Package | Owns | Does NOT own |
|---|---|---|
| `core/` | env var loading (`config.py`), JWT + bcrypt (`security.py`), logging setup, the slowapi rate limiter | DB access, HTTP routing |
| `db/` | the Motor client and collection index creation | query logic (that's `repositories/`) |
| `models/` | shared document-shape factories (currently just the per-subject stats slot) | Pydantic API contracts (that's `schemas/`) |
| `schemas/` | request/response validation | anything that touches Mongo or an external API |
| `repositories/` | one function per simple `db.<collection>.<verb>()` call | multi-collection writes bundled via `asyncio.gather` and business-logic aggregations — those stay in the router, since wrapping a single-caller orchestration in a repository method adds indirection without reuse benefit |
| `services/` | the RAG pipeline (`vector_db.py`, `learning_system.py`), long-term user memory (`user_memory.py`), the Gemini client + retry wrapper (`ai_client.py`), NLP preprocessing (`nlp.py`), the adaptive decision engine, the nightly scheduler, the session cache (`session_manager.py`) | HTTP concerns (status codes, request parsing) |
| `dependencies/` | FastAPI `Depends()` providers (`get_current_user`, `get_current_active_user`) | business logic beyond auth resolution |
| `routers/` | request parsing, calling into services/repositories, shaping the HTTP response | direct Mongo queries (goes through `repositories/`) except gather-bundled writes and the analytics aggregation loop |
| `utils/` | small stateless helpers with no framework or DB dependency | anything stateful |

## Backend Request Lifecycle

```
client
  → Vite dev proxy (dev) / FastAPI static mount (prod)
  → slowapi rate-limit check (routes that declare @limiter.limit(...))
  → app.dependencies.auth.get_current_active_user  (JWT decode → app.repositories.users lookup)
  → router handler (app.routers.*)
      → app.services.session_manager.get_learning_session()  (cached LearningSystem per user, TTL-evicted)
      → app.services.* / app.repositories.* for the actual work
  → response
```

Uncaught exceptions that aren't `HTTPException` (or `RateLimitExceeded`, which has its own handler) are caught by a global handler in `app/main.py`: the full traceback is logged server-side, and the client gets a generic `{"detail": "Internal server error"}` — no internal exception text ever reaches a response body.

## AI / RAG Request Flow

**Document ingestion** (`POST /upload_pdf`):
```
PDF bytes → app.utils.pdf.extract_text_from_pdf() (page-tagged text)
          → app.services.vector_db._chunk_text() (paragraph-aware, ~900 chars)
          → Jina AI embeddings (retrieval.passage, async HTTP)
          → ChromaDB upsert (per-user collection, cosine space)
          → app.repositories.documents (metadata record)
```

**Chat** (`POST /chat`):
```
message → app.services.nlp (preprocess, extract topics, classify intent, detect emotion)
        → app.services.decision_engine.decide_next_step (proficiency/engagement/inactivity → strategy+difficulty+tone)
        → app.services.vector_db hybrid retrieval:
            dense (ChromaDB cosine) + sparse (BM25 over the same pool) → merged via Reciprocal Rank Fusion
        → app.services.learning_system._resolve_tutor_mode (direct-teaching / contextual-RAG / hybrid)
        → prompt assembly (persona + long-term memory + emotion tone + subject style guide + adaptive block)
        → app.services.ai_client.safe_generate() (Gemini call with retry/backoff/timeout/fallback)
        → response persisted (chat_history, learning_events), long-term memory updated (fire-and-forget)
```

The tutor's persona subject is driven by the user's **active workspace** (`current_subject`), threaded into `LearningSystem.profile["subject"]` by `session_manager.get_learning_session()` — this was a bug fixed in Sprint 1 (the persona used to read a dormant, UI-inaccessible legacy field and always said "General").

**Quiz/Roadmap generation**: same `ai_client.safe_generate()` path, with a JSON-array prompt contract. Both generators run a normalization pass on the parsed response (`generate_quiz` remaps a legacy `answer` key to `correct_answer`; `generate_roadmap` remaps legacy `module`/`topic` keys to `title`/`description` and assigns a reliable sequential `step` number itself) — this is what actually fixed the Sprint 1 bugs where the frontend and backend contracts had drifted apart.

## Database

MongoDB via Motor, no ORM — `app/models/` documents the *shape* of what's stored but nothing is runtime-validated against it. Collections: `users`, `chat_history`, `quiz_performance`, `documents`, `feedback`, `learning_events`, `user_models`, `analytics_events`, `explanation_failures`. See CLAUDE.md for the per-collection contents table.

`users.subjects` is an embedded subdocument (`{name: {weak_topics, strong_topics, proficiency_score, engagement_score, cumulative_score, total_attempts, roadmap?}}`) rather than a separate collection — reasonable at the cardinality of a handful of workspaces per user. The shape is defined once, in `app/models/subject.py::default_subject_stats()`.

## Testing

- **Backend**: pytest + pytest-asyncio, 100 tests, everything mocked (Motor, ChromaDB, Gemini) — no real network calls. Test files roughly mirror the service boundaries (`test_auth.py` → `core/security.py` + `services/auth_service.py`; `test_core.py` → `services/vector_db.py` + `services/learning_system.py`; etc.), not the old flat-file names.
- **Frontend**: Vitest + React Testing Library, 17 tests across the 5 pages named in Sprint 2's scope (Auth, Chat, Quiz, Roadmap, Profile). `src/lib/api.ts` is mocked per test file so nothing hits a real backend.

## Known Architectural Constraints (not fixed by Sprint 2 — noted for future work)

- **Single-process**: `app/services/session_manager.py`'s in-memory cache, the slowapi rate limiter's default in-memory store, and the nightly APScheduler job all live in one process. Scaling to multiple replicas would need a shared cache (Redis) for the first two and leader election (or a dedicated worker) for the third.
- **ChromaDB is per-user, not per-subject**: all of a user's uploaded documents share one vector collection across every subject workspace — RAG retrieval isn't subject-scoped.
- **Repository depth is deliberately uneven by design**, not by omission: gather-bundled multi-collection writes and the analytics day-bucket aggregation stay in their router because they're orchestration, not reusable data access. See the "Does NOT own" column above.
