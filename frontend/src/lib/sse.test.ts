import { describe, expect, it } from 'vitest';
import { parseSSEChunk, readSSEStream } from './sse';

describe('parseSSEChunk', () => {
  it('parses a single event with event and data lines', () => {
    const { events, rest } = parseSSEChunk('event: token\r\ndata: {"delta":"hi"}\r\n\r\n');
    expect(events).toEqual([{ event: 'token', data: '{"delta":"hi"}' }]);
    expect(rest).toBe('');
  });

  it('parses multiple events separated by blank lines', () => {
    const buffer = 'event: token\r\ndata: {"delta":"a"}\r\n\r\nevent: token\r\ndata: {"delta":"b"}\r\n\r\n';
    const { events } = parseSSEChunk(buffer);
    expect(events).toEqual([
      { event: 'token', data: '{"delta":"a"}' },
      { event: 'token', data: '{"delta":"b"}' },
    ]);
  });

  it('keeps an incomplete trailing event as the remainder', () => {
    const { events, rest } = parseSSEChunk('event: token\r\ndata: {"delta":"a"}\r\n\r\nevent: tok');
    expect(events).toEqual([{ event: 'token', data: '{"delta":"a"}' }]);
    expect(rest).toBe('event: tok');
  });

  it('defaults to a "message" event type when none is given', () => {
    const { events } = parseSSEChunk('data: hello\n\n');
    expect(events).toEqual([{ event: 'message', data: 'hello' }]);
  });

  it('joins multi-line data fields with newlines', () => {
    const { events } = parseSSEChunk('event: token\ndata: line1\ndata: line2\n\n');
    expect(events).toEqual([{ event: 'token', data: 'line1\nline2' }]);
  });

  it('ignores comment lines', () => {
    const { events } = parseSSEChunk(': ping - keepalive\n\nevent: token\ndata: hi\n\n');
    expect(events).toEqual([{ event: 'token', data: 'hi' }]);
  });

  it('tolerates plain \\n separators, not just \\r\\n', () => {
    const { events } = parseSSEChunk('event: done\ndata: {"ok":true}\n\n');
    expect(events).toEqual([{ event: 'done', data: '{"ok":true}' }]);
  });

  it('skips events with no data field', () => {
    const { events } = parseSSEChunk('event: ping\n\nevent: token\ndata: hi\n\n');
    expect(events).toEqual([{ event: 'token', data: 'hi' }]);
  });
});

function fakeResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (i < chunks.length) {
        controller.enqueue(encoder.encode(chunks[i++]));
      } else {
        controller.close();
      }
    },
  });
  return new Response(stream);
}

describe('readSSEStream', () => {
  it('yields events as they arrive across multiple network chunks', async () => {
    const response = fakeResponse(['event: token\r\ndata: {"delta":"a"}\r\n\r\n', 'event: done\r\ndata: {}\r\n\r\n']);

    const collected = [];
    for await (const event of readSSEStream(response)) {
      collected.push(event);
    }

    expect(collected).toEqual([
      { event: 'token', data: '{"delta":"a"}' },
      { event: 'done', data: '{}' },
    ]);
  });

  it('reassembles a single event split across chunk boundaries', async () => {
    const response = fakeResponse(['event: to', 'ken\r\ndata: {"delta":"a"}', '\r\n\r\n']);

    const collected = [];
    for await (const event of readSSEStream(response)) {
      collected.push(event);
    }

    expect(collected).toEqual([{ event: 'token', data: '{"delta":"a"}' }]);
  });

  it('throws if the response has no body', async () => {
    const response = new Response(null);
    await expect(readSSEStream(response).next()).rejects.toThrow('no body');
  });
});
