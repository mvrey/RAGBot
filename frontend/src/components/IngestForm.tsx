'use client';

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { looksLikeRepoUrl, resolveCodeloadUrl } from '@/lib/validation';
import { JobProgress } from '@/components/JobProgress';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';

interface IngestFormProps {
  onIngested: (repoKey: string) => void;
}

export function IngestForm({ onIngested }: IngestFormProps) {
  const [repoUrl, setRepoUrl] = useState('');
  const [chunkingStrategy, setChunkingStrategy] = useState('AUTO');
  const [searchMethod, setSearchMethod] = useState('HYBRID');
  const [touched, setTouched] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [failedMessage, setFailedMessage] = useState<string | null>(null);

  const { data: config } = useQuery({ queryKey: ['config'], queryFn: api.config });

  const ingest = useMutation({
    mutationFn: async (url: string) => {
      // Resolves the repo's actual default branch via the GitHub API when the
      // URL doesn't name one - guessing "main" 404s against any repo that
      // still defaults to "master".
      const resolved = await resolveCodeloadUrl(url);
      if (!resolved) throw new Error('Enter a github.com repository URL.');
      return api.ingestRepo({ repo_url: resolved, chunking_strategy: chunkingStrategy, search_method: searchMethod });
    },
    onSuccess: (data) => setJobId(data.job_id),
  });

  const isValid = looksLikeRepoUrl(repoUrl);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setFailedMessage(null);
    if (!isValid) return;
    ingest.mutate(repoUrl);
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
      <div className="space-y-2.5">
        <label htmlFor="repo-url" className="text-base font-medium">
          GitHub repository URL
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

      <Button type="submit" size="lg" className="w-full h-14 text-lg" disabled={!repoUrl || ingest.isPending}>
        {ingest.isPending ? 'Starting…' : 'Ingest repository'}
      </Button>
    </form>
  );
}
