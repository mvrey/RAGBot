'use client';

import { CheckCircle2, CircleDashed, Loader2, XCircle } from 'lucide-react';
import type { JobPhase, JobStatus } from '@/lib/types';
import { cn } from '@/lib/utils';

function phasesFor(kind: string | undefined): { key: JobPhase; label: string }[] {
  return [
    { key: 'downloading', label: kind === 'upload' ? 'Extracting' : 'Downloading' },
    { key: 'chunking', label: 'Chunking' },
    { key: 'embedding', label: 'Embedding' },
    { key: 'indexing', label: 'Indexing' },
    { key: 'ready', label: 'Ready' },
  ];
}

interface JobProgressProps {
  job: JobStatus;
}

/** Named-phase progress for a repo ingestion job.
 *
 * Purely presentational - the parent (HomePage) owns the SSE subscription and
 * passes the latest status down, so progress keeps updating even while this
 * component is unmounted (the ingest dialog minimized) and remounts already
 * showing the current phase instead of restarting from "Starting…". */
export function JobProgress({ job }: JobProgressProps) {
  const phases = phasesFor(job?.kind);
  const currentIndex = job?.phase ? phases.findIndex((p) => p.key === job.phase) : -1;
  const failed = job?.status === 'failed';

  return (
    <div className="space-y-6">
      <ol className="flex items-center gap-2">
        {phases.map((phase, i) => {
          const done = currentIndex > i || (currentIndex === i && job?.status === 'succeeded');
          const active = currentIndex === i && job?.status === 'running';
          return (
            <li key={phase.key} className="flex flex-1 items-center gap-2">
              <div className="flex flex-col items-center gap-2 text-sm">
                {failed && currentIndex === i ? (
                  <XCircle className="size-8 text-destructive" />
                ) : done ? (
                  <CheckCircle2 className="size-8 text-emerald-500" />
                ) : active ? (
                  <Loader2 className="size-8 animate-spin text-primary" />
                ) : (
                  <CircleDashed className="size-8 text-muted-foreground/50" />
                )}
                <span className={cn('whitespace-nowrap', (done || active) && 'font-medium')}>{phase.label}</span>
              </div>
              {i < phases.length - 1 && (
                <div className={cn('h-0.5 flex-1', done ? 'bg-emerald-500' : 'bg-border')} />
              )}
            </li>
          );
        })}
      </ol>
      <p className={cn('text-base', failed ? 'text-destructive' : 'text-muted-foreground')}>
        {job?.error ?? job?.message ?? 'Starting…'}
      </p>
      {job?.progress && job.status === 'running' && (
        <div className="space-y-1.5">
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary transition-[width] duration-300 ease-out"
              style={{ width: `${Math.min(100, (job.progress.current / job.progress.total) * 100)}%` }}
            />
          </div>
          <p className="text-right text-sm tabular-nums text-muted-foreground">
            {job.progress.current} / {job.progress.total}
          </p>
        </div>
      )}
    </div>
  );
}
