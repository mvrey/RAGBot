# Plan — Split RAGBot into FastAPI backend + Next.js frontend

Status: **proposed, not started.** No code written yet.

---

## 1. Why, and what makes this cheap

The app is currently a Streamlit monolith. Splitting it gives a real API, a designed UI, and a
containerised deployment story — all three graded by the assignment, and the last two are current gaps.

**The single most important finding:** `ragbot/src/` has **zero Streamlit imports**. Every module —
ingestion, chunking, embeddings, retrieval, agent, logging — is already UI-agnostic. Streamlit lives only
in `app.py`. So this is an **extraction and a new API layer, not a rewrite of the core.** The risky part
is state and streaming, not the domain logic.

### Decisions already settled

| Decision | Choice | Consequence |
|---|---|---|
| State model | Single-user, structured for multi-user | Keyed stores, not globals — swapping in Redis/Postgres later is substitution, not rewrite |
| Background jobs | FastAPI `BackgroundTasks` + job registry | Two containers only; jobs die with the process |
| Embeddings | **Gemini** (`gemini-embedding-2`) | No torch in the image — backend drops from ~2.5GB to ~400MB |
| Frontend scope | Chat + ingest + source viewer | Citations become clickable and open the real file |

All three trade-offs must be written up in the README (see Phase 8).

---

## 2. Target layout

```
RAGBot/
├── backend/
│   ├── pyproject.toml            # backend deps only
│   ├── Dockerfile
│   ├── .dockerignore
│   ├── .env.example
│   ├── ragbot/
│   │   ├── core/                 # ← today's ragbot/src, moved verbatim
│   │   │   ├── Repository.py  CodeChunker.py  TextChunker.py
│   │   │   ├── Embeddings.py  TextSearcher.py  SearchStrategy.py
│   │   │   ├── AgentWrapper.py  Prompts.py  AgentLog.py  LLM.py
│   │   │   └── settings.py       # NEW: env-driven paths
│   │   ├── api/
│   │   │   ├── main.py           # FastAPI app, CORS, lifespan
│   │   │   ├── routes/           # repos.py  jobs.py  chat.py  meta.py
│   │   │   ├── schemas.py        # pydantic request/response models
│   │   │   ├── state.py          # index cache + conversation store
│   │   │   └── jobs.py           # job registry + runner
│   │   └── cli.py                # today's main.py
│   └── tests/                    # today's tests + new API tests
├── frontend/
│   ├── package.json  Dockerfile  .dockerignore  .env.example
│   ├── app/                      # Next.js App Router
│   ├── components/
│   └── lib/
├── docker-compose.yml
├── docs/
└── README.md
```

**Import rewrite:** `from src.X import Y` → `from ragbot.core.X import Y` across ~12 modules and 6 test
files. Mechanical, and it removes today's papercut of having to `cd ragbot` before running anything.

**Two environments, fully separate:** `backend/pyproject.toml` (Python) and `frontend/package.json`
(Node). Neither knows how the other is built. The root keeps only `docker-compose.yml` and docs.

---

## 3. Phase 0 — Gemini embeddings provider *(prerequisite)*

Do this first: it's what removes torch from the image and unblocks a slim container.

Add `GeminiEmbedder` to `core/Embeddings.py` alongside the existing local/OpenAI providers. Reuses the
`google-genai` client already installed for the chat model.

```python
client.models.embed_content(
    model="gemini-embedding-2",
    contents=[...],
    config=types.EmbedContentConfig(output_dimensionality=768),
)
```

Details that matter, from the API docs:

- **Dimensions are configurable** (128–3072, default 3072). Default to **768** — same size as the current
  local model, and 4× smaller on disk than 3072 (15MB vs 61MB per 5000 chunks).
- **⚠️ The cache namespace must include the dimension.** `CachingEmbedder` currently namespaces by
  `embedder.name`. If someone changes `output_dimensionality`, vectors of two different shapes would land
  in one store. Set `name = f"google:{model}@{dim}"` so the namespace changes with the shape.
