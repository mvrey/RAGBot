'use client';

import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { api } from '@/lib/api';
import { isValidCodeloadUrl, toCodeloadUrl } from '@/lib/validation';
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
    mutationFn: (url: string) => api.ingestRepo({ repo_url: url, chunking_strategy: chunkingStrategy, search_method: searchMethod }),
    onSuccess: (data) => setJobId(data.job_id),
  });

  const normalizedUrl = isValidCodeloadUrl(repoUrl) ? repoUrl.trim() : toCodeloadUrl(repoUrl) ?? '';
  const isValid = isValidCodeloadUrl(normalizedUrl);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setTouched(true);
    setFailedMessage(null);
    if (!isValid) return;
    ingest.mutate(normalizedUrl);
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
    <form onSubmit={handleSubmit} className="space-y-4">
      <div className="space-y-1.5">
        <label htmlFor="repo-url" className="text-sm font-medium">
          GitHub repository URL
        </label>
        <Input
          id="repo-url"
          placeholder="https://github.com/owner/repo"
          value={repoUrl}
          onChange={(e) => setRepoUrl(e.target.value)}
          onBlur={() => setTouched(true)}
        />
        {touched && repoUrl && !isValid && (
          <p className="text-xs text-destructive">
            Enter a github.com repository URL, e.g. https://github.com/owner/repo
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Chunking method</label>
          <Select value={chunkingStrategy} onValueChange={(value) => value && setChunkingStrategy(value)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(config?.chunking_strategies ?? []).map((option) => (
                <SelectItem key={option.name} value={option.name}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <label className="text-sm font-medium">Search method</label>
          <Select value={searchMethod} onValueChange={(value) => value && setSearchMethod(value)}>
            <SelectTrigger className="w-full">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(config?.search_methods ?? []).map((option) => (
                <SelectItem key={option.name} value={option.name}>
                  {option.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {(ingest.isError || failedMessage) && (
        <p className="text-sm text-destructive">
          {failedMessage ?? (ingest.error instanceof Error ? ingest.error.message : 'Ingestion failed.')}
        </p>
      )}

      <Button type="submit" className="w-full" disabled={!repoUrl || ingest.isPending}>
        {ingest.isPending ? 'Starting…' : 'Ingest repository'}
      </Button>
    </form>
  );
}
