// Mirrors backend/ragbot/api/schemas.py - keep the two in sync by hand, since
// the backend deliberately has no codegen step (see docs/PLAN-fullstack-split.md).

export interface HealthResponse {
  status: string;
  chat_model: string;
  embedder: string;
  missing_api_key: string;
}

export interface Option {
  name: string;
  label: string;
}

export interface ConfigResponse {
  chunking_strategies: Option[];
  search_methods: Option[];
}

export interface IngestRequest {
  repo_url: string;
  chunking_strategy: string;
  search_method: string;
}

export interface IngestAccepted {
  job_id: string;
  repo_key: string;
}

export interface RepoSummary {
  repo_key: string;
  repo_url: string;
  downloaded_at: string;
  file_count: number;
  chunk_count: number | null;
  indexed: boolean;
  display_name: string | null;
}

export interface RenameRepoRequest {
  display_name: string;
}

export interface RepoDetail extends RepoSummary {
  language_stats: Record<string, number>;
  chunking_strategy: string | null;
  search_method: string | null;
  embedding_model: string | null;
  index_warm: boolean;
  repo_page_url: string | null;
}

export interface ChunkOut {
  filename: string;
  kind: string;
  // The concrete ChunkingStrategy member name actually used for this file
  // (e.g. "AST" or "MARKDOWN") - meaningful per-file under AUTO, which
  // dispatches differently per file rather than using one method for all.
  method: string;
  language: string;
  symbol: string;
  start_line: number | null;
  end_line: number | null;
  chunk: string;
  hash: string;
}

export interface ChunkListResponse {
  repo_key: string;
  chunks: ChunkOut[];
}

export interface EmbeddingOut {
  hash: string;
  embedding: number[] | null;
  dimensions: number | null;
  model: string | null;
}

export interface FileNode {
  name: string;
  path: string;
  type: 'file' | 'dir';
  children: FileNode[];
}

export interface FileTreeResponse {
  repo_key: string;
  root: FileNode[];
}

export interface FileContentResponse {
  path: string;
  start_line: number;
  end_line: number;
  total_lines: number;
  content: string;
}

export type JobStatusValue = 'pending' | 'running' | 'succeeded' | 'failed';
export type JobPhase = 'downloading' | 'chunking' | 'embedding' | 'indexing' | 'ready';

export interface JobProgress {
  current: number;
  total: number;
}

export interface JobStatus {
  id: string;
  kind: string;
  status: JobStatusValue;
  phase: JobPhase | null;
  message: string;
  error: string | null;
  result: { repo_key: string } | null;
  created_at: number;
  progress: JobProgress | null;
}

export interface ConversationCreate {
  repo_key: string;
}

export interface ConversationCreated {
  conversation_id: string;
  repo_key: string;
}

export interface Citation {
  path: string;
  start: number;
  end: number;
}

export interface MessageOut {
  role: 'user' | 'assistant';
  content: string;
  citations: Citation[];
}

export interface ConversationDetail {
  id: string;
  repo_key: string;
  created_at: number;
  messages: MessageOut[];
}

// --- SSE event payloads, matching the API's streaming contract -------------

export interface TokenEventData {
  delta: string;
}

export interface ToolCallEventData {
  tool: string;
  args: Record<string, unknown>;
}

export interface ToolResultEventData {
  tool: string;
  summary: string;
}

export interface DoneEventData {
  message_id: string;
  usage: { input_tokens: number; output_tokens: number; requests: number };
}

export interface ErrorEventData {
  detail: string;
}

export type ChatStreamEvent =
  | { event: 'token'; data: TokenEventData }
  | { event: 'tool_call'; data: ToolCallEventData }
  | { event: 'tool_result'; data: ToolResultEventData }
  | { event: 'citation'; data: Citation }
  | { event: 'done'; data: DoneEventData }
  | { event: 'error'; data: ErrorEventData };
