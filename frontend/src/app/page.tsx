'use client';

import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useRouter } from 'next/navigation';
import { FolderGit2, Info, Loader2, Minus, Pencil, Plus, Trash2 } from 'lucide-react';
import { api, ApiError, streamJobEvents } from '@/lib/api';
import type { JobStatus, RepoSummary } from '@/lib/types';
import { IngestForm, type StartedIngestion } from '@/components/IngestForm';
import { RenameRepoDialog, type RenameTarget } from '@/components/RenameRepoDialog';
import { RepoStatsDialog } from '@/components/RepoStatsDialog';
import { Button } from '@/components/ui/button';
import { Card, CardAction, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Skeleton } from '@/components/ui/skeleton';

interface DeleteTarget {
  repo_key: string;
  display_name: string | null;
  pending?: boolean;
}

export default function HomePage() {
  const router = useRouter();
  const queryClient = useQueryClient();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [repoToDelete, setRepoToDelete] = useState<DeleteTarget | null>(null);
  const [repoToRename, setRepoToRename] = useState<RenameTarget | null>(null);
  const [repoToInspect, setRepoToInspect] = useState<RepoSummary | null>(null);

  // The one ingestion allowed at a time. Set the moment the job is accepted
  // (before any real work happens), so the card and the "New project" lockout
  // both appear immediately - not once the pipeline gets around to reporting
  // progress.
  const [activeIngestion, setActiveIngestion] = useState<StartedIngestion | null>(null);
  const [jobStatus, setJobStatus] = useState<JobStatus | null>(null);
  const [ingestError, setIngestError] = useState<string | null>(null);

  const { data: repos, isLoading } = useQuery({ queryKey: ['repos'], queryFn: api.listRepos });

  // Read inside the SSE loop below without retriggering the subscription -
  // only matters at the moment the job actually finishes.
  const dialogOpenRef = useRef(dialogOpen);
  useEffect(() => {
    dialogOpenRef.current = dialogOpen;
  }, [dialogOpen]);

  // Owns the job's SSE subscription for as long as it's in flight, regardless
  // of whether the dialog showing it is open or minimized - a minimized job
  // still needs to flip the homepage card to "ready" (or drop it) on its own.
  useEffect(() => {
    if (!activeIngestion) return;
    const jobId = activeIngestion.jobId;
    const controller = new AbortController();
    let settled = false;

    (async () => {
      try {
        for await (const status of streamJobEvents(jobId, controller.signal)) {
          setJobStatus(status);

          if (status.status === 'succeeded' && status.result && !settled) {
            settled = true;
            const repoKey = status.result.repo_key;
            queryClient.invalidateQueries({ queryKey: ['repos'] });
            setActiveIngestion(null);
            setJobStatus(null);
            if (dialogOpenRef.current) {
              setDialogOpen(false);
              router.push(`/repo/${repoKey}`);
            }
            break;
          }

          if (status.status === 'failed' && !settled) {
            settled = true;
            setIngestError(status.error ?? 'Ingestion failed.');
            setActiveIngestion(null);
            setJobStatus(null);
            break;
          }
        }
      } catch {
        // AbortError from our own cleanup below (dialog deleted the job, or
        // this effect is re-running) - anything else is a real dropped
        // connection, which we treat the same as a failure.
        if (!settled && !controller.signal.aborted) {
          setIngestError('Lost connection to the ingestion job.');
          setActiveIngestion(null);
          setJobStatus(null);
        }
      }
    })();

    return () => controller.abort();
    // Depend only on the job id, not the whole object - renaming the pending
    // card updates activeIngestion.displayName and must not restart the
    // subscription.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeIngestion?.jobId, queryClient, router]);

  const deleteRepo = useMutation({
    mutationFn: async (target: DeleteTarget) => {
      if (target.pending && activeIngestion) {
        try {
          await api.cancelJob(activeIngestion.jobId);
        } catch {
          // best effort - the job may already be done
        }
      }
      try {
        await api.deleteRepo(target.repo_key);
      } catch (e) {
        // A pending repo may not have downloaded far enough to exist on disk
        // yet - nothing to delete is a success, not a failure, in that case.
        if (!target.pending || !(e instanceof ApiError) || e.status !== 404) throw e;
      }
    },
    onSuccess: (_data, target) => {
      queryClient.invalidateQueries({ queryKey: ['repos'] });
      if (target.pending) {
        setActiveIngestion(null);
        setJobStatus(null);
        setDialogOpen(false);
      }
      setRepoToDelete(null);
    },
  });

  const pendingRepoKey = activeIngestion?.repoKey;
  const displayJob: JobStatus | null = activeIngestion
    ? jobStatus ?? {
        id: activeIngestion.jobId, kind: '', status: 'pending', phase: null,
        message: 'Starting…', error: null, result: null, created_at: 0, progress: null,
      }
    : null;

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 px-6 py-12">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">RAGBot</h1>
          <p className="text-muted-foreground">Ask questions about your source code and docs.</p>
        </div>
        <Dialog
          open={dialogOpen}
          onOpenChange={(open, eventDetails) => {
            // While a job is running, the dialog can only be minimized (via
            // the explicit button below), never closed out from under it via
            // the X button, Escape, or an outside click.
            if (!open && activeIngestion) {
              eventDetails.cancel();
              return;
            }
            setDialogOpen(open);
          }}
        >
          <DialogTrigger
            render={
              <Button
                disabled={!!activeIngestion}
                title={activeIngestion ? 'An ingestion is already in progress' : undefined}
              />
            }
          >
            <Plus className="size-4" />
            New project
          </DialogTrigger>
          <DialogContent className="sm:max-w-2xl p-8 gap-6" showCloseButton={!activeIngestion}>
            <DialogHeader className={activeIngestion ? 'flex-row items-center justify-between space-y-0 pr-8' : undefined}>
              <DialogTitle className="text-2xl">Ingest sources</DialogTitle>
              {activeIngestion && (
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  aria-label="Minimize"
                  title="Minimize - the ingestion keeps running in the background"
                  onClick={() => setDialogOpen(false)}
                >
                  <Minus className="size-4" />
                </Button>
              )}
            </DialogHeader>
            <IngestForm
              job={displayJob}
              error={ingestError}
              onStarted={(info) => {
                setIngestError(null);
                setJobStatus(null);
                setActiveIngestion(info);
              }}
            />
          </DialogContent>
        </Dialog>
      </div>

      <div className="space-y-3">
        {isLoading &&
          Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} className="h-20 w-full" />)}

        {!isLoading && !activeIngestion && repos?.length === 0 && (
          <Card className="border-dashed">
            <CardContent className="flex flex-col items-center gap-3 py-12 text-center text-muted-foreground">
              <FolderGit2 className="size-8" />
              <p>No repositories yet. Ingest one to start chatting with its code.</p>
            </CardContent>
          </Card>
        )}

        {activeIngestion && (
          <Card className="border-primary/30 bg-primary/5">
            <CardHeader>
              <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                <Loader2 className="size-4 shrink-0 animate-spin text-primary" />
                <span className="truncate">{activeIngestion.displayName}</span>
              </CardTitle>
              <CardAction className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-foreground"
                  aria-label="View ingestion progress"
                  onClick={() => setDialogOpen(true)}
                >
                  <Info className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Rename ${activeIngestion.displayName}`}
                  onClick={() =>
                    setRepoToRename({ repo_key: activeIngestion.repoKey, display_name: activeIngestion.displayName })
                  }
                >
                  <Pencil className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-destructive"
                  aria-label={`Delete ${activeIngestion.displayName}`}
                  onClick={() =>
                    setRepoToDelete({ repo_key: activeIngestion.repoKey, display_name: activeIngestion.displayName, pending: true })
                  }
                >
                  <Trash2 className="size-4" />
                </Button>
              </CardAction>
            </CardHeader>
            <CardContent>
              <span className="text-sm text-muted-foreground">
                Still ingesting — {displayJob?.message || 'starting…'}
              </span>
            </CardContent>
          </Card>
        )}

        {repos?.filter((repo) => repo.repo_key !== pendingRepoKey).map((repo) => (
          <Card
            key={repo.repo_key}
            className="cursor-pointer transition-colors hover:bg-accent/50"
            onClick={() => router.push(`/repo/${repo.repo_key}`)}
          >
            <CardHeader>
              <CardTitle className="flex min-w-0 items-center gap-2 text-base">
                <FolderGit2 className="size-4 shrink-0 text-muted-foreground" />
                <span className="truncate">{repo.display_name ?? repo.repo_key}</span>
              </CardTitle>
              <CardAction className="flex items-center gap-1">
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`View info for ${repo.repo_key}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setRepoToInspect(repo);
                  }}
                >
                  <Info className="size-4" />
                </Button>
                <Button
                  variant="ghost"
                  size="icon-sm"
                  className="text-muted-foreground hover:text-foreground"
                  aria-label={`Rename ${repo.repo_key}`}
                  onClick={(e) => {
                    e.stopPropagation();
                    setRepoToRename(repo);
                  }}
                >
                  <Pencil className="size-4" />
                </Button>
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
            <CardContent className="flex flex-col gap-1">
              {repo.display_name && (
                <span className="truncate font-mono text-xs text-muted-foreground/70">{repo.repo_key}</span>
              )}
              <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted-foreground">
                <span>{repo.file_count} files</span>
                {repo.chunk_count != null && <span>{repo.chunk_count} chunks</span>}
                <span>{repo.indexed ? 'Indexed' : 'Not indexed'}</span>
                <span>{new Date(repo.downloaded_at).toLocaleString()}</span>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Dialog open={!!repoToDelete} onOpenChange={(open) => !open && setRepoToDelete(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Delete this project?</DialogTitle>
          </DialogHeader>
          <p className="text-sm text-muted-foreground">
            {repoToDelete?.pending ? (
              <>
                This stops the in-progress ingestion for{' '}
                <span className="font-mono text-foreground">{repoToDelete?.display_name}</span> and removes
                anything already downloaded, cached, or indexed for it. This can&apos;t be undone.
              </>
            ) : (
              <>
                This permanently deletes the cached files and index for{' '}
                <span className="font-mono text-foreground">{repoToDelete?.display_name ?? repoToDelete?.repo_key}</span>.
                This can&apos;t be undone — you&apos;ll need to re-ingest it to chat with it again.
              </>
            )}
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
              onClick={() => repoToDelete && deleteRepo.mutate(repoToDelete)}
              disabled={deleteRepo.isPending}
            >
              {deleteRepo.isPending ? 'Deleting…' : 'Delete'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <RenameRepoDialog
        repo={repoToRename}
        onClose={() => setRepoToRename(null)}
        onRenamed={(repoKey, displayName) => {
          queryClient.invalidateQueries({ queryKey: ['repos'] });
          setActiveIngestion((prev) => (prev && prev.repoKey === repoKey ? { ...prev, displayName } : prev));
          setRepoToRename(null);
        }}
      />

      <RepoStatsDialog repo={repoToInspect} onClose={() => setRepoToInspect(null)} />
    </main>
  );
}
