# RAGBot - Code Documentation Assistant

An LLM-powered RAG agent that ingests a code project (**source code and documentation**) and
answers questions about it: how it works, where functionality lives, what the APIs and dependencies are.

Built for **Option 2: Code Documentation Assistant**.

| Assignment requirement | Section |
|---|---|
| a. Quick setup instructions | [a. Quick setup](#a-quick-setup) |
| b. Architecture overview | [b. Architecture overview](#b-architecture-overview) |
| c. Production on a hyper-scaler | [c. Production](#c-production-on-a-hyper-scaler) |
| d. RAG/LLM approach & decisions | [d. RAG / LLM approach & decisions](#d-rag--llm-approach--decisions) |
| e. Key technical decisions and why | [e. Key technical decisions](#e-key-technical-decisions-and-why) |
| f. Engineering standards followed / skipped | [f. Engineering standards](#f-engineering-standards-followed-and-skipped) |
| g. How I used AI tools | [g. AI tools in development](#g-how-i-used-ai-tools-in-my-development-process) |
| h. What I'd do differently with more time | [h. With more time](#h-what-id-do-differently-with-more-time) |
| Screenshots / video | [Screenshots & demo](#screenshots--demo) |

Also: [Known limitations](#known-limitations).

---

## a. Quick setup

The app is a FastAPI backend + Next.js frontend, split into `backend/` and `frontend/`

**Requirements:**

* a **Google Gemini API key** used for both the chat model and the default embedding provider.

### Docker Compose

```bash
cp backend/.env.example backend/.env      # then edit backend/.env and add GOOGLE_API_KEY
docker compose up --build
```

- Backend: http://localhost:8000 (docs at `/docs`, health at `/api/health`)
- Frontend: http://localhost:3000

`docker-compose.yml` mounts named volumes for the repo mirror, embedding cache, and interaction logs, so
they survive a rebuild. The frontend's `NEXT_PUBLIC_API_URL` is baked in at **build** time (see the gotcha
in section b), so if you change ports, rebuild rather than just restarting the container.

### Running without Docker

**Backend** (Python 3.13+):

```bash
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1                # Windows PowerShell
# source .venv/bin/activate               # Linux / macOS
pip install -e .                          # add '.[local-embeddings]' for EMBEDDING_PROVIDER=local
cp .env.example .env                      # then edit .env and add GOOGLE_API_KEY

python -m uvicorn ragbot.api.main:app --reload
# or, without installing: uvicorn ragbot.api.main:app --reload --app-dir backend
```

**Frontend** (Node 22+), in a second terminal:

```bash
cd frontend
npm install
cp .env.example .env.local                # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

Open http://localhost:3000, ingest a repo or upload a codebase, and chat. Or drive the backend directly:

```bash
curl -X POST localhost:8000/api/repos -H 'Content-Type: application/json' \
  -d '{"repo_url": "https://codeload.github.com/<owner>/<repo>/zip/refs/heads/main", "chunking_strategy": "AUTO", "search_method": "HYBRID"}'
```

**Or use the CLI**, a thin wrapper over the same pipeline for one-off questions without a browser:

```bash
cd backend
python -m ragbot.cli --question "How does hybrid search combine results?"
python -m ragbot.cli --repo <codeload-zip-url> --question "..." --cached --evaluate
```

Repo URLs are `codeload.github.com` zip links, e.g.
`https://codeload.github.com/<owner>/<repo>/zip/refs/heads/main`.

**Run the tests:**

```bash
cd backend && pytest                      # 155 tests
cd frontend && npm test                   # 34 tests (vitest)
```

---

## b. Architecture overview

SEE docs/architecture.jpg


| Module | Responsibility |
|---|---|
| `backend/ragbot/core/Repository.py` | Downloads the repo zip, filters files, mirrors them to an on-disk cache, dispatches chunking |
| `backend/ragbot/core/CodeChunker.py` | tree-sitter AST chunking; falls back to line windows |
| `backend/ragbot/core/TextChunker.py` | Markdown/prose chunking (headings, paragraphs, sliding window, LLM) |
| `backend/ragbot/core/ChunkingStrategy.py` | Strategy enum; `AUTO` dispatches per file type |
| `backend/ragbot/core/Embeddings.py` | Pluggable embedding providers (Google / local / OpenAI) and the on-disk vector cache |
| `backend/ragbot/core/LLM.py` | Chat-model selection from `.env`, and up-front credential checks |
| `backend/ragbot/core/TextSearcher.py` | Keyword, vector, and hybrid (RRF) retrieval over minsearch |
| `backend/ragbot/core/SearchStrategy.py` | Retrieval-mode dispatch |
| `backend/ragbot/core/AgentWrapper.py` | pydantic-ai agent, its three tools, and the SSE event stream (`run_stream`) |
| `backend/ragbot/core/Prompts.py` | System prompt, evaluation checklist, question generation |
| `backend/ragbot/core/AgentLog.py` | Per-interaction JSON logs and LLM-as-judge scoring |
| `backend/ragbot/core/settings.py` | Env-driven data/log paths |
| `backend/ragbot/api/main.py` | FastAPI app, CORS, lifespan-managed state |
| `backend/ragbot/api/routes/` | `meta` (health/config), `repos` (ingest/files), `jobs` (SSE progress), `chat` (conversations, SSE tokens) |
| `backend/ragbot/api/state.py` | Index cache (LRU), conversation store, job registry — keyed, not global |
| `backend/ragbot/api/jobs.py` | Background ingestion job: download → chunk → embed → index |
| `backend/ragbot/cli.py` | Command-line entry point over the same core pipeline |
| `frontend/src/lib/api.ts` | Typed fetch client, including the two SSE-consuming generators |
| `frontend/src/lib/sse.ts` | SSE framing parser (used for both the job and chat streams) |
| `frontend/src/lib/citations.ts` | Parses `path:start-end` citations out of an answer for the clickable chips |
| `frontend/src/components/ChatPanel.tsx` | Streams an answer; renders tool calls as collapsible steps |
| `frontend/src/components/SourceViewer.tsx` | Opens a cited file, syntax-highlighted, scrolled to and highlighting the cited lines |

**Ingestion.** The repo zip is fetched once and every file is written to
`backend/data/repos/<owner>_<repo>_<branch>/`. That cache is what makes `read_file`, `list_files`, and the
API's file-tree/file-content endpoints possible, and it means re-runs don't re-download. Zip entries are
untrusted input, so paths are resolved and checked against the cache root before writing (zip-slip guard);
the same path-resolution helper (`AgentWrapper.safe_repo_path`) is reused, not reimplemented, by the
`/files/{path}` endpoint — that route is reachable by anyone who can call the API, not just the model.

File selection uses an **allowlist** of ~35 extensions plus `Dockerfile`/`Makefile`. A denylist would be
one missing entry away from feeding a binary to the indexer; an allowlist fails safe by skipping instead.
Vendored and generated directories (`node_modules`, `.venv`, `dist`, `target`, …), lockfiles, minified
bundles, and files over 200 KB are excluded.

**Retrieval.** Every chunk is indexed twice: keyword search over `chunk`/`symbol`/`filename` (lexical), and dense vectors (semantical).
Hybrid mode fuses the two ranked lists with reciprocal rank fusion.

**The agent** gets three tools, because one-shot similarity search answers "what does X do" but not
"where is X implemented":

- `search_code(query)` — hybrid retrieval over the chunk index
- `read_file(path, start_line, end_line)` — read the real file to confirm before explaining
- `list_files(subdirectory)` — orient in the repo structure

### Trade-offs made splitting into backend + frontend

Three decisions were made explicitly for a simpler single-instance demo, each with a stated upgrade path:

**1. Single-user state, in-process.** The index cache, conversation store, and job registry
(`backend/ragbot/api/state.py`) are plain Python objects keyed by `(repo_key, chunking, search_method)` /
`conversation_id` / `job_id` held by one `AppState` per process.
Today: one backend instance only, and conversations and jobs are lost on restart. 
What's missing for multi-user: those shared stores, plus auth and per-user
scoping: right now any client can read any `repo_key`/`conversation_id`.

**2. No Redis/RabbitMQ/Celery — jobs run via FastAPI `BackgroundTasks`.** Ingestion (download → chunk →
embed → index) runs as a background task in the same process, with progress polled
by the job registry and pushed to the client. That's two containers instead of four (Redis+RabbitMQ), and no
broker to operate for a demo. 
Cost: a job dies if the process restarts mid-ingestion, it can't be retried
or distributed across instances, and a big ingestion competes with request-serving CPU (although they run on different threads). 
Upgrade path: RQ or Celery with workers, behind the same `JobRegistry` interface.

**3. Gemini embeddings over the local model by default.** `EMBEDDING_PROVIDER=google` instead of `local`. 
Payoff: no torch in the dependency tree — the backend image is ~400MB instead
of the ~2.5GB `sentence-transformers` pulls in. 
Cost: **every chunk of every ingested repo is sent to Google**, and
indexing now needs network access and API spend instead of running fully offline. For private or
air-gapped code this is the wrong default;

---

## c. Production on a hyper-scaler

What this would need to run as a real service:

**Storage and retrieval.** Replace minsearch (local embeddings) with a managed vector database: pgvector on RDS/Cloud SQL if
Postgres is already in the stack, or Pinecone/Qdrant/Vertex AI Vector Search otherwise, with an Nearest Neighbour index
for scaling performance.
Move the repo cache and the embedding cache from local disk to S3/GCS so they're shared across
instances rather than rebuilt per container.

**Ingestion as a job.** Indexing a large repo takes minutes; it doesn't belong in a request. Push it to a
queue with workers (ECS/Cloud Run Jobs), and make it incremental. Re-embed only files whose
content hash changed, driven by a webhook on push, instead of re-processing the repo.

**Serving.** Containerized and split already. The remaining step is putting
state in Redis/Postgres behind the existing `AppState` interface, rather than in-process, so any backend
instance can serve any request and autoscale on request rate.

**Cost and safety.** Add query-level caching, per-user rate limits and token budgets. Keys move to Secrets
Manager. Add input validation on repo URLs and a repository size ceiling.

**Observability.** The JSON logs become structured traces (OpenTelemetry → Datadog/Cloud Trace), with
per-query latency, token spend, tool-call counts, and retrieval hit rates on dashboards. Run the
LLM-as-judge checklist against a fixed question set in CI and alert on regressions.

---

## d. RAG / LLM approach & decisions

### LLM selection

Gemini provides ample free tier requests to make this project work without token cost ramping up.

**Final choice:** `google-gla:gemini-2.5-flash`, via pydantic-ai. Configurable in `.env`:

| Option | Trade-off |
|---|---|
| **Gemini 2.5 Flash** (chosen) | Fast and realtively cheap, with a large context window that suits reading several source files in one turn. Requires a `GOOGLE_API_KEY`. |
| gemini-2.5-flash-lite | Cheapest of the 4.1 family and reliable at tool calling, but weaker at reasoning across several files. |
| Local model (Ollama etc.) | No API spend and fully offline, but project complexity scales out of bounds and tool-calling reliability drops sharply, and this agent depends on it. |

Because pydantic-ai takes provider-prefixed model strings, switching provider is a `.env` change rather
than a code change — `backend/ragbot/core/LLM.py` owns the default and reports a missing credential **by
name, before the first question** rather than failing mid-query. The same model backs the evaluation agent.


### Embedding model

**Final choice:** pluggable, defaulting to Gemini. Set in `.env`:

```
EMBEDDING_PROVIDER=google        # default: gemini-embedding-2, needs GOOGLE_API_KEY
EMBEDDING_PROVIDER=local         # free, offline, no key (pip install '.[local-embeddings]')
EMBEDDING_PROVIDER=openai        # text-embedding-3-small
EMBEDDING_MODEL=...              # optional override for whichever provider
EMBEDDING_DIMENSIONS=768         # google only; 128-3072, default 768
EMBEDDING_CACHE=0                # optional: disable the on-disk vector cache
```

| Option | Trade-off |
|---|---|
| **`gemini-embedding-2`** (default) | Retrieves noticeably better on code than the old local default, and needs no torch in the image (~400MB vs ~2.5GB). Needs `GOOGLE_API_KEY`, network at index time, and sends every chunk to Google. |
| `text-embedding-3-small` (supported) | Also handles code well, ~$0.02/1M tokens. Needs `OPENAI_API_KEY` and network. |
| local `multi-qa-distilbert-cos-v1` (supported, opt-in) | Free, offline, no key — the only fully air-gapped option. Trained for natural-language QA over prose, not source code, so it's the weakest of the three on retrieval quality; also the only one requiring `pip install '.[local-embeddings]'` (torch). |

All three are implemented behind one `Embedder` interface, so switching is a one-line `.env` change. Gemini
doesn't support the old `task_type` parameter for asymmetric query/document retrieval that some embedding
APIs expose; instead, `GeminiEmbedder` prefixes queries and documents with a task description
(`"task: search result | query: ..."` / `"... | document: ..."`), which maps directly onto the existing
`encode()` contract — a bare `str` is a query, a `list` is corpus documents. The embedding-cache namespace
includes the configured dimension (`google:gemini-embedding-2@768`), so changing `EMBEDDING_DIMENSIONS`
can't silently mix vectors of two different shapes in one store.

### Vector database — and why there isn't one

`minsearch` keeps TF-IDF and a numpy embedding matrix in memory and scores by brute-force cosine. Before
reaching for something bigger, it's worth knowing where the time actually goes. Measured on this repo
(112 chunks, 768-dim, local embeddings):

| step | time |
|---|---|
| chunking (tree-sitter) | 0.03s |
| fit TF-IDF index | 0.03s |
| **embed the corpus** | **7.5s** (~67ms/chunk) |

Extrapolating the search side to larger corpora:

| corpus | RAM | brute-force search | load cache from disk | embedding cost avoided |
|---|---|---|---|---|
| 5,000 chunks | 15 MB | 11.5 ms | 14 ms | ~5.6 min |
| 20,000 chunks | 61 MB | 46 ms | 32 ms | ~22 min |
| 100,000 chunks | 307 MB | 223 ms | 121 ms | ~1.9 hr |

At the scale this targets, search is ~11ms — imperceptible next to a multi-second LLM call. Embedding is
~99% of the repeatable cost. **A vector database would optimise the 11ms and leave the minutes untouched**,
so the useful move was to cache vectors, not to add an engine. For reference, `chromadb` wanted ~40
transitive packages (aiohttp, bcrypt, kubernetes, …) to speed up an operation that isn't slow.

**Options considered:** Chroma (embedded, but the heaviest dependency tree); LanceDB (embedded,
memory-mapped, built-in full-text search); sqlite-vec (tiny, but vector-only — minsearch would stay for
keyword); FAISS (index only, no metadata persistence); pgvector (needs a server, so not "fully local").

**When to revisit:** past roughly 50–100k chunks — several repos indexed together, or a large monorepo —
search crosses ~200ms and RAM passes 300MB. At that point **LanceDB** is the pick: it would replace *both*
halves of retrieval (`minsearch.Index` and `VectorSearch`) and do hybrid natively instead of us fusing by
hand.

### Persistence — a flat file, not a database

Vectors are cached to `backend/data/index/embeddings/<provider>_<model>/` as `vectors.npy` plus a
`keys.json` mapping. Re-indexing a cached repo drops from **17.6s to effectively zero**, with identical
results.

- **Content-addressed by `sha256(chunk_text)`, not keyed per repo.** The cache invalidates itself: edit one
  file and only its chunks are re-embedded (measured: 111 hits, 1 miss), and identical chunks — licence
  headers, boilerplate, empty `__init__.py` — are stored once, within and across repos. A per-repo snapshot
  would need an explicit cache-version constant and still go stale silently when the chunker changes.
- **Namespaced per model *and* dimension.** Gemini's default is 768-dim, OpenAI's is 1536-dim, and Gemini's
  own dimension is itself configurable (`EMBEDDING_DIMENSIONS`) — mixing any of these would be silent
  nonsense rather than a loud failure, so the dimension is part of the cache key, not just the model name.
- **`.npy` with `allow_pickle=False`, not `minsearch.save()`.** Both `Index` and `VectorSearch` offer
  pickle-based persistence, but pickling a fitted scikit-learn vectoriser is version-fragile and executes
  arbitrary code on load — to save 0.03s of refitting.
- **Only embeddings are cached; chunks are not.** Chunking takes 0.03s, so caching it would add
  invalidation logic to save nothing measurable.
- **Queries are not cached**, only corpus chunks — a one-off query would just bloat the store.
- **Atomic writes** (temp file + `os.replace`); a corrupt or desynchronised cache is detected on load and
  rebuilt rather than trusted.

Honest cost: the store grows without bound (~15MB per 5000 chunks) with **no pruning**, and concurrent
writers are last-writer-wins — safe, but a simultaneous session's additions can be lost.

### Orchestration framework

**Final choice:** `pydantic-ai` (slim, with the `openai` and `google` extras).

| Option | Trade-off |
|---|---|
| **pydantic-ai** (chosen) | Tools are plain Python functions — signature and docstring become the schema, so there's no separate tool spec to keep in sync. Structured outputs via pydantic models (used by the evaluation checklist), and a serialisable message history that the JSON logging depends on. Smaller and less abstracted than the alternatives. |
| LangChain / LangGraph | Largest ecosystem and prebuilt RAG chains, but heavy abstractions over what is ultimately a short tool loop, and more indirection to debug. |
| LlamaIndex | Strongest built-in RAG primitives (loaders, retrievers, indices) — but this project deliberately owns its chunking and retrieval, which is the interesting part. |
| Raw OpenAI SDK | Zero abstraction, but the tool loop, schema generation, and message serialisation all become hand-written. |

One dependency note worth recording: the project originally pinned `pydantic-ai`, the meta-package that
pulls in *every* provider SDK (logfire, mistralai, anthropic, …). Their conflicting OpenTelemetry
constraints resolved to a version missing a module `pydantic-ai` imports, breaking the install outright.
Switching to `pydantic-ai-slim[openai]` — only what's used — fixed it.

### Chunking

Paragraph and markdown-heading splitting are meaningless for source code: they cut functions in half and
strand a body from its signature. Chunks are therefore cut at **real syntactic boundaries** — one function,
method, or class per chunk, signature and docstring intact.

**Options considered:** tree-sitter AST (chosen); Python's stdlib `ast` (no new dependency, but real
structure only for `.py`, and most repos aren't Python); universal line windows (simplest, but splits
functions mid-body).

- **Multi-language.** `tree-sitter-language-pack` covers Python, JS/TS, Go, Rust, Java, Kotlin, Ruby, PHP,
  C/C++, Swift, Scala, and Bash. Node type names differ per grammar (`function_definition` in Python,
  `function_declaration` in Go, `function_item` in Rust), so the type map was read off the actual parsers
  rather than assumed.
- **Qualified symbols.** A method chunk is named `ClassName.method_name`, so symbol search resolves.
- **Large containers split.** A class over 120 lines becomes a header chunk plus one chunk per method;
  smaller classes stay whole, since they read better that way.
- **Module-level code is kept.** Imports and top-level constants become their own chunk — that's where
  dependency and configuration questions get answered.
- **Everything degrades, nothing crashes.** Unsupported grammar (C# isn't bundled), a syntax error, or an
  oversized node falls back to overlapping line windows. One bad file must never sink a repo's ingestion.

Each chunk is embedded with a context header — `# path | language | Symbol (kind) | L12-34` — so the
vector actually sees the path and symbol name, which is what people search for.

Markdown keeps heading-based chunking, with line numbers so its citations link like code does.
`AUTO` dispatches per file, because a repo contains both.

### Retrieval approach

Keyword search nails exact identifiers; vector search handles "how does authentication work". Hybrid runs
both and fuses by **reciprocal rank fusion** (`1/(60+rank)`), so a chunk both retrievers like outranks one
that only scored well in a single list. The earlier concatenate-and-dedupe approach always put every
keyword hit above every vector hit regardless of relevance.

### Prompt & context management

The system prompt tells the agent to search first, confirm with `read_file` before explaining, follow
references across files, and cite `path:line` for every claim. Tool output is capped — 400 lines per
`read_file`, 300 entries per `list_files`, 5 search results — so a single call can't swallow the context
window. When the repo URL is parseable, GitHub blob-link instructions are appended so citations become
clickable.

### Guardrails

**Prompt-level:** never invent files/functions/APIs; say plainly when something isn't in the repo; label
inference as inference; decline off-repo questions.

**Code-level:** `read_file` and `list_files` resolve paths and reject anything outside the cache root, and
the same guard covers zip extraction (zip-slip). Both are covered by tests. Tool output caps bound context
growth. The allowlist bounds what can enter the index at all.

### Quality controls

`AgentLog.evaluate_log_record` runs an **LLM-as-judge** checklist over a logged run: instruction following,
relevance, clarity, citations, completeness, whether search was actually called, and whether every claim is
grounded in retrieved code. `python -m ragbot.cli --evaluate` scores the answer you just got, and
`Prompts.QUESTION_GENERATION_PROMPT` generates test questions from the corpus to evaluate in bulk.

**189 tests total.** Backend (`backend/tests`, 155 tests, pytest): chunking across six languages and its
fallback paths, file selection, path-traversal rejection, RRF ordering, embedding-cache correctness (reuse,
invalidation, model isolation, corruption recovery, per-dimension namespacing), model/credential resolution,
the Gemini embedding provider (query/document prefixes, batching, retries), the `agent.iter()`-based SSE
event stream (tokens, tool calls, citations, done, history continuity), and the full FastAPI surface via
`httpx.ASGITransport` — every route, the job lifecycle (`pending → running → succeeded`/`failed`), SSE
framing, 404s, and path traversal through `/files/{path}`. Frontend (`frontend/src`, 34 tests, vitest):
citation parsing (bare and markdown-link forms, including the piece with real logic — segmenting an answer
into text/citation runs) and SSE frame parsing (multi-chunk reassembly, malformed input).

### Observability

Every interaction is written to `backend/logs/*.json` with the full message trace, model, tools, and system
prompt — enough to replay or evaluate any answer after the fact. `GET /api/repos/{key}` reports ingestion
stats (files per language, chunk count) computed once at ingest time, and the ingestion job's SSE stream
reports named phases (`downloading → chunking → embedding → indexing → ready`) instead of an indeterminate
spinner.

> _Gap worth naming: there are no latency or token-spend metrics yet, and nothing aggregates the logs._

---

## e. Key technical decisions and why

> The decisions and their trade-offs are documented in section (d). This section is for **your** reasoning:
> what you weighed, what you rejected, and what you'd defend in an interview.

| Decision | Made | Your reasoning |
|---|---|---|
| Option 2 (Code Documentation Assistant) | | |
| FastAPI + Next.js split (from a Streamlit monolith) | | |
| tree-sitter AST chunking over simpler splitting | | |
| Gemini embeddings by default, local/OpenAI opt-in | | |
| minsearch + flat-file cache over a vector DB | | |
| Three agent tools rather than one-shot retrieval | | |
| pydantic-ai as orchestrator | | |
| Gemini 3.5 Flash as default chat model | | |
| In-process state + `BackgroundTasks` over Redis/Celery | | |

---

## f. Engineering standards followed (and skipped)

**In place, and verifiable in the repo:**

- 189 tests (155 backend + 34 frontend) covering chunking, ingestion, retrieval fusion, the embedding
  cache, path-traversal guards, the full FastAPI surface (every route, SSE framing, the job lifecycle), and
  the frontend's citation/SSE parsing logic
- `backend/Dockerfile` + `frontend/Dockerfile` + `docker-compose.yml`; `.github/workflows/ci.yml` runs both
  test suites (backend pytest, frontend lint + typecheck + vitest + build) on every push/PR
- Separation of concerns — ingestion, chunking, embedding, retrieval, agent, and now the API/state layer
  each own one module; `backend/ragbot/core` has zero HTTP/FastAPI imports, so the CLI and the API share
  the exact same pipeline
- Strategy pattern for chunking and retrieval, so alternatives are swappable and comparable
- Dependency injection (`Embedder`, `SearchStrategy` passed in) — which is what makes the tests fast and
  network-free; the API tests fake the same seams (a fake `requests.get`, a fake embedder, a fake
  `FunctionModel` chat model) rather than mocking framework internals
- Configuration via `.env` with a committed `.env.example` per service; no secrets in source
- Security guards on all untrusted input (zip entries, agent-supplied paths, the `/files/{path}` API route
  reusing the same path-resolution helper as the agent tool), each with tests
- Failure isolation — one unparseable file degrades to line windows instead of failing ingestion; a failed
  ingestion job reports `status: "failed"` with the error rather than crashing the process
- Keyed, not global, server-side state (index cache, conversation store, job registry) — an explicit
  substitution path to Redis/Postgres, see the trade-offs in section b
- Atomic writes for anything persisted
- Full TypeScript strictness on the frontend (`tsc --noEmit` is part of CI); ESLint (`eslint-config-next`)
  clean
- Comments explain *why*, not *what*

**Deliberately skipped, and why:**

- **No Python type checking** (mypy/pyright) and only partial type hints on the backend — the frontend is
  fully typed, the backend isn't.
- **No linter/formatter config** (ruff/black) committed for the backend.
- **No structured logging or metrics** — JSON traces only.
- **No integration test against a live LLM** — the agent's streaming loop is tested against pydantic-ai's
  `FunctionModel` (a fake that exercises the real `agent.iter()`/event-stream mechanics with no network),
  so tool wiring and SSE framing are covered but answer *quality* isn't asserted automatically. A live
  end-to-end smoke test was planned but blocked mid-build by hitting the Google Cloud project's spend cap.
- **No production database** — see the single-user-state trade-off in section b; the substitution path
  exists but isn't built.
- **`docker compose up --build` is untested** — the Dockerfiles and compose file are written and reviewed
  carefully, but this environment didn't have Docker installed to actually run them.

> _Your take: which of these were conscious trade-offs for the time budget versus things you'd never ship
> without, and what your normal bar looks like._

---

## g. How I used AI tools in my development process

> This section must be in your own words — it's explicitly what the assignment is screening for.
> Prompts to cover:

- **Which tools**, and for what parts of the work.
- **What you delegated vs. wrote or specified yourself** — and where you drew that line.
- **How you verified the output.** (Worth mentioning: several decisions here were settled by *measuring*
  rather than accepting a plausible suggestion — the vector-database question was decided by benchmarking
  search at 11ms against embedding at 7.5s, and the tree-sitter node-type map was read off the real parsers
  after an assumed one would have been wrong for Go and C#.)
- **Bugs AI introduced or missed**, and how you caught them.
- **How you keep AI-assisted code consistent with your own style** and maintainable by others.
- **Your do's and don'ts.**

---

## h. What I'd do differently with more time

> Your own priorities and judgement. The technical backlog below is scope, not judgement — pick from it,
> reorder it, and say what you'd actually change about the *approach*.

Technical backlog, roughly in the order I'd tackle it:

1. Actually run `docker compose up --build` end to end — written and reviewed, not yet verified, since this
   environment had no Docker installed.
2. Redis/Postgres behind `AppState`'s existing interface, so the backend can run more than one instance.
3. Benchmark Gemini 3.5 Flash against 3.7 Flash on the evaluation checklist before settling the default.
4. Prune the embedding cache (LRU cap or a `--clear-cache` command); it currently grows unbounded.
5. A fixed evaluation question set wired into CI, so retrieval changes are measured rather than eyeballed —
   the CI pipeline exists now, this just isn't in it yet.
6. Re-ingest only files whose content hash changed (the embedding cache already makes this cheap;
   ingestion just doesn't check yet).
7. A cross-file symbol graph, so "who calls this?" is answered by resolution rather than search.
8. RQ/Celery workers behind the `JobRegistry` interface, so ingestion survives a backend restart.

---

## Screenshots & demo

> Add screenshots to `docs/screenshots/` and link them here. Worth capturing:
>
> - The ingest dialog and its named-phase progress (`downloading → chunking → embedding → indexing → ready`)
> - A chat answer with clickable `path:start-end` citation chips
> - Clicking a citation opening the source viewer, scrolled to and highlighting the cited lines
> - An answer where the agent's tool calls are visible as collapsible steps (`search_code`, `read_file`)
> - The file tree, browsing the ingested repo directly
> - Optionally a short screen recording of one end-to-end run

```
![Pipeline complete](docs/screenshots/pipeline.png)
![Cited answer](docs/screenshots/answer.png)
```

---

## Known limitations

- **No cross-file symbol graph.** The agent follows references by reading files, not by resolving symbols;
  "who calls this function?" is answered by search, not by a call graph.
- **Retrieval is chunk-local.** A function split across the 120-line threshold can lose surrounding context.
- **C# and other unbundled grammars** fall back to line windows, so their chunks have no symbol names.
- **Only the default branch** of a repo is ingested, and only via public `codeload` zip URLs — no auth,
  no private repos, no incremental git clone.
- **Ingestion is all-or-nothing.** Re-ingesting re-downloads and re-chunks everything; only the embeddings
  are reused.
- **In-process, single-instance state.** The index cache, conversations, and jobs live in the backend
  process's memory, so a restart loses conversations and in-flight jobs (rebuilding an index is cheap,
  since embeddings are cached — see the trade-offs in section b). The backend can't run more than one
  instance as-is.
- **The embedding cache never shrinks**, and concurrent writers are last-writer-wins (safe, but a
  simultaneous session's additions can be lost).
- **Binary and generated files are skipped entirely**, so questions about assets or build output can't be
  answered.
- **Local embeddings (the `EMBEDDING_PROVIDER=local` opt-in) are the weakest link** in retrieval quality of
  the three providers — see the embedding section. Gemini, the default, doesn't have this problem, at the
  cost of sending code to Google.
- **Gemini 3.5 Flash** is cheap and fast, but a larger model reasons better over multi-file questions.
  `LLM_MODEL` in `.env` switches it; 3.7 Flash is the newer, more agentic option and is untested here.
- **Live end-to-end verification is incomplete.** The full pipeline was verified against the real Gemini
  API for chat/embeddings during development, but the Google Cloud project hit its monthly spend cap
  mid-session; everything since then (the FastAPI layer, the frontend, the SSE streaming contract) is
  verified with fakes at every network/LLM boundary rather than a live run. `agent.iter()`'s streaming API
  — the plan's highest-uncertainty item — was specifically confirmed against pydantic-ai 1.0.9 before the
  cap was hit.
