import shutil
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query

from ragbot.core.AgentWrapper import AgentWrapper, MAX_FILE_LINES
from ragbot.core.ChunkingStrategy import ChunkingStrategy
from ragbot.core.Repository import Repository
from ragbot.core.SearchStrategy import SearchStrategyType
from ragbot.core.settings import REPO_CACHE_DIR
from ragbot.api.jobs import run_ingest_job
from ragbot.api.schemas import (
    FileContentResponse,
    FileNode,
    FileTreeResponse,
    IngestAccepted,
    IngestRequest,
    RepoDetail,
    RepoSummary,
)
from ragbot.api.state import AppState, get_state, read_repo_meta

router = APIRouter(prefix='/repos', tags=['repos'])


def _validate_choice(value: str, enum_cls, field_name: str) -> None:
    if value not in enum_cls.__members__:
        allowed = ', '.join(enum_cls.__members__)
        raise HTTPException(422, f"Invalid {field_name} '{value}'. Expected one of: {allowed}")


@router.get('', response_model=list[RepoSummary])
def list_repos() -> list[RepoSummary]:
    return [
        RepoSummary(
            repo_key=meta['repo_key'],
            repo_url=meta['repo_url'],
            downloaded_at=meta['downloaded_at'],
            file_count=meta.get('file_count', 0),
            chunk_count=meta.get('chunk_count'),
            indexed=bool(meta.get('chunking_strategy')),
        )
        for meta in Repository.list_cached_repos()
    ]


@router.post('', response_model=IngestAccepted, status_code=202)
def create_repo(
    payload: IngestRequest,
    background_tasks: BackgroundTasks,
    state: AppState = Depends(get_state),
) -> IngestAccepted:
    _validate_choice(payload.chunking_strategy, ChunkingStrategy, 'chunking_strategy')
    _validate_choice(payload.search_method, SearchStrategyType, 'search_method')

    job_id = state.jobs.create(kind='ingest')
    background_tasks.add_task(
        run_ingest_job, state, job_id, payload.repo_url, payload.chunking_strategy, payload.search_method,
    )
    repo_key = Repository._slugify(payload.repo_url)
    return IngestAccepted(job_id=job_id, repo_key=repo_key)


@router.get('/{repo_key}', response_model=RepoDetail)
def get_repo(repo_key: str) -> RepoDetail:
    meta = read_repo_meta(repo_key)
    if meta is None:
        raise HTTPException(404, f"No cached repo '{repo_key}'.")

    return RepoDetail(
        repo_key=meta['repo_key'],
        repo_url=meta['repo_url'],
        downloaded_at=meta['downloaded_at'],
        file_count=meta.get('file_count', 0),
        chunk_count=meta.get('chunk_count'),
        indexed=bool(meta.get('chunking_strategy')),
        language_stats=meta.get('language_stats', {}),
        chunking_strategy=meta.get('chunking_strategy'),
        search_method=meta.get('search_method'),
    )


@router.delete('/{repo_key}', status_code=204)
def delete_repo(repo_key: str, state: AppState = Depends(get_state)) -> None:
    meta = read_repo_meta(repo_key)
    if meta is None:
        raise HTTPException(404, f"No cached repo '{repo_key}'.")

    repo_dir = REPO_CACHE_DIR / repo_key
    shutil.rmtree(repo_dir, ignore_errors=True)

    stale_keys = [key for key in state.indexes if key[0] == repo_key]
    for key in stale_keys:
        del state.indexes[key]


@router.get('/{repo_key}/files', response_model=FileTreeResponse)
def get_file_tree(repo_key: str) -> FileTreeResponse:
    meta = read_repo_meta(repo_key)
    if meta is None:
        raise HTTPException(404, f"No cached repo '{repo_key}'.")

    repo_dir = REPO_CACHE_DIR / repo_key
    paths = sorted(
        p.relative_to(repo_dir).as_posix()
        for p in repo_dir.rglob('*')
        if p.is_file() and p.name != '_meta.json'
    )
    return FileTreeResponse(repo_key=repo_key, root=_build_tree(paths))


def _build_tree(paths: list[str]) -> list[FileNode]:
    """Turn a flat list of repo-relative paths into a nested FileNode tree."""
    root: dict = {}
    for path in paths:
        parts = path.split('/')
        node = root
        for i, part in enumerate(parts):
            is_leaf = i == len(parts) - 1
            node = node.setdefault(part, {'__type__': 'file' if is_leaf else 'dir', '__children__': {}})
            node = node['__children__']

    def to_nodes(children: dict, prefix: str) -> list[FileNode]:
        out = []
        for name, entry in sorted(children.items(), key=lambda kv: (kv[1]['__type__'] != 'dir', kv[0].lower())):
            full_path = f'{prefix}/{name}' if prefix else name
            out.append(FileNode(
                name=name,
                path=full_path,
                type=entry['__type__'],
                children=to_nodes(entry['__children__'], full_path),
            ))
        return out

    return to_nodes(root, '')


@router.get('/{repo_key}/files/{path:path}', response_model=FileContentResponse)
def get_file_content(
    repo_key: str,
    path: str,
    start_line: Optional[int] = Query(None, ge=1),
    end_line: Optional[int] = Query(None, ge=1),
) -> FileContentResponse:
    meta = read_repo_meta(repo_key)
    if meta is None:
        raise HTTPException(404, f"No cached repo '{repo_key}'.")

    repo_dir = REPO_CACHE_DIR / repo_key
    try:
        # Reuses the exact traversal guard the agent's read_file tool uses -
        # this endpoint is reachable by anyone who can call the API, not just
        # the model, so the check must not be reimplemented here.
        target = AgentWrapper.safe_repo_path(repo_dir, path)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not target.is_file():
        raise HTTPException(404, f"File not found: {path}")

    lines = target.read_text(encoding='utf-8', errors='ignore').splitlines()
    total = len(lines)

    first = max(start_line or 1, 1)
    last = min(end_line or total, total)
    if first > total:
        raise HTTPException(400, f"{path} has only {total} lines.")

    selected = lines[first - 1:last]
    if len(selected) > MAX_FILE_LINES:
        selected = selected[:MAX_FILE_LINES]
        last = first + MAX_FILE_LINES - 1

    return FileContentResponse(
        path=path, start_line=first, end_line=last, total_lines=total, content='\n'.join(selected),
    )
