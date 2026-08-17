import re
from ragbot.core.Prompts import Prompts
from ragbot.core.OpenAIAPI import OpenAIAPI

class TextChunker:

    def __init__(self, text: str):
        self.text = text


    # Simple sliding window chunking by characters
    def sliding_window(self, seq, size, step):
        if size <= 0 or step <= 0:
            raise ValueError("size and step must be positive")

        n = len(seq)
        result = []
        for i in range(0, n, step):
            chunk = seq[i:i+size]
            result.append({'start': i, 'chunk': chunk})
            if i + size >= n:
                break
        return result


    #Chunking by paraghps
    def chunk_by_paragraphs(self, text):
        paragraphs = []
        line_number = 1

        for block in re.split(r"\n\s*\n", text):
            block_lines = block.count('\n') + 1
            if block.strip():
                paragraphs.append({
                    'chunk': block.strip(),
                    'body': block.strip(),
                    'symbol': '',
                    'kind': 'paragraph',
                    'start_line': line_number,
                    'end_line': line_number + block_lines - 1,
                })
            # +1 for the blank line the split consumed.
            line_number += block_lines + 1

        return paragraphs


    #chunking by levels of headings
    def split_markdown_by_level(self, text, level=2):
        """Split markdown at the given heading level, tracking line numbers.

        Line numbers matter as much here as they do for code: markdown answers get
        cited the same way, so a section without a line range cannot be linked.
        """
        lines = text.splitlines()
        heading_pattern = re.compile(r'^(#{' + str(level) + r'} )(.+)$')

        # Each boundary is where a section starts; the preamble before the first
        # heading is a section too, otherwise intros go unindexed.
        boundaries = []
        for offset, line in enumerate(lines):
            match = heading_pattern.match(line)
            if match:
                boundaries.append((offset, match.group(2).strip()))

        if not boundaries:
            return []

        sections = []
        if boundaries[0][0] > 0:
            sections.append(self._markdown_section(lines, 0, boundaries[0][0] - 1, ''))

        for index, (start, title) in enumerate(boundaries):
            end = boundaries[index + 1][0] - 1 if index + 1 < len(boundaries) else len(lines) - 1
            sections.append(self._markdown_section(lines, start, end, title))

        return [s for s in sections if s]


    def _markdown_section(self, lines, start, end, title):
        body = '\n'.join(lines[start:end + 1]).strip()
        if not body:
            return None
        return {
            'chunk': body,
            'body': body,
            'symbol': title,
            'kind': 'section',
            'start_line': start + 1,
            'end_line': end + 1,
        }



    def intelligent_chunking(self, text):
        prompt = Prompts.CHUNKING_PROMPT.strip().format(document=text)
        openai_api = OpenAIAPI()

        messages = [
            {"role": "user", "content": prompt}
        ]

        response = openai_api.send_prompt(messages)
        sections = response.split('---')
        sections = [s.strip() for s in sections if s.strip()]
        return sections