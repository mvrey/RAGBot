'use client';

import { useQuery } from '@tanstack/react-query';
import { useEffect, useRef, useState } from 'react';
import { FileCode2 } from 'lucide-react';
import { api } from '@/lib/api';
import { highlightLines, type HighlightedToken } from '@/lib/highlight';
import { Skeleton } from '@/components/ui/skeleton';
import { cn } from '@/lib/utils';

export interface OpenTarget {
  path: string;
  start?: number;
  end?: number;
}

interface SourceViewerProps {
  repoKey: string;
  target: OpenTarget | null;
}

export function SourceViewer({ repoKey, target }: SourceViewerProps) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['file-content', repoKey, target?.path],
    queryFn: () => api.getFileContent(repoKey, target!.path),
    enabled: !!target,
  });

  const [lines, setLines] = useState<HighlightedToken[][] | null>(null);
  const highlightRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    highlightLines(data.content, data.path).then((result) => {
      if (!cancelled) setLines(result);
    });
    return () => {
      cancelled = true;
    };
  }, [data]);

  useEffect(() => {
    highlightRef.current?.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }, [lines]);

  if (!target) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-muted-foreground">
        <FileCode2 className="size-8" />
        <p className="text-sm">Click a citation or a file to view its source.</p>
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-4 py-2 font-mono text-sm text-muted-foreground">
        {target.path}
        {target.start && <span> — lines {target.start}-{target.end ?? target.start}</span>}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading && (
          <div className="space-y-2 p-4">
            {Array.from({ length: 12 }).map((_, i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
          </div>
        )}
        {isError && <p className="p-4 text-sm text-destructive">Could not load this file.</p>}
        {!isLoading && lines && data && (
          <pre className="p-4 text-xs leading-6">
            {lines.map((lineTokens, i) => {
              const lineNumber = data.start_line + i;
              const isHighlighted =
                target.start != null && lineNumber >= target.start && lineNumber <= (target.end ?? target.start);
              return (
                <div
                  key={i}
                  ref={isHighlighted && lineNumber === target.start ? highlightRef : undefined}
                  className={cn('flex px-2 -mx-2', isHighlighted && 'bg-primary/15 border-l-2 border-primary')}
                >
                  <span className="w-10 shrink-0 select-none pr-3 text-right text-muted-foreground/60">
                    {lineNumber}
                  </span>
                  <span className="whitespace-pre-wrap break-all">
                    {lineTokens.map((t, j) => (
                      <span key={j} style={t.color ? { color: t.color } : undefined}>
                        {t.content}
                      </span>
                    ))}
                  </span>
                </div>
              );
            })}
          </pre>
        )}
      </div>
    </div>
  );
}
