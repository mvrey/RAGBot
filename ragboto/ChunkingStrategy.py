from enum import Enum

class ChunkingStrategy(Enum):
    CHARACTER = 'character'
    PARAGRAPH = 'paragraph' 
    MARKDOWN = 'markdown'
    LLM = 'llm'
    
    def chunk(self, doc_handler):
        if self == ChunkingStrategy.CHARACTER:
            return doc_handler.chunk_by_characters()
        elif self == ChunkingStrategy.PARAGRAPH:
            return doc_handler.chunk_by_paragraphs()
        elif self == ChunkingStrategy.MARKDOWN:
            return doc_handler.chunk_by_markdown_headings()
        elif self == ChunkingStrategy.LLM:
            return doc_handler.llm_chunking()