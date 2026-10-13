import uuid
from datetime import UTC, date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class InvestigationRun(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "investigation_runs"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    denial_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("denial_events.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    initiated_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), default="QUEUED", nullable=False, index=True)
    graph_thread_id: Mapped[str] = mapped_column(String(100), nullable=False)
    retries_used: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_retries_allowed: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    terminal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_name: Mapped[str] = mapped_column(String(100), default="qwen3:8b", nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), default="v1.0", nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    retrieval_attempts: Mapped[list["RetrievalAttempt"]] = relationship("RetrievalAttempt", back_populates="run", cascade="all, delete-orphan")
    assessments: Mapped[list["EvidenceAssessment"]] = relationship("EvidenceAssessment", back_populates="run", cascade="all, delete-orphan")


class RetrievalAttempt(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "retrieval_attempts"

    investigation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    query_text: Mapped[str] = mapped_column(Text, nullable=False)
    target_sources: Mapped[list[str]] = mapped_column(ARRAY(String(50)), default=list, nullable=False)
    applied_filters: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    index_version: Mapped[str] = mapped_column(String(50), nullable=False)
    retrieval_strategy: Mapped[str] = mapped_column(String(50), default="HYBRID_RRF", nullable=False)
    chunks_returned_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Relationships
    run: Mapped["InvestigationRun"] = relationship("InvestigationRun", back_populates="retrieval_attempts")


class EvidenceChunk(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_chunks"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    source_resource_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ClinicalDocument, Observation, etc.
    source_resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="SET NULL"),
        nullable=True,
    )
    # Explicit polymorphic provenance foreign keys
    clinical_document_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("clinical_documents.id", ondelete="SET NULL"),
        nullable=True,
    )
    diagnostic_report_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("diagnostic_reports.id", ondelete="SET NULL"),
        nullable=True,
    )
    observation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("observations.id", ondelete="SET NULL"),
        nullable=True,
    )
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("conditions.id", ondelete="SET NULL"),
        nullable=True,
    )
    procedure_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("procedures.id", ondelete="SET NULL"),
        nullable=True,
    )
    fhir_resource_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("fhir_resources.id", ondelete="SET NULL"),
        nullable=True,
    )

    effective_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    chunk_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(50), default="v1.0", nullable=False)
    embedding_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("patient_id", "source_resource_id", "chunk_index", name="uq_evidence_chunk_patient_src_idx"),
    )


class EvidenceAssessment(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "evidence_assessments"

    investigation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigation_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    requirement_id: Mapped[str] = mapped_column(String(100), nullable=False)
    requirement_description: Mapped[str] = mapped_column(Text, nullable=False)
    sufficiency_status: Mapped[str] = mapped_column(String(30), nullable=False)  # SUPPORTED, PARTIALLY_SUPPORTED, MISSING, CONFLICTING
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    supporting_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    conflicting_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    run: Mapped["InvestigationRun"] = relationship("InvestigationRun", back_populates="assessments")


class GroundTruthLabel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "ground_truth_labels"

    dataset_build_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    denial_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("denial_events.id", ondelete="CASCADE"),
        nullable=False,
    )
    requirement_id: Mapped[str] = mapped_column(String(100), nullable=False)
    expected_status: Mapped[str] = mapped_column(String(30), nullable=False)
    expected_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    distractor_chunk_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), default=list, nullable=False)
    scenario_template_id: Mapped[str] = mapped_column(String(100), nullable=False)
    is_locked: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class AuditEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "audit_events"

    actor_type: Mapped[str] = mapped_column(String(20), nullable=False)  # USER, SYSTEM_WORKER, LLM_AGENT
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    correlation_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    payload_diff: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(45), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
        index=True,
    )


class DatasetBuild(Base, TimestampMixin):
    __tablename__ = "dataset_builds"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # synth_smoke_20261013_v1
    generator_version: Mapped[str] = mapped_column(String(50), nullable=False)
    seed: Mapped[int] = mapped_column(BigInteger, nullable=False)
    profile_name: Mapped[str] = mapped_column(String(50), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    patient_count: Mapped[int] = mapped_column(Integer, nullable=False)
    claim_count: Mapped[int] = mapped_column(Integer, nullable=False)
    validation_passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    validation_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)


class IndexBuild(Base, TimestampMixin):
    __tablename__ = "index_builds"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)  # idx_bge_small_v1_20261013
    dataset_build_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, default=384, nullable=False)
    chunker_version: Mapped[str] = mapped_column(String(50), nullable=False)
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False)
    faiss_index_path: Mapped[str] = mapped_column(String(500), nullable=False)
    faiss_index_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="READY", nullable=False)
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
