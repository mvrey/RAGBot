from enum import Enum


class ChunkingStrategy(Enum):
    # AUTO dispatches per file (code -> AST, markdown -> headings, rest -> windows);
    # the others force one strategy across every file and exist mainly for comparison.
    AUTO = 'auto'
    CODE = 'code'
    MARKDOWN = 'markdown'
    PARAGRAPH = 'paragraph'
    CHARACTER = 'character'
    LLM = 'llm'

    def chunk(self, repository):
        return repository.chunk(self)
