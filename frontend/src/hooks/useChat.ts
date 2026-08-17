'use client';

import { useCallback, useRef, useState } from 'react';
import { streamAsk } from '@/lib/api';
import type { Citation, DoneEventData, MessageOut, ToolCallEventData, ToolResultEventData } from '@/lib/types';

export interface ToolStep {
  id: string;
  tool: string;
  args?: ToolCallEventData['args'];
  result?: ToolResultEventData;
}

/** A chat message, optionally carrying the usage of the turn that produced it -
 * only ever set for assistant messages from *this* session (the done event is
 * live-only, not persisted server-side), which is enough to answer "why did
 * this message cost what it cost" right where the answer appears. */
export interface ChatMessage extends MessageOut {
  usage?: DoneEventData['usage'];
}

interface UseChatState {
  messages: ChatMessage[];
  streamingAnswer: string;
  streamingCitations: Citation[];
  toolSteps: ToolStep[];
  isStreaming: boolean;
  error: string | null;
}

/** Drives one conversation's message stream: sends a question, plays back SSE
 * events (tokens / tool calls / citations / done / error) into render state. */
export function useChat(conversationId: string | null, initialMessages: MessageOut[] = []) {
  const [state, setState] = useState<UseChatState>({
    messages: initialMessages,
    streamingAnswer: '',
    streamingCitations: [],
    toolSteps: [],
    isStreaming: false,
    error: null,
  });
  const abortRef = useRef<AbortController | null>(null);

  const setMessages = useCallback((messages: MessageOut[]) => {
    setState((s) => ({ ...s, messages }));
  }, []);

  const send = useCallback(
    async (content: string) => {
      if (!conversationId || state.isStreaming) return;

      const controller = new AbortController();
      abortRef.current = controller;

      setState((s) => ({
        ...s,
        messages: [...s.messages, { role: 'user', content, citations: [] }],
        streamingAnswer: '',
        streamingCitations: [],
        toolSteps: [],
        isStreaming: true,
        error: null,
      }));

      let answer = '';
      const citations: Citation[] = [];
      const toolCallsById = new Map<string, ToolStep>();

      try {
        for await (const event of streamAsk(conversationId, content, controller.signal)) {
          if (event.event === 'token') {
            answer += event.data.delta;
            setState((s) => ({ ...s, streamingAnswer: answer }));
          } else if (event.event === 'tool_call') {
            const id = `${toolCallsById.size}:${event.data.tool}`;
            toolCallsById.set(id, { id, tool: event.data.tool, args: event.data.args });
            setState((s) => ({ ...s, toolSteps: Array.from(toolCallsById.values()) }));
          } else if (event.event === 'tool_result') {
            const pending = Array.from(toolCallsById.values()).find((t) => !t.result && t.tool === event.data.tool);
            if (pending) pending.result = event.data;
            setState((s) => ({ ...s, toolSteps: Array.from(toolCallsById.values()) }));
          } else if (event.event === 'citation') {
            citations.push(event.data);
            setState((s) => ({ ...s, streamingCitations: [...citations] }));
          } else if (event.event === 'error') {
            setState((s) => ({ ...s, error: event.data.detail, isStreaming: false }));
            return;
          } else if (event.event === 'done') {
            setState((s) => ({
              messages: [
                ...s.messages,
                { role: 'assistant', content: answer, citations: [...citations], usage: event.data.usage },
              ],
              streamingAnswer: '',
              streamingCitations: [],
              toolSteps: s.toolSteps,
              isStreaming: false,
              error: null,
            }));
          }
        }
      } catch (err) {
        if ((err as Error).name !== 'AbortError') {
          setState((s) => ({ ...s, error: (err as Error).message, isStreaming: false }));
        }
      }
    },
    [conversationId, state.isStreaming],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return { ...state, send, stop, setMessages };
}
