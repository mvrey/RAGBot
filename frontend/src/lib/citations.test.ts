import { describe, expect, it } from 'vitest';
import { citationKey, formatCitation, parseCitations, splitIntoSegments } from './citations';

describe('parseCitations', () => {
  it('finds a bare path:start-end citation', () => {
    const result = parseCitations('See src/TextSearcher.py:59-72 for details.');
    expect(result).toEqual([{ path: 'src/TextSearcher.py', start: 59, end: 72 }]);
  });

  it('finds a citation wrapped in a markdown link', () => {
    const text =
      'See [src/TextSearcher.py:59-72](https://github.com/o/r/blob/main/src/TextSearcher.py#L59-L72) for details.';
    const result = parseCitations(text);
    expect(result).toEqual([{ path: 'src/TextSearcher.py', start: 59, end: 72 }]);
  });

  it('finds multiple citations in one answer', () => {
    const text = 'Look at a.py:1-2 and also b/c.py:10-20.';
    const result = parseCitations(text);
    expect(result).toEqual([
      { path: 'a.py', start: 1, end: 2 },
      { path: 'b/c.py', start: 10, end: 20 },
    ]);
  });

  it('returns an empty array when there is nothing to cite', () => {
    expect(parseCitations('No citations here.')).toEqual([]);
  });

  it('does not treat a bare number range without a file extension as a citation', () => {
    expect(parseCitations('Between 10-20 items.')).toEqual([]);
  });
});

describe('splitIntoSegments', () => {
  it('splits text around a bare citation', () => {
    const segments = splitIntoSegments('Before src/x.py:1-2 after.');
    expect(segments).toEqual([
      { type: 'text', value: 'Before ' },
      { type: 'citation', path: 'src/x.py', start: 1, end: 2 },
      { type: 'text', value: ' after.' },
    ]);
  });

  it('collapses a markdown-link citation into a single citation segment', () => {
    const segments = splitIntoSegments('[src/x.py:1-2](https://example.com/x.py#L1-L2) done.');
    expect(segments[0]).toEqual({ type: 'citation', path: 'src/x.py', start: 1, end: 2 });
    expect(segments[1]).toEqual({ type: 'text', value: ' done.' });
  });

  it('returns a single text segment when there are no citations', () => {
    expect(splitIntoSegments('plain text')).toEqual([{ type: 'text', value: 'plain text' }]);
  });

  it('handles a citation at the very start and end of the string', () => {
    const segments = splitIntoSegments('a.py:1-2 middle b.py:3-4');
    expect(segments).toEqual([
      { type: 'citation', path: 'a.py', start: 1, end: 2 },
      { type: 'text', value: ' middle ' },
      { type: 'citation', path: 'b.py', start: 3, end: 4 },
    ]);
  });

  it('handles back-to-back citations with no text between them', () => {
    const segments = splitIntoSegments('a.py:1-2 b.py:3-4');
    expect(segments.filter((s) => s.type === 'citation')).toHaveLength(2);
  });
});

describe('formatCitation / citationKey', () => {
  it('formats a citation back to path:start-end', () => {
    expect(formatCitation({ path: 'src/x.py', start: 1, end: 2 })).toBe('src/x.py:1-2');
  });

  it('produces a stable, unique key per citation', () => {
    const a = citationKey({ path: 'src/x.py', start: 1, end: 2 });
    const b = citationKey({ path: 'src/x.py', start: 1, end: 3 });
    expect(a).not.toBe(b);
  });
});
