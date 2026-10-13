"""Pydantic request, response, and manifest schemas for the hybrid retrieval engine."""

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.app.ingestion.schemas import EvidentiaryRole


class RetrievalChannel(str, Enum):
    """Retrieval channel selector."""
    SEMANTIC = "semantic"
    LEXICAL = "lexical"
    HYBRID = "hybrid"


class RetrievalScopeContext(BaseModel):
    """Authoritative scope boundary for evidence access control."""
    model_config = ConfigDict(frozen=True)

    claim_id: UUID = Field(..., description="Target claim being investigated")
    patient_id: UUID = Field(..., description="Authorized patient ID for the investigation")
    tenant_id: UUID | None = Field(default=None, description="Optional organization/tenant ID")
    payer_id: UUID | None = Field(default=None, description="Payer ID associated with the claim")
    service_date: date | datetime | None = Field(default=None, description="Service date of the claim for policy temporal validity")
    allowed_roles: list[EvidentiaryRole] | None = Field(
        default=None,
        description="Optional filter for allowed evidentiary roles (CLINICAL_SUPPORTING, PAYER_POLICY, DENIAL_CONTEXT)",
    )


class RetrievalRequest(BaseModel):
    """User/investigation retrieval request specification."""
    query: str = Field(..., min_length=1, description="Natural language search query or clinical/policy keywords")
    claim_id: UUID = Field(..., description="Target claim being investigated")
    patient_id: UUID = Field(..., description="Authorized patient ID for the investigation")
    tenant_id: UUID | None = Field(default=None, description="Optional organization/tenant ID")
    payer_id: UUID | None = Field(default=None, description="Optional payer ID (if not provided, looked up from claim)")
    service_date: date | datetime | None = Field(default=None, description="Claim service date for policy effective date check")
    allowed_roles: list[EvidentiaryRole] | None = Field(default=None, description="Permitted evidentiary roles")
    limit: int = Field(default=10, ge=1, le=100, description="Requested maximum result count")
    min_score: float | None = Field(default=None, ge=0.0, description="Optional minimum fused score threshold")
    channel: RetrievalChannel = Field(default=RetrievalChannel.HYBRID, description="Retrieval channel to use")
    rrf_k: int = Field(default=60, ge=1, le=500, description="Reciprocal Rank Fusion constant k (default: 60)")


class RetrievalResultItem(BaseModel):
    """Standardized, provenance-preserving evidence chunk retrieval result."""
    chunk_id: UUID
    source_resource_type: str
    source_resource_id: UUID
    evidentiary_role: EvidentiaryRole
    chunker_version: str
    chunk_index: int
    content: str
    section_name: str | None = None
    source_text_offset: int | None = None
    source_text_length: int | None = None
    text_hash: str

    # Scope and attribution identifiers
    patient_id: UUID | None = None
    payer_id: UUID | None = None
    payer_policy_version_id: UUID | None = None
    claim_id: UUID | None = None
    denial_event_id: UUID | None = None
    effective_date: datetime | date | None = None

    # Ranking metrics
    semantic_rank: int | None = Field(default=None, description="1-based rank in semantic channel")
    semantic_score: float | None = Field(default=None, description="Cosine similarity score [-1.0, 1.0]")
    lexical_rank: int | None = Field(default=None, description="1-based rank in PostgreSQL lexical channel")
    lexical_score: float | None = Field(default=None, description="PostgreSQL ts_rank score")
    fused_rank: int = Field(..., description="1-based rank after Reciprocal Rank Fusion")
    fused_score: float = Field(..., description="Reciprocal Rank Fusion (RRF) score")

    # Transparency and provenance
    explanation: str = Field(..., description="Deterministic explanation of retrieval and ranking")
    provenance: dict[str, Any] = Field(default_factory=dict, description="Relational provenance metadata")


class RetrievalResponse(BaseModel):
    """Response containing retrieved evidence chunks with provenance and ranking metadata."""
    query: str
    claim_id: UUID
    patient_id: UUID
    channel: RetrievalChannel
    total_candidates: int
    results: list[RetrievalResultItem]
    retrieval_metadata: dict[str, Any] = Field(default_factory=dict)


class IndexBuildManifest(BaseModel):
    """Manifest tracking vector index build provenance, dimensions, and active chunk mapping."""
    index_id: str
    dataset_build_id: str
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    embedding_dimension: int = 384
    metric: str = "INNER_PRODUCT"
    normalized: bool = True
    chunker_version: str = "v1.0"
    chunk_count: int
    chunk_ids: list[str] = Field(..., description="Ordered list of canonical EvidenceChunk UUIDs in FAISS index")
    corpus_fingerprint: str = Field(..., description="SHA-256 fingerprint of corpus chunk hashes")
    faiss_index_hash: str = Field(..., description="SHA-256 hash of the generated .faiss file")
    status: str = "READY"
    created_at: str
