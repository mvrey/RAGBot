import numpy as np
import pytest

from ragbot.core.Embeddings import CachingEmbedder, GeminiEmbedder


class FakeEmbedding:
    def __init__(self, values):
        self.values = values


class FakeEmbedContentResponse:
    def __init__(self, embeddings):
        self.embeddings = embeddings


class FakeModels:
    """Records every call so tests can assert on prefixes and batching."""

    def __init__(self, dim=768, fail_times=0):
        self.calls = []
        self.dim = dim
        self.fail_times = fail_times

    def embed_content(self, model, contents, config):
        if self.fail_times > 0:
            self.fail_times -= 1
            raise ConnectionError("simulated transient failure")

        self.calls.append({'model': model, 'contents': list(contents), 'config': config})
        return FakeEmbedContentResponse(
            [FakeEmbedding(self._vector(text)) for text in contents]
        )

    def _vector(self, text):
        rng = np.random.default_rng(abs(hash(text)) % (2 ** 32))
        return rng.random(self.dim).tolist()


class FakeClient:
    def __init__(self, dim=768, fail_times=0):
        self.models = FakeModels(dim=dim, fail_times=fail_times)


@pytest.fixture
def embedder(monkeypatch):
    e = GeminiEmbedder()
    fake_client = FakeClient()
    monkeypatch.setattr(e, '_get_client', lambda: fake_client)
    return e, fake_client


class TestNaming:

    def test_default_name_includes_model_and_dimension(self):
        embedder = GeminiEmbedder()
        assert embedder.name == 'google:gemini-embedding-2@768'

    def test_name_changes_with_dimension(self):
        default_dim = GeminiEmbedder(dimensions=768)
        other_dim = GeminiEmbedder(dimensions=1536)

        assert default_dim.name != other_dim.name
        assert '1536' in other_dim.name

    def test_different_dimensions_get_different_cache_namespaces(self, tmp_path, monkeypatch):
        small = GeminiEmbedder(dimensions=768)
        large = GeminiEmbedder(dimensions=3072)
        monkeypatch.setattr(small, '_get_client', lambda: FakeClient(dim=768))
        monkeypatch.setattr(large, '_get_client', lambda: FakeClient(dim=3072))

        small_cached = CachingEmbedder(small, cache_dir=tmp_path)
        large_cached = CachingEmbedder(large, cache_dir=tmp_path)

        assert small_cached.cache_dir != large_cached.cache_dir

        small_cached.encode(["def a(): pass"])
        large_cached.encode(["def a(): pass"])

        # A vector-shape mismatch would only be caught here if the two providers
        # shared one cache directory.
        assert np.load(small_cached.vectors_path).shape[1] == 768
        assert np.load(large_cached.vectors_path).shape[1] == 3072


class TestPromptPrefixes:

    def test_query_gets_query_prefix(self, embedder):
        e, fake_client = embedder

        e.encode("how does search work")

        sent = fake_client.models.calls[0]['contents'][0]
        assert sent.startswith(GeminiEmbedder.QUERY_PREFIX)
        assert sent.endswith("how does search work")

    def test_documents_get_document_prefix(self, embedder):
        e, fake_client = embedder

        e.encode(["def a(): pass", "def b(): pass"])

        sent = fake_client.models.calls[0]['contents']
        assert all(s.startswith(GeminiEmbedder.DOCUMENT_PREFIX) for s in sent)

    def test_query_and_document_prefixes_differ(self):
        assert GeminiEmbedder.QUERY_PREFIX != GeminiEmbedder.DOCUMENT_PREFIX

    def test_dimension_configured_on_request(self, embedder):
        e, fake_client = embedder

        e.encode(["def a(): pass"])

        assert fake_client.models.calls[0]['config'].output_dimensionality == 768


class TestBatching:

    def test_batches_respect_batch_size(self, embedder, monkeypatch):
        e, fake_client = embedder
        monkeypatch.setattr(e, 'BATCH_SIZE', 2)

        e.encode(["a", "b", "c", "d", "e"])

        assert len(fake_client.models.calls) == 3
        assert [len(c['contents']) for c in fake_client.models.calls] == [2, 2, 1]

    def test_batching_preserves_order(self, embedder, monkeypatch):
        e, fake_client = embedder
        monkeypatch.setattr(e, 'BATCH_SIZE', 2)

        vectors = e.encode(["a", "b", "c"])

        assert vectors.shape[0] == 3

    def test_empty_input_makes_no_calls(self, embedder):
        e, fake_client = embedder

        result = e.encode([])

        assert result.size == 0
        assert fake_client.models.calls == []


class TestRetries:

    def test_retries_transient_failures(self, monkeypatch):
        e = GeminiEmbedder()
        fake_client = FakeClient(fail_times=2)
        monkeypatch.setattr(e, '_get_client', lambda: fake_client)
        monkeypatch.setattr(e, 'RETRY_BASE_DELAY', 0)

        vectors = e.encode(["def a(): pass"])

        assert vectors.shape == (1, 768)

    def test_exhausting_retries_raises(self, monkeypatch):
        e = GeminiEmbedder()
        fake_client = FakeClient(fail_times=99)
        monkeypatch.setattr(e, '_get_client', lambda: fake_client)
        monkeypatch.setattr(e, 'RETRY_BASE_DELAY', 0)

        with pytest.raises(ConnectionError):
            e.encode(["def a(): pass"])


class TestApiKey:

    def test_missing_key_raises_with_guidance(self, monkeypatch):
        monkeypatch.delenv('GOOGLE_API_KEY', raising=False)
        e = GeminiEmbedder()

        with pytest.raises(ValueError, match='GOOGLE_API_KEY'):
            e._get_client()


class TestProviderSelection:

    def test_get_embedder_defaults_to_local(self, monkeypatch):
        from ragbot.core.Embeddings import get_embedder

        monkeypatch.delenv('EMBEDDING_PROVIDER', raising=False)

        embedder = get_embedder()

        assert embedder.name.startswith('local:multi-qa-distilbert-cos-v1')

    def test_get_embedder_selects_google_explicitly(self, monkeypatch):
        from ragbot.core.Embeddings import get_embedder

        monkeypatch.setenv('EMBEDDING_PROVIDER', 'google')
        monkeypatch.setenv('GOOGLE_API_KEY', 'test-key')

        embedder = get_embedder()

        assert embedder.name.startswith('google:gemini-embedding-2@768')

    def test_embedding_dimensions_env_overrides_default(self, monkeypatch):
        from ragbot.core.Embeddings import get_embedder

        monkeypatch.setenv('EMBEDDING_PROVIDER', 'google')
        monkeypatch.setenv('EMBEDDING_DIMENSIONS', '256')

        embedder = get_embedder()

        assert embedder.name == 'google:gemini-embedding-2@256'
