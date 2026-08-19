"""In-process state: the index cache, the conversation store, and repo metadata.

Single-user, structured for multi-user: everything here is a keyed store rather
than a global, so swapping in Redis/Postgres later is a substitution behind the
same interface, not a rewrite. See docs/PLAN-fullstack-split.md section 6.
"""

import json
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import Request

from ragbot.core.AgentWrapper import AgentWrapper
from ragbot.core.Repository import Repository
from ragbot.core.settings import REPO_CACHE_DIR

MAX_INDEXES = 3
MAX_CONVERSATIONS = 50


@dataclass
class BuiltIndex:
    repository: Repository
    chunks: list
    search_strategy: Any
    agent_wrapper: AgentWrapper


class LRUCache(OrderedDict):
    """A dict that evicts the least-recently-used entry past `maxsize`."""

    def __init__(self, maxsize: int):
        super().__init__()
        self.maxsize = maxsize

    def get_fresh(self, key):
        if key not in self:
            return None
        self.move_to_end(key)
        return self[key]

    def put(self, key, value):
        self[key] = value
        self.move_to_end(key)
        while len(self) > self.maxsize:
            self.popitem(last=False)


class JobRegistry:
    """Tracks background job status. In-memory: jobs die with the process."""

    def __init__(self):
        self._jobs: dict[str, dict] = {}

    def create(self, kind: str) -> str:
        job_id = uuid.uuid4().hex
        self._jobs[job_id] = {
            'id': job_id,
            'kind': kind,
            'status': 'pending',
            'phase': None,
            'message': '',
            'error': None,
            'result': None,
            'created_at': time.time(),
            'version': 0,
            'progress': None,
            'cancelled': False,
        }
        return job_id

    def get(self, job_id: str) -> Optional[dict]:
        return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.update(fields)
        job['version'] += 1

    def cancel(self, job_id: str) -> bool:
        """Flag a job for cooperative cancellation.

        There's no hard interrupt for the worker-thread chunking/embedding calls
        already in flight, so the pipeline in jobs.py checks this flag between
        stages (and inside the chunk/embed progress callbacks) and unwinds itself
        rather than being killed from the outside.
        """
        job = self._jobs.get(job_id)
        if job is None or job['status'] in ('succeeded', 'failed'):
            return False
        job['cancelled'] = True
        return True


class ConversationStore:
    """Conversation history, keyed by conversation id. In-memory, LRU-capped."""

    def __init__(self, maxsize: int = MAX_CONVERSATIONS):
        self._store = LRUCache(maxsize)

    def create(self, repo_key: str) -> str:
        conv_id = uuid.uuid4().hex
        self._store.put(conv_id, {
            'id': conv_id,
            'repo_key': repo_key,
            'pydantic_ai_history': None,
            'messages': [],
            'created_at': time.time(),
        })
        return conv_id

    def get(self, conv_id: str) -> Optional[dict]:
        return self._store.get_fresh(conv_id)

    def clear(self, conv_id: str) -> bool:
        conv = self._store.get_fresh(conv_id)
        if conv is None:
            return False
        conv['pydantic_ai_history'] = None
        conv['messages'] = []
        return True

    def append_turn(self, conv_id: str, *, question: str, answer: str, citations: list, history) -> None:
        conv = self._store.get_fresh(conv_id)
        if conv is None:
            return
        conv['pydantic_ai_history'] = history
        conv['messages'].append({'role': 'user', 'content': question, 'citations': []})
        conv['messages'].append({'role': 'assistant', 'content': answer, 'citations': citations})


class AppState:
    """Everything the API needs beyond a single request: caches and registries."""

    def __init__(self):
        self.indexes: LRUCache[tuple, BuiltIndex] = LRUCache(MAX_INDEXES)
        self.jobs = JobRegistry()
        self.conversations = ConversationStore()

    def get_or_build_index(self, repo_key: str) -> BuiltIndex:
        """Fetch a repo's cached index, or build it from disk.

        Synchronous and CPU-bound (chunking, and an embedding-cache lookup that
        may hit the network on a cold cache) - callers running in the event loop
        must wrap this in anyio.to_thread.run_sync, per the blocking-work rule
        in docs/PLAN-fullstack-split.md section 6.
        """
        from ragbot.core.AgentWrapper import AgentWrapper
        from ragbot.core.ChunkingStrategy import ChunkingStrategy
        from ragbot.core.Embeddings import get_embedder
        from ragbot.core.Prompts import Prompts
        from ragbot.core.SearchStrategy import SearchStrategy, SearchStrategyType

        meta = read_repo_meta(repo_key)
        if meta is None:
            raise KeyError(f"No cached repo for key '{repo_key}'.")
        chunking_name = meta.get('chunking_strategy')
        search_method_name = meta.get('search_method')
        if not chunking_name or not search_method_name:
            raise KeyError(f"Repo '{repo_key}' has not finished ingesting yet.")

        index_key = (repo_key, chunking_name, search_method_name)
        cached = self.indexes.get_fresh(index_key)
        if cached is not None:
            return cached

        repository = Repository(meta['repo_url'])
        repository.load_cached_repo_files()
        chunks = repository.chunk(ChunkingStrategy[chunking_name])

        embedder = get_embedder()
        search_strategy = SearchStrategy(embedder=embedder)
        search_method = SearchStrategyType[search_method_name]
        if search_method in (SearchStrategyType.VECTOR, SearchStrategyType.HYBRID):
            search_strategy.searcher._get_vector_index(chunks)

        agent_wrapper = AgentWrapper(
            chunks, search_strategy=search_strategy, search_method=search_method, repo_dir=repository.repo_dir,
        )
        agent_wrapper.setup(Prompts.system_prompt_for(repository.blob_url_base()))

        built = BuiltIndex(repository, chunks, search_strategy, agent_wrapper)
        self.indexes.put(index_key, built)
        return built


def get_state(request: Request) -> 'AppState':
    """FastAPI dependency: the single process-wide AppState, set up in main.py's
    lifespan and hung off app.state rather than a bare module-level global."""
    return request.app.state.ragbot


def update_repo_meta(repo_dir: Path, **fields) -> None:
    """Merge fields into a repo's _meta.json, written once at ingestion time.

    Kept in the on-disk meta (not only in the in-memory index cache) so
    GET /api/repos/{key} and the file tree survive a backend restart without
    re-reading every file in the repo.
    """
    meta_path = repo_dir / '_meta.json'
    meta = {}
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError):
            meta = {}

    meta.update(fields)
    meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')


def read_repo_meta(repo_key: str, cache_dir: Path = REPO_CACHE_DIR) -> Optional[dict]:
    """Load one repo's _meta.json by key, or None if it isn't cached."""
    meta_path = Path(cache_dir) / repo_key / '_meta.json'
    if not meta_path.exists():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding='utf-8'))
    except (json.JSONDecodeError, OSError):
        return None
    meta['repo_key'] = repo_key
    return meta
