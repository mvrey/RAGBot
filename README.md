# RAGBot — Code Documentation Assistant

An LLM-powered RAG agent that ingests a GitHub repository — **source code and documentation** — and
answers questions about it: how it works, where functionality lives, what the APIs and dependencies are.

Built for **Option 2: Code Documentation Assistant**.

| Assignment requirement | Section |
|---|---|
| a. Quick setup instructions | [a. Quick setup](#a-quick-setup) |
| b. Architecture overview | [b. Architecture overview](#b-architecture-overview) |
| c. Productionizing on a hyper-scaler | [c. Productionizing](#c-productionizing-on-a-hyper-scaler) |
| d. RAG/LLM approach & decisions | [d. RAG / LLM approach & decisions](#d-rag--llm-approach--decisions) |
| e. Key technical decisions and why | [e. Key technical decisions](#e-key-technical-decisions-and-why) |
| f. Engineering standards followed / skipped | [f. Engineering standards](#f-engineering-standards-followed-and-skipped) |
| g. How I used AI tools | [g. AI tools in development](#g-how-i-used-ai-tools-in-my-development-process) |
| h. What I'd do differently with more time | [h. With more time](#h-what-id-do-differently-with-more-time) |
| Screenshots / video | [Screenshots & demo](#screenshots--demo) |

Also: [Known limitations](#known-limitations).

---

## a. Quick setup

**Requirements:** Python 3.13+ and a **Google Gemini API key** ([get one here](https://aistudio.google.com/apikey)) for the chat model. Embeddings run locally by default, so no OpenAI key is needed unless you switch the embedding provider or the chat model.

```bash
# 1. Create a virtual environment
python -m venv .venv
.venv\Scripts\Activate.ps1        # Windows PowerShell
# source .venv/bin/activate       # Linux / macOS

# 2. Install dependencies
pip install -e .

# 3. Configure your API key
cp .env.example .env              # then edit .env and add your key
```

`.env` must contain at least:

```
GOOGLE_API_KEY=...
```

**Run the web app** (from the `ragbot/` directory, which is where the `src.*` imports resolve):

```bash
cd ragbot
streamlit run app.py
```

Then work through the pipeline in the UI: **Download Repo → Chunk → Index → Initialize Agent**, and chat.
Already-downloaded repos can be re-loaded from disk with **Load Cached Repo**, skipping the network fetch.

**Or use the CLI:**

```bash
cd ragbot
python main.py --question "How does hybrid search combine results?"
python main.py --repo <codeload-zip-url> --question "..." --cached --evaluate
```

Repo URLs are `codeload.github.com` zip links, e.g.
`https://codeload.github.com/<owner>/<repo>/zip/refs/heads/main`.

**Run the tests:**

```bash
pytest
```

---

## b. Architecture overview

```
GitHub zip ──► Repository ──► chunkers ──► SearchStrategy ──► AgentWrapper ──► Streamlit / CLI
                   │                            │                  │
              data/repos/                  minsearch          pydantic-ai
            (source mirror)           (TF-IDF + vectors)   (3 tools, Gemini Flash)
                   │                            │                  │
                   │                     data/index/               │
                   │                  (embedding cache)            │
                   │                                               │
                   └──────────── read_file / list_files ───────────┘
                                                                   │
                                                             logs/*.json
                                                          (+ LLM-as-judge eval)
```

`data/repos/` is a faithful mirror of the repository; `data/index/` holds derived
artefacts. They are kept apart deliberately — ingestion and the agent's `list_files`
both walk the repo tree, and would otherwise pick up cache files as source code.

| Module | Responsibility |
|---|---|
| `src/Repository.py` | Downloads the repo zip, filters files, mirrors them to an on-disk cache, dispatches chunking |
| `src/CodeChunker.py` | tree-sitter AST chunking; falls back to line windows |
| `src/TextChunker.py` | Markdown/prose chunking (headings, paragraphs, sliding window, LLM) |
| `src/ChunkingStrategy.py` | Strategy enum; `AUTO` dispatches per file type |
| `src/Embeddings.py` | Pluggable embedding providers (local / OpenAI) and the on-disk vector cache |
| `src/LLM.py` | Chat-model selection from `.env`, and up-front credential checks |
| `src/AsyncRunner.py` | One long-lived event loop, so pooled HTTP connections survive between turns |
| `src/TextSearcher.py` | Keyword, vector, and hybrid (RRF) retrieval over minsearch |
| `src/SearchStrategy.py` | Retrieval-mode dispatch |
| `src/AgentWrapper.py` | pydantic-ai agent and its three tools |
| `src/Prompts.py` | System prompt, evaluation checklist, question generation |
| `src/AgentLog.py` | Per-interaction JSON logs and LLM-as-judge scoring |

**Ingestion.** The repo zip is fetched once and every file worth indexing is written to
`ragbot/data/repos/<owner>_<repo>_<branch>/`. That cache is what makes `read_file` and `list_files`
possible, and it means re-runs don't re-download. Zip entries are untrusted input, so paths are resolved
and checked against the cache root before writing (zip-slip guard).

File selection uses an **allowlist** of ~35 extensions plus `Dockerfile`/`Makefile`. A denylist would be
one missing entry away from feeding a binary to the indexer; an allowlist fails safe by skipping instead.
Vendored and generated directories (`node_modules`, `.venv`, `dist`, `target`, …), lockfiles, minified
bundles, and files over 200 KB are excluded.

**Retrieval.** Every chunk is indexed twice — TF-IDF over `chunk`/`symbol`/`filename`, and dense vectors —
and hybrid mode fuses the two ranked lists with reciprocal rank fusion.

**The agent** gets three tools, because one-shot similarity search answers "what does X do" but not
"where is X implemented":

- `search_code(query)` — hybrid retrieval over the chunk index
- `read_file(path, start_line, end_line)` — read the real file to confirm before explaining
- `list_files(subdirectory)` — orient in the repo structure

---

## c. Productionizing on a hyper-scaler

What this would need to run as a real service:

**Storage and retrieval.** Replace minsearch with a managed vector database — pgvector on RDS/Cloud SQL if
Postgres is already in the stack, or Pinecone/Qdrant/Vertex AI Vector Search otherwise — with an ANN index
so query latency stops scaling linearly with corpus size. Keep the keyword half in OpenSearch and fuse as
now. Move the repo cache and the embedding cache from local disk to S3/GCS so they're shared across
instances rather than rebuilt per container.

**Ingestion as a job.** Indexing a large repo takes minutes; it doesn't belong in a request. Push it to a
queue (SQS/Pub-Sub) with workers (ECS/Cloud Run Jobs), and make it incremental — re-embed only files whose
content hash changed, driven by a webhook on push, instead of re-processing the repo.

**Serving.** Containerize (a Dockerfile is a known gap), split the Streamlit UI from a stateless FastAPI
backend, and put state in Redis/Postgres rather than `st.session_state` so any instance can serve any
request. Autoscale on queue depth and request rate.

**Cost and safety.** The content-addressed embedding cache already exists and would port directly to a
shared object store. Add query-level caching, per-user rate limits and token budgets. Keys move to Secrets
Manager. Add input validation on repo URLs and a repository size ceiling.

**Observability.** The JSON logs become structured traces (OpenTelemetry → Datadog/Cloud Trace), with
per-query latency, token spend, tool-call counts, and retrieval hit rates on dashboards. Run the
LLM-as-judge checklist against a fixed question set in CI and alert on regressions.

---

## d. RAG / LLM approach & decisions

### LLM selection

**Final choice:** `google-gla:gemini-3.5-flash`, via pydantic-ai. Configurable in `.env`:

```
LLM_MODEL=google-gla:gemini-3.5-flash   # default
LLM_MODEL=google-gla:gemini-3.7-flash   # newest Flash, tuned for agentic/coding work
LLM_MODEL=openai:gpt-4.1-nano           # previous default
```

| Option | Trade-off |
|---|---|
| **Gemini 3.5 Flash** (chosen) | Fast and cheap, with a large context window that suits reading several source files in one turn. Requires a `GOOGLE_API_KEY`. |
| Gemini 3.7 Flash | Google positions it explicitly for "complex coding, agentic workflows, and reliable multi-step execution" — the closest fit to this use case. One line to switch, and worth benchmarking against 3.5. |
| gpt-4.1-nano (previous) | Cheapest of the 4.1 family and reliable at tool calling, but weaker at reasoning across several files. |
| Local model (Ollama etc.) | No API spend and fully offline, but tool-calling reliability drops sharply, and this agent depends on it. |

Because pydantic-ai takes provider-prefixed model strings, switching provider is a `.env` change rather
than a code change — `src/LLM.py` owns the default and reports a missing credential **by name, before the
first question** rather than failing mid-query. The same model backs the evaluation agent.

**One trap worth recording**, since it only appears on the *second* message and so survives a quick smoke
test: `asyncio.run()` closes its event loop on return, but the Google and OpenAI clients underneath
pydantic-ai keep a persistent httpx connection pool bound to whichever loop first used it. A second
`asyncio.run()` therefore dies with `RuntimeError: Event loop is closed` as the pool touches the dead loop.
`src/AsyncRunner.py` keeps one loop alive on a dedicated thread for the process lifetime, which fixes it
and lets connections be reused across turns. The CLI hit the same bug between its answer and `--evaluate`
calls.

> _Your take: why Gemini Flash over the OpenAI default, and whether latency, cost, or context drove it._

### Embedding model

**Final choice:** pluggable, defaulting to local. Set in `.env`:

```
EMBEDDING_PROVIDER=local     # default: free, offline, no API spend
EMBEDDING_PROVIDER=openai    # text-embedding-3-small
EMBEDDING_MODEL=...          # optional override for either provider
EMBEDDING_CACHE=0            # optional: disable the on-disk vector cache
```

| Option | Trade-off |
|---|---|
| **local `multi-qa-distilbert-cos-v1`** (default) | Free, offline, no key needed. But trained for natural-language QA over prose, **not source code** — retrieval quality is the weakest link. |
| **`text-embedding-3-small`** (supported) | Handles code well, ~$0.02/1M tokens (cents per repo). Needs network and API spend at index time. |
| Local code-tuned model (e.g. jina-embeddings-v2-base-code) | Free *and* code-aware, but a large download and slow CPU embedding over a whole repo. Not wired up. |

Both providers are implemented behind one `Embedder` interface, so switching is a one-line `.env` change.
**Retrieval is noticeably better with `EMBEDDING_PROVIDER=openai`** — if you're assessing retrieval
quality, switch it on; if you're just running it, local is fine.

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

Vectors are cached to `data/index/embeddings/<provider>_<model>/` as `vectors.npy` plus a `keys.json`
mapping. Re-indexing a cached repo drops from **17.6s to effectively zero**, with identical results.

- **Content-addressed by `sha256(chunk_text)`, not keyed per repo.** The cache invalidates itself: edit one
  file and only its chunks are re-embedded (measured: 111 hits, 1 miss), and identical chunks — licence
  headers, boilerplate, empty `__init__.py` — are stored once, within and across repos. A per-repo snapshot
  would need an explicit cache-version constant and still go stale silently when the chunker changes.
- **Namespaced per model.** Local vectors are 768-dim and OpenAI's are 1536-dim; mixing them would be
  silent nonsense rather than a loud failure.
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

**Final choice:** `pydantic-ai` (slim, OpenAI extra only).

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
grounded in retrieved code. `main.py --evaluate` scores the answer you just got, and
`Prompts.QUESTION_GENERATION_PROMPT` generates test questions from the corpus to evaluate in bulk.

**119 tests** cover chunking across six languages and its fallback paths, file selection, path-traversal
rejection, RRF ordering, embedding-cache correctness (reuse, invalidation, model isolation, corruption
recovery), model/credential resolution, event-loop reuse, and the metadata-preservation regressions.

### Observability

Every interaction is written to `logs/*.json` with the full message trace, model, tools, and system prompt —
enough to replay or evaluate any answer after the fact. The UI reports ingestion stats (files per language,
chunk count), warns past the ~5000-chunk comfort limit, and shows embedding-cache hits vs misses per index.

> _Gap worth naming: there are no latency or token-spend metrics yet, and nothing aggregates the logs._

---

## e. Key technical decisions and why

> The decisions and their trade-offs are documented in section (d). This section is for **your** reasoning:
> what you weighed, what you rejected, and what you'd defend in an interview.

| Decision | Made | Your reasoning |
|---|---|---|
| Option 2 (Code Documentation Assistant) | | |
| Streamlit + Python (no separate frontend) | | |
| tree-sitter AST chunking over simpler splitting | | |
| Local embeddings by default, OpenAI opt-in | | |
| minsearch + flat-file cache over a vector DB | | |
| Three agent tools rather than one-shot retrieval | | |
| pydantic-ai as orchestrator | | |
| gpt-4.1-nano as default model | | |

---

## f. Engineering standards followed (and skipped)

**In place, and verifiable in the repo:**

- 94 tests covering chunking, ingestion, retrieval fusion, the embedding cache, and both security guards
- Separation of concerns — ingestion, chunking, embedding, retrieval, and agent each own one module
- Strategy pattern for chunking and retrieval, so alternatives are swappable and comparable
- Dependency injection (`Embedder`, `SearchStrategy` passed in) — which is what makes the tests fast and
  network-free
- Configuration via `.env` with a committed `.env.example`; no secrets in source
- Security guards on all untrusted input (zip entries, agent-supplied paths), each with tests
- Failure isolation — one unparseable file degrades to line windows instead of failing ingestion
- Atomic writes for anything persisted
- Comments explain *why*, not *what*

**Deliberately skipped, and why:**

- **No Dockerfile** — the clearest gap against the brief.
- **No CI pipeline** — tests run locally only.
- **No type checking** (mypy/pyright) and only partial type hints.
- **No linter/formatter config** (ruff/black) committed.
- **No structured logging or metrics** — JSON traces only.
- **No integration test against a live LLM** — the agent loop is tested with pydantic-ai's `TestModel`, so
  tool wiring is covered but answer quality isn't asserted automatically.

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

1. Containerize (Dockerfile + compose) — the clearest gap against the brief.
2. Benchmark Gemini 3.5 Flash against 3.7 Flash on the evaluation checklist before settling the default.
3. Prune the embedding cache (LRU cap or a `--clear-cache` command); it currently grows unbounded.
4. A fixed evaluation question set wired into CI, so retrieval changes are measured rather than eyeballed.
5. Streaming responses, and surfacing retrieved sources in the UI alongside the answer.
6. Re-ingest only files whose content hash changed (the embedding cache already makes this cheap;
   ingestion just doesn't check yet).
7. A cross-file symbol graph, so "who calls this?" is answered by resolution rather than search.

---

## Screenshots & demo

> Add screenshots to `docs/screenshots/` and link them here. Worth capturing:
>
> - The workflow controls with the pipeline complete (Repo ingested → Chunked → Indexed → Agent ready),
>   including the language breakdown and the embedding-cache hit/miss line
> - A chat answer showing `path:line` citations with clickable GitHub links
> - An answer where the agent used `read_file` or `list_files`, not just search
> - The advanced settings expander (chunking / search / system prompt)
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
- **In-memory session state.** Chunks and the fitted indexes live in the Streamlit session, so restarting
  rebuilds them — cheaply, since embeddings are cached. It also means the app is single-instance and can't
  be horizontally scaled as-is.
- **The embedding cache never shrinks**, and concurrent writers are last-writer-wins (safe, but a
  simultaneous session's additions can be lost).
- **Binary and generated files are skipped entirely**, so questions about assets or build output can't be
  answered.
- **Local embeddings are the weakest link** in retrieval quality — see the embedding section.
- **Gemini 3.5 Flash** is cheap and fast, but a larger model reasons better over multi-file questions.
  `LLM_MODEL` in `.env` switches it; 3.7 Flash is the newer, more agentic option and is untested here.
