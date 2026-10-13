import uuid
from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EvidentiaryRole(str, Enum):
    CLINICAL_SUPPORTING = "CLINICAL_SUPPORTING"
    PAYER_POLICY = "PAYER_POLICY"
    DENIAL_CONTEXT = "DENIAL_CONTEXT"
    ADMINISTRATIVE = "ADMINISTRATIVE"


class CanonicalSourceType(str, Enum):
    CLINICAL_DOCUMENT = "ClinicalDocument"
    DIAGNOSTIC_REPORT = "DiagnosticReport"
    OBSERVATION = "Observation"
    CONDITION = "Condition"
    PROCEDURE = "Procedure"
    MEDICATION_REQUEST = "MedicationRequest"
    FHIR_RESOURCE = "FhirResource"
    ENCOUNTER = "Encounter"
    PAYER_POLICY_VERSION = "PayerPolicyVersion"
    DENIAL_EVENT = "DenialEvent"


class DocumentSection(BaseModel):
    title: str = Field(..., description="Section title or classification")
    content: str = Field(..., description="Section text content")
    start_char: int = Field(0, description="Start character offset in normalized document")
    end_char: int = Field(0, description="End character offset in normalized document")


class CanonicalDocument(BaseModel):
    source_id: uuid.UUID = Field(..., description="Canonical database primary key of source record")
    source_type: CanonicalSourceType = Field(..., description="Entity type of the canonical source")
    evidentiary_role: EvidentiaryRole = Field(..., description="Evidentiary role for retrieval and investigation")
    
    # Isolation scopes
    patient_id: uuid.UUID | None = Field(None, description="Patient UUID (None for payer-scoped shared documents)")
    encounter_id: uuid.UUID | None = Field(None, description="Encounter UUID if applicable")
    payer_id: uuid.UUID | None = Field(None, description="Payer UUID for policy documents")
    payer_policy_version_id: uuid.UUID | None = Field(None, description="PayerPolicyVersion UUID for policy documents")
    claim_id: uuid.UUID | None = Field(None, description="Claim UUID for denial context")
    denial_event_id: uuid.UUID | None = Field(None, description="DenialEvent UUID for denial context")
    dataset_build_id: str | None = Field(None, description="Dataset build identifier if scoped to a build")
    
    effective_date: date | None = Field(None, description="Clinical or policy effective date")
    raw_content: str = Field(..., description="Original extracted content from canonical record")
    normalized_content: str = Field(..., description="Deterministically normalized text")
    content_hash: str = Field(..., description="SHA-256 hash of normalized content")
    
    sections: list[DocumentSection] = Field(default_factory=list, description="Extracted document sections")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Structured provenance metadata")
    is_synthetic: bool = Field(True, description="Explicit synthetic data designation")


class ChunkPayload(BaseModel):
    source_id: uuid.UUID
    source_type: CanonicalSourceType
    evidentiary_role: EvidentiaryRole
    
    patient_id: uuid.UUID | None = None
    encounter_id: uuid.UUID | None = None
    payer_id: uuid.UUID | None = None
    payer_policy_version_id: uuid.UUID | None = None
    claim_id: uuid.UUID | None = None
    denial_event_id: uuid.UUID | None = None
    dataset_build_id: str | None = None
    
    section_name: str | None = None
    chunk_index: int = 0
    content: str
    token_count: int
    char_count: int
    text_hash: str
    chunker_version: str = "v1.0"
    source_text_offset: int | None = None
    source_text_length: int | None = None
    effective_date: date | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IngestionManifest(BaseModel):
    run_id: str
    dataset_build_id: str
    processor_version: str = "processor_v1_20261013"
    chunker_version: str = "v1.0"
    started_at: datetime
    completed_at: datetime | None = None
    duration_seconds: float = 0.0
    
    sources_discovered: int = 0
    sources_processed: int = 0
    sources_skipped: int = 0
    
    chunks_generated: int = 0
    chunks_persisted: int = 0
    chunks_skipped_duplicate: int = 0
    chunks_superseded: int = 0
    
    by_source_type: dict[str, int] = Field(default_factory=dict)
    by_evidentiary_role: dict[str, int] = Field(default_factory=dict)
    rejection_reasons: dict[str, int] = Field(default_factory=dict)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    validation_passed: bool = False
