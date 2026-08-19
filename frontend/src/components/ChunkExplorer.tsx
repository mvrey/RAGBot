'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronRight } from 'lucide-react';
import { api } from '@/lib/api';
import type { ChunkOut } from '@/lib/types';
import { ScrollArea } from '@/components/ui/scroll-area';

function formatKind(kind: string): string {
  return kind.replace(/_/g, ' ');
}

interface FileGroup {
  filename: string;
  chunks: ChunkOut[];
  method: string;
}

function groupByFile(chunks: ChunkOut[]): FileGroup[] {
  const order: string[] = [];
  const byFile = new Map<string, ChunkOut[]>();
  for (const chunk of chunks) {
    if (!byFile.has(chunk.filename)) {
      byFile.set(chunk.filename, []);
      order.push(chunk.filename);
    }
    byFile.get(chunk.filename)!.push(chunk);
  }
  return order.map((filename) => {
    const fileChunks = byFile.get(filename)!;
    return { filename, chunks: fileChunks, method: fileChunks[0]?.method ?? '' };
  });
}

interface ChunkExplorerProps {
  repoKey: string;
  enabled: boolean;
}

/** File list with each file's actual chunking method, expandable down to
 * individual chunks and (lazily, on demand) their cached embedding vector. */
export function ChunkExplorer({ repoKey, enabled }: ChunkExplorerProps) {
  const { data, isLoading } = useQuery({
    queryKey: ['repo-chunks', repoKey],
    queryFn: () => api.getRepoChunks(repoKey),
    enabled,
  });

  if (isLoading) {
    return <p className="text-sm text-muted-foreground">Loading files…</p>;
  }
  if (!data || data.chunks.length === 0) {
    return <p className="text-sm text-muted-foreground">No chunks yet.</p>;
  }

  const files = groupByFile(data.chunks);

  return (
    <ScrollArea className="max-h-80 rounded-lg">
      <div className="divide-y">
        {files.map((file) => (
          <FileRow key={file.filename} file={file} repoKey={repoKey} />
        ))}
      </div>
    </ScrollArea>
  );
}

function FileRow({ file, repoKey }: { file: FileGroup; repoKey: string }) {
  return (
    <details className="group/file">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm hover:bg-muted/50">
        <ChevronRight className="size-3.5 shrink-0 text-muted-foreground transition-transform group-open/file:rotate-90" />
        <span className="min-w-0 flex-1 truncate font-mono">{file.filename}</span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {file.chunks.length} {file.chunks.length === 1 ? 'chunk' : 'chunks'}
        </span>
        <span className="shrink-0 text-xs font-medium text-muted-foreground" title={`Chunked with ${file.method || 'unknown method'}`}>
          {file.method || '—'}
        </span>
      </summary>
      <div className="divide-y border-t bg-muted/20 pl-6">
        {file.chunks.map((chunk, i) => (
          <ChunkRow key={`${chunk.hash}-${i}`} chunk={chunk} repoKey={repoKey} />
        ))}
      </div>
    </details>
  );
}

function ChunkRow({ chunk, repoKey }: { chunk: ChunkOut; repoKey: string }) {
  const [open, setOpen] = useState(false);
  const lineRange = chunk.start_line != null ? `L${chunk.start_line}–${chunk.end_line ?? chunk.start_line}` : null;

  return (
    <details onToggle={(e) => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary className="flex cursor-pointer list-none items-center gap-2 py-1.5 pr-3 text-xs hover:bg-muted/50">
        <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        <span className="truncate text-muted-foreground">
          {chunk.symbol || formatKind(chunk.kind) || 'chunk'}
        </span>
        {lineRange && <span className="shrink-0 text-muted-foreground/70">{lineRange}</span>}
      </summary>
      {open && (
        <div className="space-y-2 py-2 pr-3">
          <pre className="max-h-40 overflow-auto rounded-md bg-background p-2 text-xs">
            <code>{chunk.chunk}</code>
          </pre>
          <EmbeddingViewer repoKey={repoKey} hash={chunk.hash} />
        </div>
      )}
    </details>
  );
}

function EmbeddingViewer({ repoKey, hash }: { repoKey: string; hash: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ['chunk-embedding', repoKey, hash],
    queryFn: () => api.getChunkEmbedding(repoKey, hash),
  });

  if (isLoading) return <p className="text-xs text-muted-foreground">Loading embedding…</p>;
  if (!data?.embedding) return <p className="text-xs text-muted-foreground">Not embedded yet.</p>;

  return (
    <p className="text-xs text-muted-foreground">
      {data.dimensions} dimensions · {data.model}
    </p>
  );
}
