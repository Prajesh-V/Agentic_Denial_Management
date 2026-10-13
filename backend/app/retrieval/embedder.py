"""Local embedding service wrapping BAAI/bge-small-en-v1.5 and mock embedder for tests."""

import hashlib
from abc import ABC, abstractmethod

import numpy as np


class BaseEmbeddingService(ABC):
    """Abstract interface for evidence embedding generation."""

    @abstractmethod
    def encode_texts(self, texts: list[str]) -> np.ndarray:
        """Encode a batch of evidence chunk texts into normalized embedding vectors."""

    @abstractmethod
    def encode_query(self, query: str) -> np.ndarray:
        """Encode a search query string into a normalized embedding vector."""

    @property
    @abstractmethod
    def dimension(self) -> int:
        """Vector dimension."""


class LocalEmbeddingService(BaseEmbeddingService):
    """Production embedding service using local BAAI/bge-small-en-v1.5."""

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-en-v1.5",
        query_instruction: str = "Represent this sentence for searching relevant passages: ",
        batch_size: int = 32,
    ) -> None:
        self.model_name = model_name
        self.query_instruction = query_instruction
        self.batch_size = batch_size
        self._model = None
        self._dim = 384

    def _load_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(self.model_name)
                # Verify dimension
                if hasattr(self._model, "get_embedding_dimension"):
                    self._dim = self._model.get_embedding_dimension()
                elif hasattr(self._model, "get_sentence_embedding_dimension"):
                    self._dim = self._model.get_sentence_embedding_dimension()
                if self._dim != 384:
                    raise ValueError(f"Unexpected embedding dimension: expected 384, got {self._dim}")
            except Exception as e:
                raise RuntimeError(
                    f"Failed to initialize embedding model '{self.model_name}': {e}. "
                    "Ensure sentence-transformers and local weights are available."
                ) from e
        return self._model

    @property
    def dimension(self) -> int:
        return self._dim

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dim), dtype=np.float32)

        for i, t in enumerate(texts):
            if not t or not t.strip():
                raise ValueError(f"Empty or whitespace-only text at index {i} cannot be embedded.")

        model = self._load_model()
        vectors = model.encode(
            texts,
            batch_size=self.batch_size,
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        vectors = np.array(vectors, dtype=np.float32)

        # Validate finiteness and normalization
        if not np.isfinite(vectors).all():
            raise ValueError("Non-finite values (NaN or Inf) detected in generated embeddings.")

        return vectors

    def encode_query(self, query: str) -> np.ndarray:
        if not query or not query.strip():
            raise ValueError("Query string cannot be empty or whitespace-only.")

        model = self._load_model()
        full_query = f"{self.query_instruction}{query}" if self.query_instruction else query
        vector = model.encode(
            [full_query],
            show_progress_bar=False,
            normalize_embeddings=True,
        )
        vector = np.array(vector, dtype=np.float32)

        if not np.isfinite(vector).all():
            raise ValueError("Non-finite values detected in query embedding vector.")

        return vector


class MockEmbeddingService(BaseEmbeddingService):
    """Deterministic hash-seeded embedding generator for fast, isolated unit testing."""

    def __init__(self, dimension: int = 384) -> None:
        self._dim = dimension

    @property
    def dimension(self) -> int:
        return self._dim

    def _hash_to_unit_vector(self, text: str) -> np.ndarray:
        seed = int(hashlib.sha256(text.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        vec = rng.standard_normal(self._dim).astype(np.float32)
        norm = np.linalg.norm(vec)
        if norm == 0:
            vec[0] = 1.0
            return vec
        return vec / norm

    def encode_texts(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, self._dim), dtype=np.float32)
        for i, t in enumerate(texts):
            if not t or not t.strip():
                raise ValueError(f"Empty text at index {i} cannot be embedded.")
        return np.stack([self._hash_to_unit_vector(t) for t in texts])

    def encode_query(self, query: str) -> np.ndarray:
        if not query or not query.strip():
            raise ValueError("Query string cannot be empty.")
        return np.expand_dims(self._hash_to_unit_vector(f"query:{query}"), axis=0)