- **`gemini-embedding-2` does not support `task_type`.** Asymmetric retrieval is done with prompt
  prefixes instead — `"task: search result | query: {text}"`. This maps cleanly onto the existing
  `encode()` contract, which already treats a `str` as a query and a `list` as corpus documents.
- **8192-token input limit** — reuse the existing character-based truncation approach.
- Batch requests; handle partial failures and retries.

Config: `EMBEDDING_PROVIDER=google` (new default), `EMBEDDING_MODEL`, `EMBEDDING_DIMENSIONS`.
`sentence-transformers` becomes an optional extra rather than a base dependency.

**Tests:** dimension flows through to the cache namespace; query vs document prefixes differ; batching;
a fake client so no network is needed.

---

## 4. Phase 1 — Extract the core

1. `git mv ragbot/src backend/ragbot/core`, `ragbot/main.py` → `backend/ragbot/cli.py`.
2. Rewrite imports (`src.` → `ragbot.core.`).
3. **New `core/settings.py`** — paths are currently hardcoded relative to `__file__`, which breaks in a
   container. Make them env-driven with the current values as defaults:
   - `RAGBOT_DATA_DIR` → repo mirror + embedding cache (default `./data`)
   - `RAGBOT_LOG_DIR` → interaction logs
4. Move `tests/` under `backend/`, update `conftest.py`.
5. Delete `app.py` (Streamlit) **at the end of Phase 5**, not now — it stays runnable as a reference while
   the API is built.
6. `AsyncRunner` becomes unnecessary: FastAPI already owns one long-lived loop. Restructure `cli.py` to a
   single `asyncio.run(async_main())` and delete `AsyncRunner` and its tests.

**Gate:** all 119 existing tests pass unchanged apart from imports. If they don't, stop — the core was
more coupled than it looked.

---

## 5. Phase 2 — FastAPI surface

### Endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Liveness + active chat model and embedder |
| `GET` | `/api/config` | Chunking strategies and search methods **with their display labels** — frontend must not hardcode enums |
| `GET` | `/api/repos` | Cached repos (wraps `Repository.list_cached_repos`) |
| `POST` | `/api/repos` | Start ingestion → `202 {job_id, repo_key}` |
| `GET` | `/api/repos/{key}` | Metadata: url, file count, language stats, chunk count, index state |
| `DELETE` | `/api/repos/{key}` | Evict from cache and disk |
| `GET` | `/api/repos/{key}/files` | File tree — powers the source viewer |
| `GET` | `/api/repos/{key}/files/{path}` | File content, optional line range |
| `GET` | `/api/jobs/{id}` | Job status (poll fallback) |
| `GET` | `/api/jobs/{id}/events` | **SSE** progress stream |
| `POST` | `/api/conversations` | Create, bound to a `repo_key` |
| `GET` | `/api/conversations/{id}` | Message history |
| `DELETE` | `/api/conversations/{id}` | Clear |
| `POST` | `/api/conversations/{id}/messages` | Ask a question → **SSE** token stream |

### Streaming contract

SSE event types, so the UI can show the agent working rather than a spinner:

```
event: token        data: {"delta": "..."}
event: tool_call    data: {"tool": "search_code", "args": {...}}
event: tool_result  data: {"tool": "read_file", "summary": "src/x.py 1-40"}
event: citation     data: {"path": "src/X.py", "start": 12, "end": 34}
event: done         data: {"message_id": "...", "usage": {...}}
event: error        data: {"detail": "..."}
```

`AgentWrapper` gains a `run_stream()` using pydantic-ai's `agent.iter()` (needed for tool events;
`run_stream()` alone gives text only). **Verify the exact 1.0.9 API before building the UI against it** —
this is the highest-uncertainty item in the plan.

### Reusing existing safety

`read_file` / `list_files` already resolve paths against the repo root and reject traversal
(`AgentWrapper._safe_repo_path`). The `/files/{path}` endpoint **must reuse that same helper**, not
reimplement it — it is now reachable by anyone who can call the API, not just the model.

