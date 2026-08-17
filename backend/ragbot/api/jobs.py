"""Background ingestion job: download/chunk/embed/index a repo.

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
        jobs.update(job_id, phase='chunking', message=f'{len(files)} files loaded ({source})')

        chunking_strategy = ChunkingStrategy[chunking_name]
        chunks = await anyio.to_thread.run_sync(repository.chunk, chunking_strategy)

        message = f'{len(chunks)} chunks created'
        if len(chunks) > CHUNK_COUNT_WARNING_THRESHOLD:
            message += f' (exceeds the ~{CHUNK_COUNT_WARNING_THRESHOLD} comfort limit; indexing will be slow)'
        jobs.update(job_id, phase='embedding', message=message)

        embedder = get_embedder()
        search_strategy = SearchStrategy(embedder=embedder)
        search_method = SearchStrategyType[search_method_name]

        def _build_vector_index():
            if search_method in (SearchStrategyType.VECTOR, SearchStrategyType.HYBRID):
                search_strategy.searcher._get_vector_index(chunks)

        await anyio.to_thread.run_sync(_build_vector_index)

        jobs.update(job_id, phase='indexing', message='Setting up the agent')

        def _build_agent():
            agent_wrapper = AgentWrapper(
                chunks, search_strategy=search_strategy, search_method=search_method, repo_dir=repository.repo_dir,
            )
            agent_wrapper.setup(Prompts.system_prompt_for(repository.blob_url_base()))
            return agent_wrapper

        agent_wrapper = await anyio.to_thread.run_sync(_build_agent)

        index_key = (repository.repo_key, chunking_name, search_method_name)
        state.indexes.put(index_key, BuiltIndex(repository, chunks, search_strategy, agent_wrapper))

        update_repo_meta(
            repository.repo_dir,
            chunking_strategy=chunking_name,
            search_method=search_method_name,
            chunk_count=len(chunks),
            language_stats=repository.language_stats(),
        )

        jobs.update(
            job_id, status='succeeded', phase='ready', message='Ready',
            result={'repo_key': repository.repo_key},
        )
    except Exception as e:
        jobs.update(job_id, status='failed', phase=None, error=str(e), message=str(e))
