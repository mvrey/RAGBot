"""Embedding providers.

Gemini (google-genai) is the default: no torch in the dependency tree, and it
retrieves noticeably better on source code than the local model. Setting
EMBEDDING_PROVIDER=local swaps in sentence-transformers for a fully offline,
no-API-key setup; EMBEDDING_PROVIDER=openai swaps in text-embedding-3-small.
See the README for the trade-off.
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

from ragbot.core.settings import EMBEDDING_CACHE_DIR

load_dotenv()

DEFAULT_LOCAL_MODEL = 'multi-qa-distilbert-cos-v1'
DEFAULT_OPENAI_MODEL = 'text-embedding-3-small'
DEFAULT_GOOGLE_MODEL = 'gemini-embedding-2'
DEFAULT_GOOGLE_DIMENSIONS = 768

# Derived artefacts live outside data/repos/, which is a faithful mirror of the
# repository - Repository.load_cached_repo_files() and the agent's list_files tool
# both walk that tree, and would otherwise pick up cache files as source.

# text-embedding-3-small accepts 8191 tokens per input. Rather than pull in a
# tokenizer just for this, truncate on characters with a conservative ~4 chars
# per token estimate.
OPENAI_MAX_INPUT_CHARS = 8000 * 4
OPENAI_BATCH_SIZE = 100


class Embedder:
    """Interface for turning text into vectors."""

    name = 'embedder'

    def encode(self, texts) -> np.ndarray:
        raise NotImplementedError


class LocalEmbedder(Embedder):
    """sentence-transformers, run locally. Free, offline, no API key."""

    def __init__(self, model_name: str = DEFAULT_LOCAL_MODEL):
        self.model_name = model_name
        self.name = f'local:{model_name}'
        self._model = None

    def _get_model(self):
        # Imported lazily: loading torch is slow and pointless when the OpenAI
        # provider is selected.
        if self._model is None:
            from sentence_transformers import SentenceTransformer
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts) -> np.ndarray:
        single = isinstance(texts, str)
        batch = [texts] if single else list(texts)
        if not batch:
            return np.empty((0, 0))

        vectors = self._get_model().encode(batch, show_progress_bar=not single)
        vectors = np.asarray(vectors)
        return vectors[0] if single else vectors


class OpenAIEmbedder(Embedder):
    """OpenAI embeddings. Better on code, costs per token, needs network."""

    def __init__(self, model_name: str = DEFAULT_OPENAI_MODEL):
        self.model_name = model_name
        self.name = f'openai:{model_name}'
        self._client = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            api_key = os.getenv('OPENAI_API_KEY')
            if not api_key:
                raise ValueError(
                    "OPENAI_API_KEY is not set. Set it in .env, or use "
                    "EMBEDDING_PROVIDER=local to run without an API key."
                )
            self._client = OpenAI(api_key=api_key)
        return self._client

    def encode(self, texts) -> np.ndarray:
        single = isinstance(texts, str)
        batch = [texts] if single else list(texts)
        if not batch:
            return np.empty((0, 0))

        # The API rejects empty strings, so keep a placeholder for blank inputs.
        prepared = [(t or ' ')[:OPENAI_MAX_INPUT_CHARS] for t in batch]

        client = self._get_client()
        vectors = []
        for start in range(0, len(prepared), OPENAI_BATCH_SIZE):
            window = prepared[start:start + OPENAI_BATCH_SIZE]
            response = client.embeddings.create(model=self.model_name, input=window)
            vectors.extend(item.embedding for item in response.data)

        result = np.array(vectors)
        return result[0] if single else result


class GeminiEmbedder(Embedder):
    """Gemini embeddings via google-genai. No torch, good on code, needs network.

    gemini-embedding-2 does not support the `task_type` config field that older
    Gemini embedding models used for asymmetric retrieval (query vs document).
    The replacement is a plain text prefix on the input itself, which maps cleanly
    onto the encode() contract already in use here: a bare str is a query, a list
    is corpus documents.
    """

    QUERY_PREFIX = 'task: search result | query: '
    DOCUMENT_PREFIX = 'task: search result | document: '

    # gemini-embedding-2 accepts 8192 tokens per input. As with OpenAIEmbedder,
    # truncate on characters (~4 chars/token) rather than pull in a tokenizer.
    MAX_INPUT_CHARS = 8000 * 4
    BATCH_SIZE = 100
    MAX_RETRIES = 3
    RETRY_BASE_DELAY = 1.0

    def __init__(self, model_name: str = DEFAULT_GOOGLE_MODEL, dimensions: int = DEFAULT_GOOGLE_DIMENSIONS):
        self.model_name = model_name
        self.dimensions = dimensions
        # The cache namespaces by name, so the dimension must be part of it -
        # otherwise vectors of two different shapes could land in one store.
        self.name = f'google:{model_name}@{dimensions}'
        self._client = None

    def _get_client(self):
        if self._client is None:
            from google import genai
            api_key = os.getenv('GOOGLE_API_KEY')
            if not api_key:
                raise ValueError(
                    "GOOGLE_API_KEY is not set. Set it in .env, or use "
                    "EMBEDDING_PROVIDER=local to run without an API key."
                )
            self._client = genai.Client(api_key=api_key)
        return self._client

    def _embed_batch(self, prepared_window):
        from google.genai import types

        client = self._get_client()
        config = types.EmbedContentConfig(output_dimensionality=self.dimensions)

        last_error = None
        for attempt in range(self.MAX_RETRIES):
            try:
                response = client.models.embed_content(
                    model=self.model_name, contents=prepared_window, config=config,
                )
                return [embedding.values for embedding in response.embeddings]
            except Exception as e:
                last_error = e
                if attempt < self.MAX_RETRIES - 1:
                    time.sleep(self.RETRY_BASE_DELAY * (2 ** attempt))
        raise last_error

    def encode(self, texts) -> np.ndarray:
        single = isinstance(texts, str)
        batch = [texts] if single else list(texts)
        if not batch:
            return np.empty((0, 0))

        prefix = self.QUERY_PREFIX if single else self.DOCUMENT_PREFIX
        # The API rejects empty strings, so keep a placeholder for blank inputs.
        prepared = [prefix + (t or ' ')[:self.MAX_INPUT_CHARS] for t in batch]

        vectors = []
        for start in range(0, len(prepared), self.BATCH_SIZE):
            window = prepared[start:start + self.BATCH_SIZE]
            vectors.extend(self._embed_batch(window))

        result = np.array(vectors)
        return result[0] if single else result


class CachingEmbedder(Embedder):
    """Persists corpus vectors to disk so re-indexing skips the expensive step.

    Embedding dominates indexing cost (~67ms/chunk locally, so minutes for a large
    repo), while search over the result takes milliseconds. Caching the vectors
    therefore removes essentially all of the repeatable work, and a flat .npy file
    is enough - a vector database would optimise the part that was never slow.

    Vectors are content-addressed by a hash of the chunk text, which means the
    cache invalidates itself: change a file and only its chunks are re-embedded,
    while identical chunks (licence headers, boilerplate) are stored once.
    """

    def __init__(self, inner: Embedder, cache_dir: Path = EMBEDDING_CACHE_DIR):
        self.inner = inner
        # Keep the inner name so the UI still reports the real model.
        self.name = inner.name
        # A colon is legal in the provider name but not in a Windows path.
        self.cache_dir = Path(cache_dir) / re.sub(r'[^A-Za-z0-9._-]+', '_', inner.name)
        self.last_hits = 0
        self.last_misses = 0
        self._keys = None
        self._index = None
        self._vectors = None

    @property
    def vectors_path(self) -> Path:
        return self.cache_dir / 'vectors.npy'

    @property
    def keys_path(self) -> Path:
        return self.cache_dir / 'keys.json'

    @staticmethod
    def _hash(text: str) -> str:
        return hashlib.sha256((text or '').encode('utf-8')).hexdigest()

    def _load(self):
        if self._keys is not None:
            return

        self._keys, self._vectors = [], None
        if self.vectors_path.exists() and self.keys_path.exists():
            try:
                keys = json.loads(self.keys_path.read_text(encoding='utf-8'))['keys']
                vectors = np.load(self.vectors_path, allow_pickle=False)
                # A truncated write would desynchronise the two files; rebuilding is
                # cheaper than reasoning about a half-valid cache.
                if len(keys) == len(vectors):
                    self._keys, self._vectors = list(keys), vectors
            except Exception:
                pass

        self._index = {key: row for row, key in enumerate(self._keys)}

    def _save(self):
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Write to a temporary file and rename: os.replace is atomic, so a crash
        # or a second Streamlit session cannot leave a torn cache behind.
        tmp_vectors = self.vectors_path.with_name('vectors.npy.tmp')
        with open(tmp_vectors, 'wb') as f_out:
            # Pass a file object - np.save would otherwise append .npy to the name.
            np.save(f_out, self._vectors, allow_pickle=False)
        os.replace(tmp_vectors, self.vectors_path)

        tmp_keys = self.keys_path.with_name('keys.json.tmp')
        payload = {'model': self.inner.name, 'keys': self._keys}
        tmp_keys.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(tmp_keys, self.keys_path)

    def _append(self, keys, vectors):
        if self._vectors is None or len(self._vectors) == 0:
            self._vectors = vectors
        else:
            self._vectors = np.vstack([self._vectors, vectors])

        for key in keys:
            self._index[key] = len(self._keys)
            self._keys.append(key)

    def encode(self, texts) -> np.ndarray:
        # A bare string is a search query: one-off and unique, so caching it would
        # only bloat the corpus store.
        if isinstance(texts, str):
            return self.inner.encode(texts)

        batch = list(texts)
        if not batch:
            return np.empty((0, 0))

        self._load()
        hashes = [self._hash(text) for text in batch]

        # dict.fromkeys keeps first-seen order while dropping duplicates, so a chunk
        # repeated within one batch is embedded once.
        missing = [h for h in dict.fromkeys(hashes) if h not in self._index]
        missing_set = set(missing)
        self.last_misses = sum(1 for h in hashes if h in missing_set)
        self.last_hits = len(batch) - self.last_misses

        if missing:
            first_text = {}
            for key, text in zip(hashes, batch):
                first_text.setdefault(key, text)

            new_vectors = np.asarray(self.inner.encode([first_text[h] for h in missing]))
            self._append(missing, new_vectors)
            self._save()

        return np.array([self._vectors[self._index[h]] for h in hashes])


def get_embedder() -> Embedder:
    """Build the embedder selected by EMBEDDING_PROVIDER / EMBEDDING_MODEL."""
    provider = os.getenv('EMBEDDING_PROVIDER', 'google').strip().lower()
    model = os.getenv('EMBEDDING_MODEL', '').strip()

    if provider == 'google':
        dimensions_raw = os.getenv('EMBEDDING_DIMENSIONS', '').strip()
        dimensions = int(dimensions_raw) if dimensions_raw else DEFAULT_GOOGLE_DIMENSIONS
        embedder = GeminiEmbedder(model or DEFAULT_GOOGLE_MODEL, dimensions=dimensions)
    elif provider == 'openai':
        embedder = OpenAIEmbedder(model or DEFAULT_OPENAI_MODEL)
    elif provider == 'local':
        embedder = LocalEmbedder(model or DEFAULT_LOCAL_MODEL)
    else:
        raise ValueError(
            f"Unknown EMBEDDING_PROVIDER '{provider}'. Expected 'google', 'local', or 'openai'."
        )

    if os.getenv('EMBEDDING_CACHE', '1').strip().lower() in ('0', 'false', 'no'):
        return embedder
    return CachingEmbedder(embedder)