---

## 6. Phase 3 — State and jobs

### Index cache

```python
BuiltIndex = (repository, chunks, search_strategy, agent_wrapper)
indexes: dict[(repo_key, chunking, search_method) -> BuiltIndex]   # LRU, max ~3
```

Built lazily on first use, and rebuilt cheaply on a cold start because embeddings are already cached to
disk (~14ms to load vs minutes to recompute). **Chunks are still not persisted** — chunking is 0.03s, so
recomputing beats an invalidation problem. That decision still holds after the split.

### Conversations

```python
conversations: dict[conv_id -> {repo_key, pydantic_ai_history, created_at}]
```

In-memory, LRU-capped. Same context-growth caveat as today: history is passed whole because naive
trimming would break tool-call/tool-return pairing.

### Jobs

```python
Job = {id, kind, status, phase, progress, message, error, result, created_at}
```

Phases mirror the pipeline: `downloading → chunking → embedding → indexing → ready`, so the UI shows real
progress instead of an indeterminate bar.

### ⚠️ Blocking work must leave the event loop

Chunking, embedding, and index fitting are synchronous and CPU-bound. Called directly from an async
handler they would stall every other request. **All of it goes through `anyio.to_thread.run_sync`.** This
is the easiest way to build something that looks fine in dev and collapses under two users.

---

## 7. Phase 4 — Next.js frontend

**Stack:** Next.js (App Router) + TypeScript + Tailwind + shadcn/ui, TanStack Query for server state,
`shiki` for syntax highlighting.

### Routes

- `/` — cached repos, plus an ingest form (URL, chunking strategy, search method from `/api/config`)
- `/repo/[key]` — the workspace: chat on the left, source viewer on the right

### Key components

| Component | Notes |
|---|---|
| `IngestForm` | Validates the codeload URL shape client-side before submitting |
| `JobProgress` | Subscribes to the SSE job stream; named phases, not a fake percentage |
| `ChatPanel` | Streams tokens; renders tool calls as collapsible "what the agent did" steps |
| `CitationLink` | Parses `path:start-end` out of the answer, renders a chip |
| `SourceViewer` | Opens the cited file, scrolls to and highlights the cited lines |
| `FileTree` | Browse the ingested repo directly |

**The citation → source viewer link is the centrepiece.** The backend works hard for accurate
`path:line` citations; this is what makes that visible instead of it being trivia in a text answer.

**Design intent:** one workspace screen, not a wizard. Ingestion is a modal/side task; the chat is the
product. Dark/light via CSS variables. Empty and error states designed, not default.

---

## 8. Phase 5 — Containerisation

### `backend/Dockerfile`
`python:3.13-slim`, non-root user, layer-cached dependency install, `uvicorn` entrypoint, `HEALTHCHECK`
against `/api/health`. **No torch** — Gemini embeddings keep it to roughly **400MB**. tree-sitter ships
manylinux wheels, so no compiler is needed.

### `frontend/Dockerfile`
`node:22-alpine`, multi-stage (deps → build → runtime), `output: 'standalone'`, non-root.

### `docker-compose.yml`
```yaml
backend:   ports 8000, env_file backend/.env, volume ragbot-data:/data
frontend:  ports 3000, NEXT_PUBLIC_API_URL=http://localhost:8000, depends_on backend (healthy)
volumes:   ragbot-data          # repo mirror + embedding cache survive rebuilds
```

Gotchas: CORS must allow the frontend origin; `NEXT_PUBLIC_*` is baked at **build** time, not runtime;
SSE needs proxy buffering disabled if anything sits in front.

---

## 9. Phase 6 — Tests

- **Core:** the existing 119 tests carry over with import changes only.
- **API:** `httpx.ASGITransport` against the app — every endpoint, the job lifecycle
  (`pending → running → succeeded`), SSE framing, 404s, and **path traversal via `/files/{path}`**.
