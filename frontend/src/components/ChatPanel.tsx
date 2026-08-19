'use client';

import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Send, Trash2, Loader2, Gauge } from 'lucide-react';
import { api } from '@/lib/api';
import { useChat } from '@/hooks/useChat';
import type { CitationMatch } from '@/lib/citations';
import type { DoneEventData } from '@/lib/types';
import { AnswerText } from '@/components/AnswerText';
import { ToolSteps } from '@/components/ToolSteps';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface ChatPanelProps {
  repoKey: string;
  onOpenCitation: (citation: CitationMatch) => void;
  activeCitation?: CitationMatch | null;
}

export function ChatPanel({ repoKey, onOpenCitation, activeCitation }: ChatPanelProps) {
  const queryClient = useQueryClient();
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const createConversation = useMutation({
    mutationFn: () => api.createConversation({ repo_key: repoKey }),
    onSuccess: (data) => setConversationId(data.conversation_id),
  });

  useEffect(() => {
    // Parent mounts this component with key={repoKey}, so a repo switch is a
    // fresh mount rather than a repoKey change on the same instance - this
    // only ever needs to run once.
    createConversation.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const { data: conversation } = useQuery({
    queryKey: ['conversation', conversationId],
    queryFn: () => api.getConversation(conversationId!),
    enabled: !!conversationId,
    staleTime: Infinity,
  });

  const chat = useChat(conversationId, conversation?.messages ?? []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }, [chat.messages, chat.streamingAnswer]);

  const clearChat = useMutation({
    mutationFn: () => api.clearConversation(conversationId!),
    onSuccess: () => {
      chat.setMessages([]);
      queryClient.invalidateQueries({ queryKey: ['conversation', conversationId] });
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const content = draft.trim();
    if (!content || chat.isStreaming) return;
    setDraft('');
    chat.send(content);
  };

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b px-4 py-2">
        <h2 className="text-sm font-medium">Chat</h2>
        <Button
          variant="ghost"
          size="sm"
          onClick={() => clearChat.mutate()}
          disabled={!conversationId || chat.messages.length === 0}
        >
          <Trash2 className="size-3.5" />
          Clear
        </Button>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="flex flex-col gap-4 p-4">
          {chat.messages.length === 0 && !chat.isStreaming && (
            <p className="text-sm text-muted-foreground">Ask a question about this repository&apos;s code.</p>
          )}

          {chat.messages.map((message, i) => (
            <div key={i} className={cn('flex', message.role === 'user' ? 'justify-end' : 'justify-start')}>
              <div
                className={cn(
                  'max-w-[85%] rounded-lg px-3 py-2 text-sm',
                  message.role === 'user' ? 'bg-primary text-primary-foreground' : 'bg-muted',
                )}
              >
                {message.role === 'assistant' ? (
                  <>
                    <AnswerText text={message.content} onOpenCitation={onOpenCitation} activeCitation={activeCitation} />
                    {message.usage && <UsageCaption usage={message.usage} />}
                  </>
                ) : (
                  <p className="whitespace-pre-wrap break-words">{message.content}</p>
                )}
              </div>
            </div>
          ))}

          {chat.isStreaming && (
            <div className="flex justify-start">
              <div className="max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm">
                <ToolSteps steps={chat.toolSteps} />
                {chat.streamingAnswer ? (
                  <AnswerText text={chat.streamingAnswer} onOpenCitation={onOpenCitation} activeCitation={activeCitation} />
                ) : (
                  <Loader2 className="size-4 animate-spin text-muted-foreground" />
                )}
              </div>
            </div>
          )}

          {chat.error && <p className="text-sm text-destructive">Error: {chat.error}</p>}
          <div ref={bottomRef} />
        </div>
      </div>

      <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t p-3">
        <Input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="Ask about the code..."
          disabled={!conversationId || chat.isStreaming}
        />
        <Button type="submit" size="icon" disabled={!draft.trim() || !conversationId || chat.isStreaming}>
          <Send className="size-4" />
        </Button>
      </form>
    </div>
  );
}

/** Per-turn cost visibility: one "message" in the UI is often several Gemini
 * calls under the hood (the agent re-searches, reads files, etc., each one
 * resending the growing conversation as input tokens) - this is what actually
 * drove the bill, and it's otherwise invisible. */
function UsageCaption({ usage }: { usage: DoneEventData['usage'] }) {
  return (
    <p className="mt-1.5 flex items-center gap-1 text-xs text-muted-foreground/70">
      <Gauge className="size-3" />
      {usage.requests} LLM {usage.requests === 1 ? 'call' : 'calls'} ·{' '}
      {usage.input_tokens.toLocaleString()} in / {usage.output_tokens.toLocaleString()} out tokens
    </p>
  );
}
