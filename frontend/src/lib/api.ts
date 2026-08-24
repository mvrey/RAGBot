import { readSSEStream, type RawSSEEvent } from '@/lib/sse';
import type {
  ChatStreamEvent,
  ChunkListResponse,
  ConfigResponse,
  ConversationCreate,
  ConversationCreated,
  ConversationDetail,
  EmbeddingOut,
  FileContentResponse,
  FileTreeResponse,
  HealthResponse,
  IngestAccepted,
  IngestRequest,
  JobStatus,
  RenameRepoRequest,
  RepoDetail,
  RepoSummary,
} from '@/lib/types';

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000';

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = 'ApiError';
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...init?.headers },
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

async function uploadRequest<T>(path: string, form: FormData): Promise<T> {
  // No Content-Type header here - fetch derives the multipart boundary from
  // the FormData itself, and setting one manually breaks server-side parsing.
  const res = await fetch(`${API_BASE_URL}${path}`, { method: 'POST', body: form });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new ApiError(res.status, detail || res.statusText);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<HealthResponse>('/api/health'),
  config: () => request<ConfigResponse>('/api/config'),

  listRepos: () => request<RepoSummary[]>('/api/repos'),
  getRepo: (repoKey: string) => request<RepoDetail>(`/api/repos/${encodeURIComponent(repoKey)}`),
  ingestRepo: (payload: IngestRequest) =>
    request<IngestAccepted>('/api/repos', { method: 'POST', body: JSON.stringify(payload) }),
  deleteRepo: (repoKey: string) =>
    request<void>(`/api/repos/${encodeURIComponent(repoKey)}`, { method: 'DELETE' }),
  renameRepo: (repoKey: string, payload: RenameRepoRequest) =>
    request<RepoDetail>(`/api/repos/${encodeURIComponent(repoKey)}`, { method: 'PATCH', body: JSON.stringify(payload) }),

  getRepoChunks: (repoKey: string) =>
    request<ChunkListResponse>(`/api/repos/${encodeURIComponent(repoKey)}/chunks`),
  getChunkEmbedding: (repoKey: string, hash: string) =>
    request<EmbeddingOut>(`/api/repos/${encodeURIComponent(repoKey)}/embeddings/${encodeURIComponent(hash)}`),

  getFileTree: (repoKey: string) => request<FileTreeResponse>(`/api/repos/${encodeURIComponent(repoKey)}/files`),
  getFileContent: (repoKey: string, path: string, range?: { start_line?: number; end_line?: number }) => {
    const params = new URLSearchParams();
    if (range?.start_line) params.set('start_line', String(range.start_line));
    if (range?.end_line) params.set('end_line', String(range.end_line));
    const qs = params.toString();
    const encodedPath = path.split('/').map(encodeURIComponent).join('/');
    return request<FileContentResponse>(
      `/api/repos/${encodeURIComponent(repoKey)}/files/${encodedPath}${qs ? `?${qs}` : ''}`,
    );
  },

  uploadRepo: (payload: {
    zipBytes: Uint8Array;
    name: string;
    chunking_strategy: string;
    search_method: string;
  }) => {
    const form = new FormData();
    // fetch/FormData sets its own multipart Content-Type (with boundary) only
    // when left to infer it - passing one explicitly here would break parsing.
    form.append('file', new Blob([payload.zipBytes.slice()], { type: 'application/zip' }), 'upload.zip');
    form.append('name', payload.name);
    form.append('chunking_strategy', payload.chunking_strategy);
    form.append('search_method', payload.search_method);
    return uploadRequest<IngestAccepted>('/api/repos/upload', form);
  },

  getJob: (jobId: string) => request<JobStatus>(`/api/jobs/${jobId}`),
  cancelJob: (jobId: string) => request<void>(`/api/jobs/${jobId}/cancel`, { method: 'POST' }),

  createConversation: (payload: ConversationCreate) =>
    request<ConversationCreated>('/api/conversations', { method: 'POST', body: JSON.stringify(payload) }),
  getConversation: (conversationId: string) =>
    request<ConversationDetail>(`/api/conversations/${conversationId}`),
  clearConversation: (conversationId: string) =>
    request<void>(`/api/conversations/${conversationId}`, { method: 'DELETE' }),
};

/** Subscribe to a job's SSE progress stream, yielding each JobStatus update. */
export async function* streamJobEvents(jobId: string, signal?: AbortSignal): AsyncGenerator<JobStatus> {
  const res = await fetch(`${API_BASE_URL}/api/jobs/${jobId}/events`, { signal });
  if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => res.statusText));

  for await (const raw of readSSEStream(res)) {
    if (raw.event === 'status') {
      yield JSON.parse(raw.data) as JobStatus;
    }
  }
}

/** Ask a question in a conversation, yielding typed SSE events as they stream in. */
export async function* streamAsk(
  conversationId: string,
  content: string,
  signal?: AbortSignal,
): AsyncGenerator<ChatStreamEvent> {
  const res = await fetch(`${API_BASE_URL}/api/conversations/${conversationId}/messages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ content }),
    signal,
  });
  if (!res.ok) throw new ApiError(res.status, await res.text().catch(() => res.statusText));

  for await (const raw of readSSEStream(res)) {
    const parsed = parseChatEvent(raw);
    if (parsed) yield parsed;
  }
}

export function parseChatEvent(raw: RawSSEEvent): ChatStreamEvent | null {
  try {
    const data = JSON.parse(raw.data);
    switch (raw.event) {
      case 'token':
      case 'tool_call':
      case 'tool_result':
      case 'citation':
      case 'done':
      case 'error':
        return { event: raw.event, data } as ChatStreamEvent;
      default:
        return null;
    }
  } catch {
    return null;
  }
}
