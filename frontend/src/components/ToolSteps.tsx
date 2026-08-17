'use client';

import { useState } from 'react';
import { ChevronRight, Search, Loader2, CheckCircle2 } from 'lucide-react';
import type { ToolStep } from '@/hooks/useChat';
import { cn } from '@/lib/utils';

/** Collapsible "what the agent did" steps, built from tool_call/tool_result events. */
export function ToolSteps({ steps }: { steps: ToolStep[] }) {
  const [open, setOpen] = useState(true);

  if (steps.length === 0) return null;

  return (
    <div className="mb-2 rounded-md border bg-muted/40 text-xs">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 px-2.5 py-1.5 text-muted-foreground hover:text-foreground"
      >
        <ChevronRight className={cn('size-3.5 transition-transform', open && 'rotate-90')} />
        <Search className="size-3.5" />
        <span>{steps.length} tool {steps.length === 1 ? 'call' : 'calls'}</span>
      </button>
      {open && (
        <ul className="space-y-1 px-2.5 pb-2">
          {steps.map((step) => (
            <li key={step.id} className="flex items-start gap-1.5 text-muted-foreground">
              {step.result ? (
                <CheckCircle2 className="mt-0.5 size-3 shrink-0 text-emerald-500" />
              ) : (
                <Loader2 className="mt-0.5 size-3 shrink-0 animate-spin" />
              )}
              <span>
                <span className="font-mono text-foreground">{step.tool}</span>
                {step.args && Object.keys(step.args).length > 0 && (
                  <span className="font-mono"> ({Object.values(step.args).map(String).join(', ')})</span>
                )}
                {step.result?.summary && <span className="block truncate opacity-80">{step.result.summary}</span>}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
