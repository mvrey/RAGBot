"""Background ingestion jobs: download-or-upload, chunk, embed, index a repo.

Runs via FastAPI's BackgroundTasks - two containers only, no broker, and jobs
die with the process. See docs/PLAN-fullstack-split.md section 6 and the
README trade-off writeup.
"""

import anyio

from ragbot.core.AgentWrapper import AgentWrapper
from ragbot.core.ChunkingStrategy import ChunkingStrategy
from ragbot.core.Embeddings import get_embedder
from ragbot.core.Prompts import Prompts
from ragbot.core.Repository import CHUNK_COUNT_WARNING_THRESHOLD, Repository
from ragbot.core.SearchStrategy import SearchStrategy, SearchStrategyType
from ragbot.api.state import AppState, BuiltIndex, update_repo_meta


async def run_ingest_job(
    state: AppState,
    job_id: str,
    repo_url: str,
    chunking_name: str,
    search_method_name: str,
) -> None:
    jobs = state.jobs
    try:
        jobs.update(job_id, status='running', phase='downloading', message=f'Fetching {repo_url}')
        repository = Repository(repo_url)

        def _load_or_download():
            already_cached = (repository.repo_dir / '_meta.json').exists()
            if already_cached:
                return repository.load_cached_repo_files(), True
            return repository.get_repo_files(), False

        files, from_cache = await anyio.to_thread.run_sync(_load_or_download)
        source = 'cache' if from_cache else 'download'
        await _finish_ingest_job(state, job_id, repository, files, chunking_name, search_method_name, source, None)
    except Exception as e:
        jobs.update(job_id, status='failed', phase=None, error=str(e), message=str(e))


async def run_upload_ingest_job(
    state: AppState,
    job_id: str,
    repo_key: str,
    name: str,
    zip_bytes: bytes,
    chunking_name: str,
    search_method_name: str,
) -> None:
    """Ingest a browser-uploaded local folder, already zipped client-side.

    Shares everything past extraction with run_ingest_job - a local folder is
    indistinguishable from a downloaded repo everywhere else in the pipeline.
    """
    jobs = state.jobs
    try:
        jobs.update(job_id, status='running', phase='downloading', message=f'Extracting {name}')
        # "local:<name>" is not a real URL - it just gives blob_url_base() a
        # string that fails the codeload pattern, so citations correctly fall
        # back to bare path:line instead of a nonexistent GitHub link.
        repository = Repository(f'local:{name}', repo_key=repo_key)

        files = await anyio.to_thread.run_sync(repository.load_from_zip_bytes, zip_bytes)
        # The folder's own name reads much better as the initial display name
        # than the repo_key's random-suffixed slug - still renameable after.
        await _finish_ingest_job(state, job_id, repository, files, chunking_name, search_method_name, 'upload', name)
    except Exception as e:
        jobs.update(job_id, status='failed', phase=None, error=str(e), message=str(e))


async def _finish_ingest_job(
    state: AppState,
    job_id: str,
    repository: Repository,
    files: list,
    chunking_name: str,
    search_method_name: str,
    source: str,
    initial_display_name: str = None,
) -> None:
    """Chunk -> embed -> index -> persist, shared by both ingestion sources."""
    jobs = state.jobs
    jobs.update(job_id, phase='chunking', message=f'{len(files)} files loaded ({source})', progress=None)

    def _on_chunk_progress(done: int, total: int) -> None:
        jobs.update(job_id, progress={'current': done, 'total': total})

    chunking_strategy = ChunkingStrategy[chunking_name]
    chunks = await anyio.to_thread.run_sync(
        lambda: repository.chunk(chunking_strategy, on_progress=_on_chunk_progress)
    )

    message = f'{len(chunks)} chunks created'
    if len(chunks) > CHUNK_COUNT_WARNING_THRESHOLD:
        message += f' (exceeds the ~{CHUNK_COUNT_WARNING_THRESHOLD} comfort limit; indexing will be slow)'
    jobs.update(job_id, phase='embedding', message=message, progress=None)

    def _on_embed_progress(done: int, total: int) -> None:
        jobs.update(job_id, progress={'current': done, 'total': total})

    embedder = get_embedder()
    search_strategy = SearchStrategy(embedder=embedder)
    search_method = SearchStrategyType[search_method_name]

    def _build_vector_index():
        if search_method in (SearchStrategyType.VECTOR, SearchStrategyType.HYBRID):
            search_strategy.searcher._get_vector_index(chunks, on_progress=_on_embed_progress)

    await anyio.to_thread.run_sync(_build_vector_index)

    jobs.update(job_id, phase='indexing', message='Setting up the agent', progress=None)

    def _build_agent():
        agent_wrapper = AgentWrapper(
            chunks, search_strategy=search_strategy, search_method=search_method, repo_dir=repository.repo_dir,
        )
        agent_wrapper.setup(Prompts.system_prompt_for(repository.blob_url_base()))
        return agent_wrapper

    agent_wrapper = await anyio.to_thread.run_sync(_build_agent)

    index_key = (repository.repo_key, chunking_name, search_method_name)
    state.indexes.put(index_key, BuiltIndex(repository, chunks, search_strategy, agent_wrapper))

    extra_meta = {'display_name': initial_display_name} if initial_display_name else {}
    update_repo_meta(
        repository.repo_dir,
        chunking_strategy=chunking_name,
        search_method=search_method_name,
        chunk_count=len(chunks),
        language_stats=repository.language_stats(),
        embedding_model=embedder.name,
        **extra_meta,
    )

    jobs.update(
        job_id, status='succeeded', phase='ready', message='Ready',
        result={'repo_key': repository.repo_key},
    )
