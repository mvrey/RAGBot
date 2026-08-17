'use client';

import { useRef, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { FolderOpen } from 'lucide-react';
import { api } from '@/lib/api';
import { looksLikeRepoUrl, resolveCodeloadUrl } from '@/lib/validation';
import { buildFolderUpload } from '@/lib/zipFolder';
import { JobProgress } from '@/components/JobProgress';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

interface IngestFormProps {
  onIngested: (repoKey: string) => void;
}

type Mode = 'github' | 'local';

export function IngestForm({ onIngested }: IngestFormProps) {
  const [mode, setMode] = useState<Mode>('github');
  const [repoUrl, setRepoUrl] = useState('');
  const [selectedFiles, setSelectedFiles] = useState<FileList | null>(null);
  const [chunkingStrategy, setChunkingStrategy] = useState('AUTO');
  const [searchMethod, setSearchMethod] = useState('HYBRID');
  const [touched, setTouched] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [failedMessage, setFailedMessage] = useState<string | null>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);

  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.config });

  const ingest = useMutation({
    mutationFn: async () => {
      if (mode === 'github') {
        // Resolves the repo's actual default branch via the GitHub API when
        // the URL doesn't name one - guessing "main" 404s against any repo
        // that still defaults to "master".
        const resolved = await resolveCodeloadUrl(repoUrl);
        if (!resolved) throw new Error('Enter a github.com repository URL.');
        return api.ingestRepo({ repo_url: resolved, chunking_strategy: chunkingStrategy, search_method: searchMethod });
      }

      if (!selectedFiles || selectedFiles.length === 0) throw new Error('Choose a folder to upload.');
      const { name, zipBytes } = await buildFolderUpload(selectedFiles);
      return api.uploadRepo({ zipBytes, name, chunking_strategy: chunkingStrategy, search_method: searchMethod });
    },
    onSuccess: (data) => setJobId(data.job_id),
  });

  const isValid = mode === 'github' ? looksLikeRepoUrl(repoUrl) : !!selectedFiles && selectedFiles.length > 0;
  const folderName = selectedFiles?.[0]?.webkitRelativePath.split('/')[0];

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setFailedMessage(null);
    if (!isValid) return;
    ingest.mutate();
  };

  const switchMode = (value: string) => {
    setMode(value as Mode);
    setTouched(false);
    setFailedMessage(null);
  };

  if (jobId) {
    return (
      <JobProgress
        jobId={jobId}
        onSucceeded={onIngested}
        onFailed={(message) => {
          setFailedMessage(message);
          setJobId(null);
        }}
      />
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-8">
      <Tabs value={mode} onValueChange={switchMode}>
        <TabsList>
          <TabsTrigger value="github">GitHub repository</TabsTrigger>
          <TabsTrigger value="local">Local folder</TabsTrigger>
        </TabsList>

        <TabsContent value="github" className="mt-4 rounded-lg border bg-muted/30 p-5">
          <div className="space-y-2.5">
            <label htmlFor="repo-url" className="text-base font-medium">
              Repository URL
            </label>
            <Input
              id="repo-url"
              placeholder="https://github.com/owner/repo"
              value={repoUrl}
              onChange={(e) => setRepoUrl(e.target.value)}
              onBlur={() => setTouched(true)}
              className="h-14 px-4 text-lg"
            />
            {touched && repoUrl && !isValid && (
              <p className="text-sm text-destructive">
                Enter a github.com repository URL, e.g. https://github.com/owner/repo
              </p>
            )}
          </div>
        </TabsContent>

        <TabsContent value="local" className="mt-4 rounded-lg border bg-muted/30 p-5">
          <div className="space-y-3">
            <label className="text-base font-medium">Folder</label>
            <input
              ref={folderInputRef}
              type="file"
              className="hidden"
              onChange={(e) => {
                setSelectedFiles(e.target.files);
                setTouched(true);
              }}
              // webkitdirectory/directory are non-standard but supported by
              // every major browser for exactly this "pick a folder" case;
              // React's DOM typings don't know them, hence the spread.
              {...{ webkitdirectory: '', directory: '' }}
            />
            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" variant="outline" className="h-14 px-4 text-base" onClick={() => folderInputRef.current?.click()}>
                <FolderOpen className="size-4" />
                Choose folder…
              </Button>
              {selectedFiles && selectedFiles.length > 0 && (
                <span className="text-sm text-muted-foreground">
                  <span className="font-mono text-foreground">{folderName}</span> — {selectedFiles.length} files selected
                </span>
              )}
            </div>
            {touched && !isValid && (
              <p className="text-sm text-destructive">Choose a folder to upload.</p>
            )}
            <p className="text-sm text-muted-foreground">
              Files are filtered and zipped in your browser before upload — build output, dependencies
              (node_modules, .venv, …), and binaries are skipped automatically.
            </p>
          </div>
        </TabsContent>
      </Tabs>

      <div className="grid grid-cols-2 gap-6">
        <div className="space-y-2.5">
          <label className="text-base font-medium">Chunking method</label>
          <Select value={chunkingStrategy} onValueChange={(value) => value && setChunkingStrategy(value)}>
            <SelectTrigger className="w-full data-[size=default]:h-14 px-4 text-sm">
              <SelectValue className="min-w-0 truncate" />
            </SelectTrigger>
            <SelectContent className="text-sm">
              {(config?.chunking_strategies ?? []).map((option) => (
                <SelectItem key={option.name} value={option.name} className="py-2 text-sm">
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2.5">
          <label className="text-base font-medium">Search method</label>
          <Select value={searchMethod} onValueChange={(value) => value && setSearchMethod(value)}>
            <SelectTrigger className="w-full data-[size=default]:h-14 px-4 text-sm">
              <SelectValue className="min-w-0 truncate" />
            </SelectTrigger>
            <SelectContent className="text-sm">
              {(config?.search_methods ?? []).map((option) => (
                <SelectItem key={option.name} value={option.name} className="py-2 text-sm">
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {(ingest.isError || failedMessage) && (
        <p className="text-base text-destructive">
          {failedMessage ?? (ingest.error instanceof Error ? ingest.error.message : 'Ingestion failed.')}
        </p>
      )}

      <Button type="submit" size="lg" className="w-full h-14 text-lg" disabled={!isValid || ingest.isPending}>
        {ingest.isPending ? (mode === 'local' ? 'Zipping & uploading…' : 'Starting…') : 'Ingest'}
      </Button>
    </form>
  );
}
