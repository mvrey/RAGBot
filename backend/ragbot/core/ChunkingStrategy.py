from enum import Enum


class ChunkingStrategy(Enum):
    # AUTO dispatches per file (code -> AST, markdown -> headings, rest -> windows);
    # the others force one strategy across every file and exist mainly for comparison.
    AUTO = 'auto'
    AST = 'ast'
    MARKDOWN = 'markdown'
    PARAGRAPH = 'paragraph'
    CHARACTER = 'character'
    LLM = 'llm'

    @property
    def label(self):
        """Human-readable description for the UI dropdown."""
        return {
            ChunkingStrategy.AUTO: "AUTO — per file type (recommended)",
            ChunkingStrategy.AST: "AST — tree-sitter, syntax-aware (code)",
            ChunkingStrategy.MARKDOWN: "MARKDOWN — split on headings",
            ChunkingStrategy.PARAGRAPH: "PARAGRAPH — split on blank lines",
            ChunkingStrategy.CHARACTER: "CHARACTER — fixed sliding window",
            ChunkingStrategy.LLM: "LLM — model-written sections (slow, costs tokens)",
        }[self]

    def chunk(self, repository):
        return repository.chunk(self)
