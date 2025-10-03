from enum import Enum
import numpy as np
import TextSearcher


class SearchStrategy(Enum):
    TEXT = "text"
    VECTOR = "vector"
    HYBRID = "hybrid"


    def __init__(self):
        self.searcher = TextSearcher()

    def execute_strategy(self, strategy: SearchStrategy, query, dtc_fastapi):
        if strategy == SearchStrategy.TEXT:
            return self.searcher.text_search(query, dtc_fastapi)
        elif strategy == SearchStrategy.VECTOR:
            return self.searcher.vector_search(query, dtc_fastapi)
        elif strategy == SearchStrategy.HYBRID:
            return self.searcher.hybrid_search(query, dtc_fastapi)
        else:
            raise ValueError("Invalid search strategy")