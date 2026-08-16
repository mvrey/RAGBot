import json

import numpy as np
import pytest

from src.Embeddings import CachingEmbedder, Embedder


class CountingEmbedder(Embedder):
    """Records exactly which texts reach the real model."""

    name = 'fake:model-v1'

    def __init__(self, dim=8):
        self.dim = dim
        self.embedded = []

    def encode(self, texts):
        if isinstance(texts, str):
            self.embedded.append(texts)
            return self._vector(texts)
        self.embedded.extend(texts)
        return np.array([self._vector(t) for t in texts])

    def _vector(self, text):
        rng = np.random.default_rng(abs(hash(text)) % (2 ** 32))
        return rng.random(self.dim)


@pytest.fixture
def inner():
    return CountingEmbedder()


@pytest.fixture
def cached(inner, tmp_path):
    return CachingEmbedder(inner, cache_dir=tmp_path)


CHUNKS = ["def a(): pass", "def b(): pass", "def c(): pass"]


class TestCaching:

    def test_first_call_embeds_everything(self, cached, inner):
        vectors = cached.encode(CHUNKS)

        assert vectors.shape == (3, 8)
        assert inner.embedded == CHUNKS
        assert cached.last_misses == 3
        assert cached.last_hits == 0

    def test_second_call_embeds_nothing(self, cached, inner):
        first = cached.encode(CHUNKS)
        inner.embedded.clear()

        second = cached.encode(CHUNKS)

        assert inner.embedded == [], "cached chunks must not reach the model again"
        assert cached.last_hits == 3
        np.testing.assert_array_equal(first, second)

    def test_only_changed_chunks_are_re_embedded(self, cached, inner):
        cached.encode(CHUNKS)
        inner.embedded.clear()

        cached.encode(["def a(): pass", "def b(): CHANGED", "def c(): pass"])

        # The point of content addressing: an edit costs one embedding, not three.
        assert inner.embedded == ["def b(): CHANGED"]
        assert cached.last_hits == 2
        assert cached.last_misses == 1

    def test_duplicate_chunks_embed_once(self, cached, inner):
        vectors = cached.encode(["same", "same", "other"])

        assert inner.embedded == ["same", "other"]
        assert vectors.shape == (3, 8)
        np.testing.assert_array_equal(vectors[0], vectors[1])

    def test_vectors_align_with_input_order(self, cached):
        first = cached.encode(CHUNKS)
        reordered = cached.encode(list(reversed(CHUNKS)))

        np.testing.assert_array_equal(first[0], reordered[2])
        np.testing.assert_array_equal(first[2], reordered[0])

    def test_cache_survives_a_new_instance(self, inner, tmp_path):
        CachingEmbedder(inner, cache_dir=tmp_path).encode(CHUNKS)
        inner.embedded.clear()

        fresh = CachingEmbedder(inner, cache_dir=tmp_path)
        fresh.encode(CHUNKS)

        assert inner.embedded == [], "a restart should reuse the on-disk cache"
        assert fresh.last_hits == 3

    def test_partial_batch_growth_persists(self, inner, tmp_path):
        CachingEmbedder(inner, cache_dir=tmp_path).encode(["a", "b"])
        second = CachingEmbedder(inner, cache_dir=tmp_path)
        second.encode(["b", "c"])

        third = CachingEmbedder(inner, cache_dir=tmp_path)
        third.encode(["a", "b", "c"])

        assert third.last_hits == 3


class TestIsolationAndSafety:

    def test_models_do_not_share_a_cache(self, tmp_path):
        # Vectors from different models have different dimensions and meanings;
        # mixing them would silently corrupt retrieval.
        one = CachingEmbedder(CountingEmbedder(dim=8), cache_dir=tmp_path)
        one.encode(CHUNKS)

        other_inner = CountingEmbedder(dim=16)
        other_inner.name = 'fake:model-v2'
        other = CachingEmbedder(other_inner, cache_dir=tmp_path)
        other.encode(CHUNKS)

        assert other.last_misses == 3
        assert other.encode(CHUNKS).shape == (3, 16)

    def test_cache_directory_name_is_windows_safe(self, tmp_path):
        cached = CachingEmbedder(CountingEmbedder(), cache_dir=tmp_path)

        assert ':' not in cached.cache_dir.name
        assert cached.cache_dir.name == 'fake_model-v1'

    def test_queries_are_not_cached(self, cached, inner):
        cached.encode("a search query")
        cached.encode("a search query")

        # Queries are one-off; storing them would bloat the corpus cache.
        assert len(inner.embedded) == 2
        assert not cached.keys_path.exists()

    def test_empty_input(self, cached, inner):
        assert cached.encode([]).size == 0
        assert inner.embedded == []

    def test_corrupt_vectors_file_is_rebuilt(self, cached, inner, tmp_path):
        cached.encode(CHUNKS)
        cached.vectors_path.write_bytes(b"not a numpy file")
        inner.embedded.clear()

        recovered = CachingEmbedder(inner, cache_dir=tmp_path)
        vectors = recovered.encode(CHUNKS)

        assert vectors.shape == (3, 8)
        assert inner.embedded == CHUNKS

    def test_desynchronised_cache_is_discarded(self, cached, inner, tmp_path):
        cached.encode(CHUNKS)
        # Simulate a torn write: keys say four rows, the matrix holds three.
        payload = json.loads(cached.keys_path.read_text(encoding='utf-8'))
        payload['keys'].append('orphan')
        cached.keys_path.write_text(json.dumps(payload), encoding='utf-8')
        inner.embedded.clear()

        CachingEmbedder(inner, cache_dir=tmp_path).encode(CHUNKS)

        assert inner.embedded == CHUNKS

    def test_no_temp_files_left_behind(self, cached):
        cached.encode(CHUNKS)

        assert not list(cached.cache_dir.glob('*.tmp'))
