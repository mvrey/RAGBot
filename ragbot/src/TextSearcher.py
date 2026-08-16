import numpy as np
from minsearch import Index, VectorSearch

from src.Embeddings import get_embedder

# Reciprocal rank fusion constant. 60 is the value from the original RRF paper and
# is the usual default; it damps the influence of the top rank just enough that one
# retriever cannot dominate the other.
RRF_K = 60


class TextSearcher:

    def __init__(self, embedder=None):
        # A fresh TextSearcher/SearchStrategy is created each time the repo is
        # (re-)indexed in the app, so caching indices for the instance's lifetime
        # is safe and avoids rebuilding them (and re-embedding every chunk) on
        # every single query.
        self._text_index = None
        self._vector_index = None
        self._embedder = embedder or get_embedder()


    def _get_text_index(self, chunks):
        if self._text_index is None:
            index = Index(
                # 'symbol' matters as much as the body: TF-IDF keeps identifiers like
                # hybrid_search whole, so symbol lookups hit even when wording differs.
                text_fields=["chunk", "symbol", "filename", "title", "description"],
                keyword_fields=[]
            )
            index.fit(chunks)
            self._text_index = index
        return self._text_index


    def _get_vector_index(self, chunks):
        if self._vector_index is None:
            texts = [c.get('chunk', '') for c in chunks]
            embeddings = self._embedder.encode(texts)

            vector_index = VectorSearch()
            vector_index.fit(np.array(embeddings), chunks)
            self._vector_index = vector_index
        return self._vector_index


    def text_search(self, query, chunks, num_results=5):
        index = self._get_text_index(chunks)
        return index.search(query, num_results=num_results)


    def vector_search(self, query, chunks, num_results=5):
        vector_index = self._get_vector_index(chunks)
        query_vector = self._embedder.encode(query)
        return vector_index.search(query_vector, num_results=num_results)


    def hybrid_search(self, query, chunks, num_results=5):
        """Combine keyword and vector hits with reciprocal rank fusion.

        Naive concatenation would always rank every keyword hit above every vector
        hit regardless of relevance; RRF scores each result by its rank in both
        lists, so agreement between the two retrievers is what wins.
        """
        text_results = self.text_search(query, chunks, num_results=num_results) or []
        vector_results = self.vector_search(query, chunks, num_results=num_results) or []

        scores = {}
        seen = {}

        for results in (text_results, vector_results):
            for rank, result in enumerate(results):
                key = self._result_key(result)
                seen.setdefault(key, result)
                scores[key] = scores.get(key, 0.0) + 1.0 / (RRF_K + rank + 1)

        ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
        return [seen[key] for key, _ in ranked[:num_results]]


    @staticmethod
    def _result_key(result):
        # Prefer location over text: the same snippet can legitimately appear in
        # two files, and those are different results.
        return (
            result.get('filename', ''),
            result.get('start_line', ''),
            result.get('end_line', ''),
            result.get('chunk', '')[:200],
        )
