import re
from src.Prompts import Prompts
from src.OpenAIAPI import OpenAIAPI

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
        paragraphs = re.split(r"\n\s*\n", text.strip())
        return [{'chunk': p} for p in paragraphs]
    

    #chunking by levels of headings
    def split_markdown_by_level(self, text):
        level = 2  # You can adjust this to change the heading level

        header_pattern = r'^(#{' + str(level) + r'} )(.+)$'
        pattern = re.compile(header_pattern, re.MULTILINE)

        # Split and keep the headers
        parts = pattern.split(text)
        
        sections = []
        for i in range(1, len(parts), 3):
            header = parts[i] + parts[i+1]  # "## " + "Title"
            header = header.strip()

            # Get the content after this header
            content = ""
            if i+2 < len(parts):
                content = parts[i+2].strip()

            section = {'chunk': f'{header}\n\n{content}' if content else header}
            sections.append(section)
        
        return sections
    

    def intelligent_chunking(text):
        prompt = Prompts.CHUNKING_PROMPT.strip().format(document=text)
        openai_api = OpenAIAPI()

        messages = [
            {"role": "user", "content": prompt}
        ]

        response = openai_api.send_prompt(messages)
        sections = response.split('---')
        sections = [s.strip() for s in sections if s.strip()]
        return sections