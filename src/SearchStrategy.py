from enum import Enum
import numpy as np
from src.TextSearcher import TextSearcher


class SearchStrategyType(Enum):
    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


class SearchStrategy:
    def __init__(self):
        self.searcher = TextSearcher()

    def execute_strategy(self, strategy: SearchStrategyType, query, dtc_fastapi):
        if strategy == SearchStrategyType.TEXT:
            return self.searcher.text_search(query, dtc_fastapi)
        elif strategy == SearchStrategyType.VECTOR:
            return self.searcher.vector_search(query, dtc_fastapi)
        elif strategy == SearchStrategyType.HYBRID:
            return self.searcher.hybrid_search(query, dtc_fastapi)
        else:
            raise ValueError("Invalid search strategy")