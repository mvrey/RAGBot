'use client';

import { FileCode2 } from 'lucide-react';
import { formatCitation, type CitationMatch } from '@/lib/citations';
import { cn } from '@/lib/utils';

interface CitationLinkProps {
  citation: CitationMatch;
  onOpen: (citation: CitationMatch) => void;
  active?: boolean;
}

/** A clickable chip for one path:start-end citation - opens it in the source viewer. */
export function CitationLink({ citation, onOpen, active }: CitationLinkProps) {
  return (
    <button
      type="button"
      onClick={() => onOpen(citation)}
      title={`Open ${formatCitation(citation)}`}
      className={cn(
        'inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 align-middle font-mono text-xs',
        'border-border bg-muted hover:bg-accent hover:text-accent-foreground transition-colors cursor-pointer',
        active && 'border-primary bg-primary/10 text-primary',
      )}
    >
      <FileCode2 className="size-3" />
      {formatCitation(citation)}
    </button>
  );
}
