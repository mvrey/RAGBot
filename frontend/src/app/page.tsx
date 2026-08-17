'use client';

import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { FolderGit2, Plus, Trash2 } from 'lucide-react';
import { api } from '@/lib/api';
import type { RepoSummary } from '@/lib/types';
import { IngestForm } from '@/components/IngestForm';
import { Button } from '@/components/ui/button';
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';

export default function HomePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [repoToDelete, setRepoToDelete] = useState<RepoSummary | null>(null);
  const { data: repos, isLoading } = useQuery({ queryKey: ['repos'], queryFn: api.listRepos });

  const openRepo = (repoKey: string) => {
    setDialogOpen(false);
    router.push(`/repo/${repoKey}`);
  };

  const deleteRepo = useMutation({
    mutationFn: (repoKey: string) => api.deleteRepo(repoKey),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repos'] });
      setRepoToDelete(null);
    },
  });

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">RAGBot</h1>
          <p className="text-muted-foreground">Ask questions about a GitHub repository&apos;s code and docs.</p>
        </div>
        <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
          <DialogTrigger render={<Button />}>
            <Plus className="size-4" />
            Ingest a repo
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl p-8 gap-6">
            <DialogHeader>
              <DialogTitle className="text-2xl">Ingest a GitHub repository</DialogTitle>
            </DialogHeader>
            <IngestForm onIngested={openRepo} />
          </DialogContent>
        </Dialog>
      </div>

      <div className="space-y-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}

        {!isLoading && repos?.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
              <FolderGit2 className="size-8" />
              <p>No repositories yet. Ingest one to start chatting with its code.</p>
            </CardContent>
          </Card>
        )}

        {repos?.map((repo) => (
          <Card
            key={repo.repo_key}
            className="cursor-pointer transition-colors hover:bg-accent/50"
            onClick={() => router.push(`/repo/${repo.repo_key}`)}
          >
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FolderGit2 className="size-4 text-muted-foreground" />
                {repo.repo_key}
              </CardTitle>
              <CardAction>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-destructive"
                  aria-label={`Delete ${repo.repo_key}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setRepoToDelete(repo);
                  }}
                >
                  <Trash2 className="size-4" />
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
              <span>{repo.file_count} files</span>
              {repo.chunk_count != null && <span>{repo.chunk_count} chunks</span>}
              <span>{repo.indexed ? 'Indexed' : 'Not indexed'}</span>
              <span>{new Date(repo.downloaded_at).toLocaleString()}</span>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={!!repoToDelete} onOpenChange={(open) => !open && setRepoToDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete this repository?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            This permanently deletes the cached files and index for{' '}
            <span className="font-mono text-foreground">{repoToDelete?.repo_key}</span>. This can&apos;t be
            undone — you&apos;ll need to re-ingest it to chat with it again.
          </p>
          {deleteRepo.isError && (
            <p className="text-sm text-destructive">Failed to delete. Try again.</p>
          )}
          <DialogFooter>
            <Button variant="outline" onClick={() => setRepoToDelete(null)} disabled={deleteRepo.isPending}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => repoToDelete && deleteRepo.mutate(repoToDelete.repo_key)}
              disabled={deleteRepo.isPending}
            >
              {deleteRepo.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </main>
  );
}
