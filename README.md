# RAGBot

An LLM-powered RAG agent that ingests a GitHub repository — **source code and documentation** — and
answers questions about it: how it works, where functionality lives, what the APIs and dependencies are.

---

## Quick setup

**Requirements:** Python 3.13+ and an OpenAI API key (used for the chat model; embeddings run locally by default).

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
OPENAI_API_KEY=sk-...
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

## Architecture

```
GitHub zip ──► Repository ──► chunkers ──► SearchStrategy ──► AgentWrapper ──► Streamlit / CLI
                   │                            │                  │
              data/repos/                  minsearch          pydantic-ai
            (source mirror)           (TF-IDF + vectors)    (3 tools, gpt-4.1-nano)
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

## RAG / LLM approach & decisions

### Chunking — tree-sitter AST

Paragraph and markdown-heading splitting are meaningless for source code: they cut functions in half and
strand a body from its signature. Chunks are therefore cut at **real syntactic boundaries** — one function,
method, or class per chunk, signature and docstring intact.

- **Multi-language.** `tree-sitter-language-pack` covers Python, JS/TS, Go, Rust, Java, Kotlin, Ruby, PHP,
  C/C++, Swift, Scala, and Bash. Node type names differ per grammar (`function_definition` in Python,
  `function_declaration` in Go, `function_item` in Rust), so the type map was read off the actual parsers
  rather than assumed.
- **Qualified symbols.** A method chunk is named `ClassName.method_name`, so symbol search resolves.
- **Large containers split.** A class over 120 lines is split into a header chunk plus one chunk per
  method; smaller classes stay whole, since they read better that way.
- **Module-level code is kept.** Imports and top-level constants become their own chunk — that's where
  dependency and configuration questions get answered.
- **Everything degrades, nothing crashes.** Unsupported grammar (C# isn't bundled), a syntax error, or an
  oversized node falls back to overlapping line windows. One bad file must never sink a repo's ingestion.

Each chunk is embedded with a context header — `# path | language | Symbol (kind) | L12-34` — so the
vector actually sees the path and symbol name, which is what people search for.

Markdown keeps heading-based chunking, now with line numbers so its citations link like code does.
`AUTO` dispatches per file, because a repo contains both.

### Embedding model — pluggable, local by default

Set in `.env`:

```
EMBEDDING_PROVIDER=local     # default: free, offline, no API spend
EMBEDDING_PROVIDER=openai    # text-embedding-3-small
EMBEDDING_MODEL=...          # optional override for either provider
EMBEDDING_CACHE=0            # optional: disable the on-disk vector cache
```

The default is local `sentence-transformers` (`multi-qa-distilbert-cos-v1`) so the app runs with no
embedding spend. **Retrieval is noticeably better with `EMBEDDING_PROVIDER=openai`** — that model was
trained for natural-language QA over prose, not source code, whereas `text-embedding-3-small` handles
code well and costs roughly $0.02 per million tokens (cents for a typical repo). If you're evaluating
retrieval quality, switch it on; if you're just running it, local is fine.

### Vector store — minsearch, and why not a vector database

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

### Persistence — a flat file, not a database

Vectors are cached to `data/index/embeddings/<provider>_<model>/` as `vectors.npy` plus a `keys.json`
mapping. Re-indexing a cached repo drops from **17.6s to effectively zero**, with identical results.

The decisions inside that, and what they cost:

- **Content-addressed by `sha256(chunk_text)`, not keyed per repo.** The cache invalidates itself: edit one
  file and only its chunks are re-embedded (measured: 111 hits, 1 miss), and identical chunks — licence
  headers, boilerplate, empty `__init__.py` — are stored once, within and across repos. The alternative,
  a per-repo snapshot, needs an explicit cache-version constant and still goes stale silently when the
  chunker changes.
- **Namespaced per model.** Local vectors are 768-dim and OpenAI's are 1536-dim; mixing them would be
  silent nonsense rather than a loud failure. Switching provider builds a separate cache, so you pay the
  embedding cost once per model, not once per switch.
- **`.npy` with `allow_pickle=False`, not `minsearch.save()`.** Both `Index` and `VectorSearch` offer
  pickle-based persistence, but pickling a fitted scikit-learn vectoriser is version-fragile and executes
  arbitrary code on load — to save 0.03s of refitting. Persisting plain data and rebuilding the indexes in
  memory is safer and, at these sizes, free.
- **Only embeddings are cached; chunks are not.** Chunking takes 0.03s, so caching it would add
  invalidation logic to save nothing measurable.
- **Queries are not cached**, only corpus chunks — a one-off query would just bloat the store.
- **Atomic writes** (temp file + `os.replace`), so a crash or a second Streamlit session can't leave a
  torn cache. A desynchronised or corrupt cache is detected on load and rebuilt rather than trusted.

Costs and limits, honestly: the store grows without bound (~15MB per 5000 chunks) and has **no pruning** —
it wants an LRU cap or a `--clear-cache` command eventually. Concurrent writers are last-writer-wins, which
loses additions but never corrupts. Set `EMBEDDING_CACHE=0` in `.env` to disable it.

**When to revisit this:** past roughly 50–100k chunks — several repos indexed together, or a large
monorepo — search crosses ~200ms and RAM passes 300MB. At that point I'd move to **LanceDB**: embedded, no
server, memory-mapped rather than fully resident, and it has built-in full-text search, so it would replace
*both* halves of retrieval (`minsearch.Index` and `VectorSearch`) and do hybrid natively instead of us
fusing by hand. sqlite-vec is vector-only, so minsearch would stay for keyword; faiss stores no metadata,
so payload persistence becomes your problem.

