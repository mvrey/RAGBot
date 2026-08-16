"""Embedding providers.

Local sentence-transformers is the default so the app runs with no API spend.
Setting EMBEDDING_PROVIDER=openai in .env swaps in text-embedding-3-small, which
retrieves noticeably better on source code - see the README for the trade-off.
"""

import os

import numpy as np
from dotenv import load_dotenv

load_dotenv()

DEFAULT_LOCAL_MODEL = 'multi-qa-distilbert-cos-v1'
DEFAULT_OPENAI_MODEL = 'text-embedding-3-small'

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


def get_embedder() -> Embedder:
    """Build the embedder selected by EMBEDDING_PROVIDER / EMBEDDING_MODEL."""
    provider = os.getenv('EMBEDDING_PROVIDER', 'local').strip().lower()
    model = os.getenv('EMBEDDING_MODEL', '').strip()

    if provider == 'openai':
        return OpenAIEmbedder(model or DEFAULT_OPENAI_MODEL)
    if provider == 'local':
        return LocalEmbedder(model or DEFAULT_LOCAL_MODEL)

    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER '{provider}'. Expected 'local' or 'openai'."
    )
