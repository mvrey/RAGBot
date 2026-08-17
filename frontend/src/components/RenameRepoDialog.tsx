'use client';

import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';

export interface RenameTarget {
  repo_key: string;
  display_name: string | null;
}

interface RenameRepoDialogProps {
  repo: RenameTarget | null;
  onClose: () => void;
  onRenamed: (repoKey: string, displayName: string) => void;
}

/** Renames a repo's display label only - repo_key (routes, index cache,
 * conversations, the on-disk directory) never changes underneath it. */
export function RenameRepoDialog({ repo, onClose, onRenamed }: RenameRepoDialogProps) {
  return (
    <Dialog open={!!repo} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        {/* Keyed by repo_key so switching targets (or reopening the same one
         * after a save) starts from a fresh, correctly-initialised form
         * instead of needing an effect to reset it. */}
        {repo && <RenameForm key={repo.repo_key} repo={repo} onClose={onClose} onRenamed={onRenamed} />}
      </DialogContent>
    </Dialog>
  );
}

function RenameForm({ repo, onClose, onRenamed }: { repo: RenameTarget } & Omit<RenameRepoDialogProps, 'repo'>) {
  const [name, setName] = useState(repo.display_name ?? repo.repo_key);

  const rename = useMutation({
    mutationFn: () => api.renameRepo(repo.repo_key, { display_name: name.trim() }),
    onSuccess: (data) => onRenamed(data.repo_key, data.display_name ?? data.repo_key),
  });

  const isValid = name.trim().length > 0;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;
    rename.mutate();
  };

  return (
    <form onSubmit={handleSubmit}>
      <DialogHeader>
        <DialogTitle>Rename repository</DialogTitle>
      </DialogHeader>
      <div className="mt-4 space-y-2">
        <label htmlFor="rename-input" className="text-sm font-medium">
          Display name
        </label>
        <Input id="rename-input" value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        <p className="text-xs text-muted-foreground">
          Only changes what&apos;s shown here — <span className="font-mono">{repo.repo_key}</span> stays the
          same underneath.
        </p>
      </div>
      {rename.isError && <p className="mt-2 text-sm text-destructive">Failed to rename. Try again.</p>}
      <DialogFooter className="mt-4">
        <Button type="button" variant="outline" onClick={onClose} disabled={rename.isPending}>
          Cancel
        </Button>
        <Button type="submit" disabled={!isValid || rename.isPending}>
          {rename.isPending ? 'Saving…' : 'Save'}
        </Button>
      </DialogFooter>
    </form>
  );
}
