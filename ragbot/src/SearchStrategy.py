from enum import Enum

from src.TextSearcher import TextSearcher


class SearchStrategyType(Enum):
    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


class SearchStrategy:
    def __init__(self, embedder=None):
        self.searcher = TextSearcher(embedder=embedder)

    def execute_strategy(self, strategy: SearchStrategyType, query, chunks, num_results=5):
        if strategy == SearchStrategyType.TEXT:
            return self.searcher.text_search(query, chunks, num_results=num_results)
        elif strategy == SearchStrategyType.VECTOR:
            return self.searcher.vector_search(query, chunks, num_results=num_results)
        elif strategy == SearchStrategyType.HYBRID:
            return self.searcher.hybrid_search(query, chunks, num_results=num_results)
        else:
            raise ValueError("Invalid search strategy")
