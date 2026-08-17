'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, Files, FileCode2 } from 'lucide-react';
import { api } from '@/lib/api';
import type { CitationMatch } from '@/lib/citations';
import { ChatPanel } from '@/components/ChatPanel';
import { FileTree } from '@/components/FileTree';
import { SourceViewer, type OpenTarget } from '@/components/SourceViewer';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Skeleton } from '@/components/ui/skeleton';

export default function RepoWorkspacePage({ params }: { params: Promise<{ key: string }> }) {
  const { key: repoKey } = use(params);
  const [target, setTarget] = useState<OpenTarget | null>(null);
  const [tab, setTab] = useState('source');

  const { data: repo, isLoading, isError } = useQuery({
    queryKey: ['repo', repoKey],
    queryFn: () => api.getRepo(repoKey),
  });

  const openCitation = (citation: CitationMatch) => {
    setTarget({ path: citation.path, start: citation.start, end: citation.end });
    setTab('source');
  };

  const openFile = (path: string) => {
    setTarget({ path });
    setTab('source');
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
    <main className="flex flex-1 flex-col">
      <header className="flex items-center gap-3 border-b px-4 py-2.5">
        <Link href="/" className="text-muted-foreground hover:text-foreground">
          <ArrowLeft className="size-4" />
        </Link>
        {isLoading ? (
          <Skeleton className="h-5 w-48" />
        ) : (
          <div className="flex items-center gap-2">
            <span className="font-medium">{repo?.repo_key}</span>
            <span className="text-sm text-muted-foreground">
              {repo?.chunking_strategy} · {repo?.search_method}
            </span>
          </div>
        )}
      </header>

      <div className="grid flex-1 grid-cols-1 md:grid-cols-2">
        <section className="flex min-h-0 flex-col border-r">
          <ChatPanel
            key={repoKey}
            repoKey={repoKey}
            onOpenCitation={openCitation}
            activeCitation={target?.start != null ? { path: target.path, start: target.start, end: target.end ?? target.start } : null}
          />
        </section>

        <section className="flex min-h-0 flex-col">
          <Tabs value={tab} onValueChange={setTab} className="flex min-h-0 flex-1 flex-col gap-0">
            <TabsList className="w-full justify-start rounded-none border-b bg-transparent px-2">
              <TabsTrigger value="source" className="gap-1.5">
                <FileCode2 className="size-3.5" />
                Source
              </TabsTrigger>
              <TabsTrigger value="files" className="gap-1.5">
                <Files className="size-3.5" />
                Files
              </TabsTrigger>
            </TabsList>
            <TabsContent value="source" className="min-h-0 flex-1">
              <SourceViewer repoKey={repoKey} target={target} />
            </TabsContent>
            <TabsContent value="files" className="min-h-0 flex-1">
              <FileTree repoKey={repoKey} selectedPath={target?.path} onSelectFile={openFile} />
            </TabsContent>
          </Tabs>
        </section>
      </div>
    </main>
  );
}