- **Frontend:** vitest + RTL for citation parsing (the piece with real logic) and for SSE handling;
  one Playwright happy-path smoke test (ingest → ask → citation opens the file) if time allows.
- **CI:** a GitHub Actions workflow running both suites — currently missing entirely.

---

## 10. Phase 7 — README

Three trade-offs to write up explicitly, as agreed:

1. **Single-user state.** In-process, keyed stores; one backend instance only; conversations and jobs are
   lost on restart. Why: no database or cache service for a demo. What multi-user needs: Redis or Postgres
   behind the same interfaces, plus auth and per-user scoping.
2. **No Redis/RabbitMQ/Celery.** Jobs run in-process via `BackgroundTasks`: two containers instead of
   four, no broker to operate. Cost: jobs die with the process, can't be retried or distributed, and
   ingestion competes with request serving. Upgrade path: RQ or Celery with the job registry swapped
   behind its current interface.
3. **Gemini embeddings over a local model.** Cheap, no torch, ~400MB image instead of ~2.5GB, and better
   on code than the old local default. Cost: **every chunk of every ingested repo is sent to Google**, and
   indexing needs network and spend. For private or air-gapped code this is the wrong default —
   `EMBEDDING_PROVIDER=local` keeps everything on the machine, at the price of a much larger image, slower
   CPU indexing, and weaker retrieval. Both stay supported; only the default changes.

Also update: architecture diagram, setup (compose-first), and the module table.

---

## 11. Risks, worst first

| Risk | Mitigation |
|---|---|
| pydantic-ai 1.0.9 streaming/`iter()` API differs from expectation | **Spike this in Phase 2 before any UI work.** Fall back to non-streaming responses if needed — the UI degrades to a spinner rather than being blocked |
| Blocking work stalls the event loop | `anyio.to_thread.run_sync` everywhere; load-test with concurrent requests |
| Embedding dimension change silently corrupts the cache | Dimension in the cache namespace (Phase 0), plus a test |
| SSE buffered by a proxy | Correct headers; test through compose, not just directly |
| Import rewrite breaks something subtle | The 119 existing tests are the gate at the end of Phase 1 |
| Scope creep in the frontend | Source viewer is the only "extra"; retrieval inspector explicitly deferred |
| Windows dev vs Linux container path handling | Paths via `pathlib` + settings; CI runs the Linux image |

---

## 12. Explicitly not doing

Auth/multi-tenancy · a database · a vector database (unchanged: search is ~11ms at this scale) ·
persisted chunks · incremental re-indexing · WebSockets (SSE is enough — traffic is one-directional) ·
the retrieval inspector panel · Kubernetes manifests.

---

## 13. Verification

1. `pytest` green in `backend/` (119 existing + new API tests).
2. `docker compose up --build` → both containers healthy from a clean clone.
3. Ingest a repo through the UI; progress advances through named phases.
4. Ask a question; tokens stream; tool steps appear.
5. Click a `path:line` citation → the file opens with those lines highlighted.
6. Restart the backend → the repo is still listed, and re-indexing is fast (embedding cache hit).
7. `GET /api/repos/{key}/files/../../etc/passwd` → rejected.
8. Ingest a **non-Python** repo (Go or TypeScript) to exercise the language map.
9. Confirm the image is ~400MB and contains no torch.

---

## 14. Sequencing

| Phase | Depends on | Rough size |
|---|---|---|
| 0 — Gemini embeddings | — | S |
| 1 — Extract core | 0 | S |
| 2 — FastAPI surface | 1 | M |
| 3 — State & jobs | 2 | M |
| 4 — Next.js frontend | 2 (contract) | L |
| 5 — Containerisation | 2, 4 | M |
| 6 — Tests | 3, 4 | M |
| 7 — README | all | S |

Phases 0–3 deliver a working API testable with `curl` — a real checkpoint before any frontend work
begins. Streamlit stays runnable until Phase 5 so there is always a working app.
