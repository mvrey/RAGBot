'use client';

import type { ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ExternalLink } from 'lucide-react';
import { api } from '@/lib/api';
import type { RepoSummary } from '@/lib/types';
import { ChunkExplorer } from '@/components/ChunkExplorer';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

interface RepoStatsDialogProps {
  repo: RepoSummary | null;
  onClose: () => void;
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="space-y-0.5 rounded-lg border bg-muted/30 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="truncate text-sm font-medium">{value}</p>
    </div>
  );
}

/** Formats "google:gemini-embedding-2@768" as "gemini-embedding-2 (google, 768d)". */
function formatEmbeddingModel(raw: string): string {
  const [provider, rest] = raw.split(':', 2);
  if (!rest) return raw;
  const [model, dims] = rest.split('@', 2);
  return dims ? `${model} (${provider}, ${dims}d)` : `${model} (${provider})`;
}

/** Big lightbox showing everything known about one cached project: counts,
 * chunking/embedding config, index warmth, a language breakdown, and the
 * per-file chunk/embedding explorer. */
export function RepoStatsDialog({ repo, onClose }: RepoStatsDialogProps) {
  const { data: detail, isLoading } = useQuery({
    queryKey: ['repo', repo?.repo_key],
    queryFn: () => api.getRepo(repo!.repo_key),
    enabled: !!repo,
  });
  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.config, enabled: !!repo });

  const chunkingLabel = config?.chunking_strategies.find((o) => o.name === detail?.chunking_strategy)?.label
    ?? detail?.chunking_strategy;

  const languages = detail ? Object.entries(detail.language_stats).sort((a, b) => b[1] - a[1]) : [];
  const maxCount = languages[0]?.[1] ?? 1;

  return (
    <Dialog open={!!repo} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="text-xl">{repo?.display_name ?? repo?.repo_key}</DialogTitle>
          {repo?.display_name && (
            <p className="font-mono text-xs text-muted-foreground">{repo.repo_key}</p>
          )}
        </DialogHeader>

        {isLoading || !detail ? (
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : (
          <div className="space-y-5">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Files" value={detail.file_count} />
              <Stat label="Chunks" value={detail.chunk_count ?? '—'} />
              <Stat
                label="Index"
                value={
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className={cn(
                        'size-1.5 shrink-0 rounded-full',
                        !detail.indexed
                          ? 'bg-muted-foreground/40'
                          : detail.index_warm
                            ? 'bg-emerald-500'
                            : 'bg-amber-500',
                      )}
                    />
                    {detail.indexed ? (detail.index_warm ? 'Warm' : 'Cold — rebuilds next question') : 'Not indexed'}
                  </span>
                }
              />
              <Stat label="Chunking method" value={chunkingLabel ?? '—'} />
              <Stat
                label="Embedding model"
                value={detail.embedding_model ? formatEmbeddingModel(detail.embedding_model) : '—'}
              />
              <Stat label="Ingested" value={new Date(detail.downloaded_at).toLocaleString()} />
              <Stat
                label="Source"
                value={
                  detail.repo_page_url ? (
                    <a
                      href={detail.repo_page_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 text-primary hover:underline"
                    >
                      GitHub <ExternalLink className="size-3" />
                    </a>
                  ) : (
                    'Local upload'
                  )
                }
              />
            </div>

            {languages.length > 0 && (
              <>
                <Separator />
                <div className="space-y-2">
                  <p className="text-sm font-medium">Languages</p>
                  <ScrollArea className="max-h-48">
                    <div className="space-y-1.5 pr-3">
                      {languages.map(([name, count]) => (
                        <div key={name} className="flex items-center gap-2 text-sm">
                          <span className="w-24 shrink-0 truncate text-muted-foreground">{name}</span>
                          <div className="h-2 min-w-8 flex-1 overflow-hidden rounded-full bg-muted">
                            <div
                              className="h-full rounded-full bg-primary"
                              style={{ width: `${Math.max(4, (count / maxCount) * 100)}%` }}
                            />
                          </div>
                          <span className="w-10 shrink-0 text-right tabular-nums text-muted-foreground">
                            {count}
                          </span>
                        </div>
                      ))}
                    </div>
                  </ScrollArea>
                </div>
              </>
            )}

            <Separator />
            <div className="space-y-2">
              <p className="text-sm font-medium">Files &amp; chunks</p>
              <ChunkExplorer repoKey={detail.repo_key} enabled={!!repo} />
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
