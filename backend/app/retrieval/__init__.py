"""Hybrid evidence retrieval and indexing package."""

from backend.app.retrieval.embedder import (
    BaseEmbeddingService,
    LocalEmbeddingService,
    MockEmbeddingService,
)
from backend.app.retrieval.faiss_index import FAISSVectorIndex
from backend.app.retrieval.fusion import FusedCandidate, ReciprocalRankFusionEngine
from backend.app.retrieval.lexical import PostgresLexicalSearchService
from backend.app.retrieval.schemas import (
    IndexBuildManifest,
    RetrievalChannel,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResultItem,
    RetrievalScopeContext,
)
from backend.app.retrieval.scope_filter import RetrievalScopeFilter, ScopeValidationError
from backend.app.retrieval.service import HybridRetrievalService

__all__ = [
    "BaseEmbeddingService",
    "FAISSVectorIndex",
    "FusedCandidate",
    "HybridRetrievalService",
    "IndexBuildManifest",
    "LocalEmbeddingService",
    "MockEmbeddingService",
    "PostgresLexicalSearchService",
    "ReciprocalRankFusionEngine",
    "RetrievalChannel",
    "RetrievalRequest",
    "RetrievalResponse",
    "RetrievalResultItem",
    "RetrievalScopeContext",
    "RetrievalScopeFilter",
    "ScopeValidationError",
]
