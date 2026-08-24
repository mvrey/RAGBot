// Server-Sent Events framing, parsed from a fetch() ReadableStream rather than
// the browser's native EventSource: EventSource only supports GET, but
// POST /api/conversations/{id}/messages needs a JSON body to send the
// question. One parser covers both the GET job-events stream and the POST
// chat stream.
//
// sse-starlette (the backend's SSE library) separates fields within one event
// by "\r\n" and separates events with a blank line, per the SSE spec. This
// parser is line-ending tolerant (\r\n, \r, or \n) since that separator is a
// server-side implementation detail, not part of the wire contract.

export interface RawSSEEvent {
  event: string;
  data: string;
}

/** Split raw SSE text into events. Exported for the parts that don't need a stream. */
export function parseSSEChunk(buffer: string): { events: RawSSEEvent[]; rest: string } {
  const blocks = buffer.split(/\r\n\r\n|\n\n|\r\r/);
  // The last block is either empty (buffer ended right on a boundary) or a
  // partial event still waiting for more bytes - either way, keep it as the
  // remainder rather than parsing it.
  const rest = blocks.pop() ?? '';

  const events: RawSSEEvent[] = [];
  for (const block of blocks) {
    if (!block.trim()) continue;
    let event = 'message';
    const dataLines: string[] = [];
    for (const line of block.split(/\r\n|\r|\n/)) {
      if (line.startsWith('event:')) {
        event = line.slice('event:'.length).trim();
      } else if (line.startsWith('data:')) {
        dataLines.push(line.slice('data:'.length).trim());
      }
      // Comment lines (":...") and other fields (id:, retry:) are ignored -
      // nothing in this app's contract uses them.
    }
    if (dataLines.length > 0) {
      events.push({ event, data: dataLines.join('\n') });
    }
  }
  return { events, rest };
}

/** Consume a fetch Response's body as a stream of parsed SSE events. */
export async function* readSSEStream(response: Response): AsyncGenerator<RawSSEEvent> {
  if (!response.body) {
    throw new Error('Response has no body to stream.');
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const { events, rest } = parseSSEChunk(buffer);
      buffer = rest;
      for (const event of events) {
        yield event;
      }
    }
    // Flush a final event that arrived without a trailing blank line.
    const { events } = parseSSEChunk(buffer + '\n\n');
    for (const event of events) {
      yield event;
    }
  } finally {
    reader.releaseLock();
  }
}
