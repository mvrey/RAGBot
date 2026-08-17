'use client';

import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, CircleDashed, Loader2, XCircle } from 'lucide-react';
import { streamJobEvents } from '@/lib/api';
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
  jobId: string;
  onSucceeded: (repoKey: string) => void;
  onFailed?: (message: string) => void;
}

/** Named-phase progress for a repo ingestion job, driven by its SSE stream. */
export function JobProgress({ jobId, onSucceeded, onFailed }: JobProgressProps) {
  const [job, setJob] = useState<JobStatus | null>(null);
  const settledRef = useRef(false);

  useEffect(() => {
    settledRef.current = false;
    const controller = new AbortController();

    (async () => {
      try {
        for await (const status of streamJobEvents(jobId, controller.signal)) {
          setJob(status);
          if (status.status === 'succeeded' && status.result && !settledRef.current) {
            settledRef.current = true;
            onSucceeded(status.result.repo_key);
          } else if (status.status === 'failed' && !settledRef.current) {
            settledRef.current = true;
            onFailed?.(status.error ?? 'Ingestion failed.');
          }
        }
      } catch {
        // AbortError on unmount, or a transient network drop - the job status
        // endpoint still exists for a manual retry, so this fails soft.
      }
    })();

    return () => controller.abort();
  }, [jobId, onSucceeded, onFailed]);

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
    </div>
  );
}
