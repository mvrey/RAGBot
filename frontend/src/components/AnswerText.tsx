'use client';

import { Fragment } from 'react';
import { CitationLink } from '@/components/CitationLink';
import { citationKey, splitIntoSegments, type CitationMatch } from '@/lib/citations';

interface AnswerTextProps {
  text: string;
  onOpenCitation: (citation: CitationMatch) => void;
  activeCitation?: CitationMatch | null;
}

/** Renders an assistant answer as flowing text with inline, clickable citation chips. */
export function AnswerText({ text, onOpenCitation, activeCitation }: AnswerTextProps) {
  const segments = splitIntoSegments(text);

  return (
    <p className="whitespace-pre-wrap break-words leading-relaxed">
      {segments.map((segment, i) =>
        segment.type === 'text' ? (
          <Fragment key={i}>{segment.value}</Fragment>
        ) : (
          <CitationLink
            key={citationKey(segment) + i}
            citation={segment}
            onOpen={onOpenCitation}
            active={
              !!activeCitation &&
              activeCitation.path === segment.path &&
              activeCitation.start === segment.start &&
              activeCitation.end === segment.end
            }
          />
        ),
      )}
    </p>
  );
}
