// Parses "path:start-end" citations out of an answer's text, matching the
// format the backend's system prompt asks the model to use (see
// backend/ragbot/core/Prompts.py SYSTEM_PROMPT and CITATION_SUFFIX_FORMAT).
// Citations may appear bare ("src/X.py:12-34") or as a markdown link
// ("[src/X.py:12-34](https://github.com/.../X.py#L12-L34)") when the repo's
// GitHub URL is known - either form is replaced by a single clickable chip
// rather than being left as inline markdown, since the chip is what opens the
// source viewer (see CitationLink / SourceViewer).

export interface CitationMatch {
  path: string;
  start: number;
  end: number;
}

export type TextSegment = { type: 'text'; value: string };
export type CitationSegment = { type: 'citation' } & CitationMatch;
export type AnswerSegment = TextSegment | CitationSegment;

// Optional leading "[" / trailing "]" and an optional trailing "(...)" absorb
// the markdown-link wrapper the backend adds when it knows the repo's GitHub
// URL, so a citation renders as one chip either way instead of leaving stray
// bracket/URL text behind.
const CITATION_RE = /\[?([\w.\-/]+\.[A-Za-z0-9_]+):(\d+)-(\d+)\]?(?:\([^)]*\))?/g;

export function parseCitations(text: string): CitationMatch[] {
  const matches: CitationMatch[] = [];
  for (const m of text.matchAll(CITATION_RE)) {
    matches.push({ path: m[1], start: Number(m[2]), end: Number(m[3]) });
  }
  return matches;
}

/** Split an answer into alternating text and citation segments, for rendering. */
export function splitIntoSegments(text: string): AnswerSegment[] {
  const segments: AnswerSegment[] = [];
  let lastIndex = 0;

  for (const m of text.matchAll(CITATION_RE)) {
    const index = m.index ?? 0;
    if (index > lastIndex) {
      segments.push({ type: 'text', value: text.slice(lastIndex, index) });
    }
    segments.push({ type: 'citation', path: m[1], start: Number(m[2]), end: Number(m[3]) });
    lastIndex = index + m[0].length;
  }

  if (lastIndex < text.length) {
    segments.push({ type: 'text', value: text.slice(lastIndex) });
  }

  return segments;
}

export function formatCitation(citation: CitationMatch): string {
  return `${citation.path}:${citation.start}-${citation.end}`;
}

export function citationKey(citation: CitationMatch): string {
  return `${citation.path}#${citation.start}-${citation.end}`;
}
