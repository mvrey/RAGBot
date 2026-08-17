from typing import Any, Optional

from pydantic import BaseModel, Field

from ragbot.core.ChunkingStrategy import ChunkingStrategy
from ragbot.core.SearchStrategy import SearchStrategyType


class HealthResponse(BaseModel):
    status: str
    chat_model: str
    embedder: str
    missing_api_key: str = ''


class OptionOut(BaseModel):
    name: str
    label: str


class ConfigResponse(BaseModel):
    chunking_strategies: list[OptionOut]
    search_methods: list[OptionOut]

    @classmethod
    def build(cls) -> 'ConfigResponse':
        return cls(
            chunking_strategies=[OptionOut(name=s.name, label=s.label) for s in ChunkingStrategy],
            search_methods=[OptionOut(name=s.name, label=s.label) for s in SearchStrategyType],
        )


class IngestRequest(BaseModel):
    repo_url: str
    chunking_strategy: str = 'AUTO'
    search_method: str = 'HYBRID'


class IngestAccepted(BaseModel):
    job_id: str
    repo_key: str


class RepoSummary(BaseModel):
    repo_key: str
    repo_url: str
    downloaded_at: str
    file_count: int
    chunk_count: Optional[int] = None
    indexed: bool = False
    # User-editable label shown in the UI in place of repo_key, which stays
    # the stable identifier everything else (URLs, index cache, conversations,
    # the on-disk directory) is keyed by - renaming never touches any of that.
    display_name: Optional[str] = None


class RepoDetail(RepoSummary):
    language_stats: dict[str, int] = Field(default_factory=dict)
    chunking_strategy: Optional[str] = None
    search_method: Optional[str] = None


class RenameRepoRequest(BaseModel):
    display_name: str


class FileNode(BaseModel):
    name: str
    path: str
    type: str  # 'file' | 'dir'
    children: list['FileNode'] = Field(default_factory=list)


FileNode.model_rebuild()


class FileTreeResponse(BaseModel):
    repo_key: str
    root: list[FileNode]


class FileContentResponse(BaseModel):
    path: str
    start_line: int
    end_line: int
    total_lines: int
    content: str


class JobProgress(BaseModel):
    current: int
    total: int


class JobStatus(BaseModel):
    id: str
    kind: str
    status: str
    phase: Optional[str] = None
    message: str = ''
    error: Optional[str] = None
    result: Optional[dict[str, Any]] = None
    created_at: float
    # Set only during a phase with real sub-progress to report (chunking,
    # embedding) - None otherwise, including for phases that are effectively
    # one shot (downloading, indexing).
    progress: Optional[JobProgress] = None


class ConversationCreate(BaseModel):
    repo_key: str


class ConversationCreated(BaseModel):
    conversation_id: str
    repo_key: str


class MessageOut(BaseModel):
    role: str
    content: str
    citations: list[dict] = Field(default_factory=list)


class ConversationDetail(BaseModel):
    id: str
    repo_key: str
    created_at: float
    messages: list[MessageOut]


class AskRequest(BaseModel):
    content: str
