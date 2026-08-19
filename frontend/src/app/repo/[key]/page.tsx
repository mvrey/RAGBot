'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ArrowLeft, Files, Pencil } from 'lucide-react';
import { api } from '@/lib/api';
import type { CitationMatch } from '@/lib/citations';
import { ChatPanel } from '@/components/ChatPanel';
import { FileTree } from '@/components/FileTree';
import { RenameRepoDialog, type RenameTarget } from '@/components/RenameRepoDialog';
import { SourceViewer, type OpenTarget } from '@/components/SourceViewer';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';

export default function RepoWorkspacePage({ params }: { params: Promise<{ key: string }> }) {
  const { key: repoKey } = use(params);
  const queryClient = useQueryClient();
  const [target, setTarget] = useState<OpenTarget | null>(null);
  const [renaming, setRenaming] = useState<RenameTarget | null>(null);

  const { data: repo, isLoading, isError } = useQuery({
    queryKey: ['repo', repoKey],
    queryFn: () => api.getRepo(repoKey),
  });

  const openCitation = (citation: CitationMatch) => {
    setTarget({ path: citation.path, start: citation.start, end: citation.end });
  };

  const openFile = (path: string) => {
    setTarget({ path });
  };

  if (isError) {
    return (
      <main className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-3 px-6 text-center">
        <p className="text-lg font-medium">Repository not found</p>
        <Link href="/" className="text-sm text-primary underline underline-offset-4">
          Back to repositories
        </Link>
      </main>
    );
  }

  return (
    <main className="flex h-dvh flex-col overflow-hidden">
      <header className="flex shrink-0 items-center gap-3 border-b px-4 py-2.5">
        <Link href="/" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" />
        </Link>
        {isLoading ? (
          <Skeleton className="h-5 w-48" />
        ) : (
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate font-medium">{repo?.display_name ?? repo?.repo_key}</span>
            <Button
              variant="ghost"
              size="icon-sm"
              className="shrink-0 text-muted-foreground hover:text-foreground"
              aria-label="Rename project"
              onClick={() => repo && setRenaming({ repo_key: repo.repo_key, display_name: repo.display_name })}
            >
              <Pencil className="size-3.5" />
            </Button>
            <span className="shrink-0 text-sm text-muted-foreground">
              {repo?.chunking_strategy} · {repo?.search_method}
            </span>
          </div>
        )}
      </header>

      <div className="flex min-h-0 flex-1">
        <section className="flex min-h-0 min-w-0 flex-1 flex-col border-r">
          <ChatPanel
            key={repoKey}
            repoKey={repoKey}
            onOpenCitation={openCitation}
            activeCitation={target?.start != null ? { path: target.path, start: target.start, end: target.end ?? target.start } : null}
          />
        </section>

        <section className="flex min-h-0 w-64 shrink-0 flex-col border-r">
          <div className="flex shrink-0 items-center gap-1.5 border-b px-3 py-2 text-sm font-medium">
            <Files className="size-3.5" />
            Files
          </div>
          <FileTree repoKey={repoKey} selectedPath={target?.path} onSelectFile={openFile} />
        </section>

        <section className="flex min-h-0 min-w-0 flex-1 flex-col">
          <SourceViewer repoKey={repoKey} target={target} />
        </section>
      </div>

      <RenameRepoDialog
        repo={renaming}
        onClose={() => setRenaming(null)}
        onRenamed={() => {
          queryClient.invalidateQueries({ queryKey: ['repo', repoKey] });
          setRenaming(null);
        }}
      />
    </main>
  );
}