### Retrieval — hybrid with reciprocal rank fusion

Keyword search nails exact identifiers; vector search handles "how does authentication work". Hybrid runs
both and fuses by rank (`1/(60+rank)`), so a chunk both retrievers like outranks one that only scored
well in a single list. The earlier concatenate-and-dedupe approach always put every keyword hit above
every vector hit regardless of relevance.

### Prompt & context management

The system prompt tells the agent to search first, confirm with `read_file` before explaining, follow
references across files, and cite `path:line` for every claim. Tool output is capped — 400 lines per
`read_file`, 300 entries per `list_files`, 5 search results — so a single call can't swallow the context
window. When the repo URL is parseable, GitHub blob-link instructions are appended so citations become
clickable.

### Guardrails

Prompt-level: never invent files/functions/APIs, say plainly when something isn't in the repo, label
inference as inference, and decline off-repo questions. Code-level: both `read_file` and `list_files`
resolve paths and reject anything outside the cache root, and the same guard covers zip extraction.

### Quality & observability

Every interaction is written to `logs/*.json` with the full message trace, model, tools, and system
prompt. `AgentLog.evaluate_log_record` runs an **LLM-as-judge** checklist over a logged run — instruction
following, relevance, clarity, citations, completeness, whether search was actually called, and whether
every claim is grounded in retrieved code. `main.py --evaluate` runs it on the answer you just got, and
`Prompts.QUESTION_GENERATION_PROMPT` generates test questions from the corpus to evaluate in bulk.

80 tests cover chunking across six languages, the fallback paths, file selection, path-traversal
rejection, RRF ordering, and the metadata-preservation regressions.

---

## Productionizing on a hyper-scaler

What this would need to run as a real service:

**Storage and retrieval.** Replace minsearch with a managed vector database — pgvector on RDS/Cloud SQL if
Postgres is already in the stack, or Pinecone/Qdrant/Vertex AI Vector Search otherwise — with an ANN index
so query latency stops scaling linearly with corpus size. Keep the keyword half in OpenSearch and fuse as
now. Move the repo cache from local disk to S3/GCS so it's shared across instances.

**Ingestion as a job.** Indexing a large repo takes minutes; it doesn't belong in a request. Push it to a
queue (SQS/Pub-Sub) with workers (ECS/Cloud Run Jobs), and make it incremental — re-embed only files whose
content hash changed, driven by a webhook on push, instead of re-processing the repo.

**Serving.** Containerize (a Dockerfile is a known gap), split the Streamlit UI from a stateless FastAPI
backend, and put state in Redis/Postgres rather than `st.session_state` so any instance can serve any
request. Autoscale on queue depth and request rate.

**Cost and safety.** Cache embeddings by content hash; cache identical queries. Add per-user rate limits
and token budgets. Keys move to Secrets Manager. Add input validation on repo URLs and a size ceiling.

**Observability.** The JSON logs become structured traces (OpenTelemetry → Datadog/Cloud Trace), with
per-query latency, token spend, tool-call counts, and retrieval hit rates on dashboards. Run the
LLM-as-judge checklist against a fixed question set in CI and alert on regressions.

---

## Known limitations

- **No incremental re-indexing.** Re-ingesting a repo redoes everything from scratch.
- **No cross-file symbol graph.** The agent follows references by reading files, not by resolving symbols;
  "who calls this function?" is answered by search, not by a call graph.
- **Retrieval is chunk-local.** A function split across the 120-line threshold can lose surrounding context.
- **C# and other unbundled grammars** fall back to line windows, so their chunks have no symbol names.
- **Only the default branch** of a repo is ingested, and only via public `codeload` zip URLs — no auth,
  no private repos, no incremental git clone.
- **In-memory state.** Chunks and the fitted indexes live in the Streamlit session, so restarting rebuilds
  them — cheaply, since the embeddings themselves are cached to disk. Session state also means the app is
  single-instance; it can't be horizontally scaled as-is.
- **The embedding cache never shrinks.** No pruning or size cap yet, and concurrent writers are
  last-writer-wins (safe, but a simultaneous session's additions can be lost).
- **Binary and generated files are skipped entirely**, so questions about assets or build output can't be
  answered.
- **gpt-4.1-nano** is the default chat model — cheap and fast, but a stronger model reasons better over
  multi-file questions.

## What's next

1. Containerize (Dockerfile + compose) — the clearest gap against the brief.
2. Prune the embedding cache (LRU cap or a `--clear-cache` command); it currently grows unbounded.
3. A fixed evaluation question set wired into CI, so retrieval changes are measured rather than eyeballed.
4. Streaming responses, and surfacing retrieved sources in the UI alongside the answer.
5. Re-ingest only files whose content hash changed, so updating a repo skips untouched files entirely
   (the embedding cache already makes this cheap; ingestion just doesn't check yet).

---

## Notes for the author

> The following sections are required by the assignment and are deliberately left blank — they ask for
> *your* reasoning and process, which shouldn't be written by an LLM. Delete this note once filled in.

### Key technical decisions I made and why

_(The decisions are documented above; this section is for why you made them — what you traded off, what
you rejected, what you'd defend in an interview.)_

### Engineering standards I followed (and some I skipped)

_(e.g. what you test and what you deliberately don't, typing, error handling, commit hygiene, what you
cut for time.)_

### How I used AI tools in my development process

_(Which tools, what you delegated vs. wrote yourself, how you verified output, your do's and don'ts, how
you keep AI-assisted code maintainable and consistent with your own style.)_

### What I'd do differently with more time

_(Your own priorities — the "What's next" list above is technical scope, not judgement.)_
