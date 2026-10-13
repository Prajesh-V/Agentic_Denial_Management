# Data Contracts & FHIR R4 Specifications

**Project Title:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management  
**Specification Status:** Phase 1 Design & Specification Contract (Authoritative)  
**Type System:** Pydantic v2 & HL7 FHIR Release 4 (R4)

---

## 1. Domain Entities & Pydantic v2 Schemas

All internal Python boundaries, API controllers, and database serialization logic validate against strongly typed Pydantic v2 models.

### 1.1 Identity & Multi-Tenancy

```python
from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field, EmailStr, ConfigDict

class OrganizationBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    name: str = Field(..., max_length=255)
    type: str = Field(..., description="PROVIDER_GROUP, HOSPITAL_SYSTEM, BILLING_AGENCY")
    tax_id: str = Field(..., max_length=20)
    npi: str = Field(..., max_length=10)

class PatientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    organization_id: UUID
    synthetic_mrn: str
    first_name: str
    last_name: str
    gender: str
    birth_date: date
    split_group: str
    is_synthetic: bool = True
```

### 1.2 Claims & Denial Workflow

```python
class ClaimLineItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    line_number: int
    service_code: str
    modifiers: List[str] = Field(default_factory=list)
    units: Decimal
    billed_amount: Decimal
    diagnosis_pointers: List[int]
    authorization_id: Optional[UUID] = None
    service_date: date

class DenialEventSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    claim_id: UUID
    claim_line_id: Optional[UUID] = None
    denial_category: str
    carc_code: str
    rarc_code: Optional[str] = None
    denial_reason_text: str
    denied_amount: Decimal
    denial_date: date
    appeal_deadline: date
    is_appealable: bool

class ClaimDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    claim_number: str
    patient_id: UUID
    organization_id: UUID
    status: str
    priority: str
    service_start_date: date
    service_end_date: date
    submission_date: datetime
    total_billed_amount: Decimal
    currency: str = "USD"
    lines: List[ClaimLineItem] = Field(default_factory=list)
    denial_events: List[DenialEventSummary] = Field(default_factory=list)
```

---

## 2. FHIR R4 Resource Mapping Specifications

The platform supports an explicit, fully validated subset of HL7 FHIR Release 4 resources.

### 2.1 Supported FHIR Resource Profiles

1. **`Patient`:** Basic demographics, synthetic MRN identifier, gender, and birth date.
2. **`Encounter`:** Visit classification (`inpatient`, `outpatient`, `emergency`), period start/end, service provider, and attending practitioner.
3. **`Condition`:** Clinical diagnosis, ICD-10 coding, clinical status (`active`, `resolved`), and onset date.
4. **`Procedure`:** Performed interventions, CPT/HCPCS coding, status (`completed`), and performed timestamp.
5. **`Observation`:** Lab tests and vitals with LOINC coding, effective date, quantitative numeric values with units or qualitative text findings.
6. **`MedicationRequest`:** Prescriptions, RxNorm codes, dosage instructions, and order dates.
7. **`DiagnosticReport`:** Radiology and pathology study conclusions with linked observations.
8. **`DocumentReference`:** Metadata pointer to clinical documents, document type code, and narrative attachment.

### 2.2 Concrete FHIR JSON Payloads

#### FHIR Patient Example
```json
{
  "resourceType": "Patient",
  "id": "pat-01hm9a781b2c3d4e5f6a",
  "identifier": [
    {
      "system": "http://hospital.synthetic.local/mrn",
      "value": "MRN-SYNTH-984210"
    }
  ],
  "name": [
    {
      "use": "official",
      "family": "Miller",
      "given": ["Eleanor", "Jane"]
    }
  ],
  "gender": "female",
  "birthDate": "1964-08-22"
}
```

#### FHIR Encounter Example
```json
{
  "resourceType": "Encounter",
  "id": "enc-01hm9b122c3d4e5f6a7b",
  "status": "finished",
  "class": {
    "system": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "code": "AMB",
    "display": "ambulatory"
  },
  "subject": {
    "reference": "Patient/pat-01hm9a781b2c3d4e5f6a"
  },
  "period": {
    "start": "2025-11-04T09:30:00Z",
    "end": "2025-11-04T11:15:00Z"
  }
}
```

#### FHIR Condition Example
```json
{
  "resourceType": "Condition",
  "id": "cond-01hm9c344d5e6f7a8b9c",
  "clinicalStatus": {
    "coding": [
      {
        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
        "code": "active"
      }
    ]
  },
  "code": {
    "coding": [
      {
        "system": "http://hl7.org/fhir/sid/icd-10-cm",
        "code": "M17.11",
        "display": "Unilateral primary osteoarthritis, right knee"
      }
    ]
  },
  "subject": {
    "reference": "Patient/pat-01hm9a781b2c3d4e5f6a"
  },
  "encounter": {
    "reference": "Encounter/enc-01hm9b122c3d4e5f6a7b"
  },
  "onsetDateTime": "2025-05-12T00:00:00Z"
}
```

---

## 3. EvidenceChunk Contract

An `EvidenceChunk` is the atomic unit of retrieval and citation grounding.

```python
class EvidenceChunkModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID = Field(..., description="Stable chunk identifier")
    patient_id: UUID = Field(..., description="Mandatory patient scope")
    source_resource_type: str = Field(..., description="ClinicalDocument, Observation, DiagnosticReport")
    source_resource_id: UUID = Field(..., description="Foreign key to source table")
    fhir_resource_id: Optional[str] = None
    encounter_id: Optional[UUID] = None
    effective_date: Optional[date] = None
    chunk_index: int = 0
    content: str = Field(..., description="Exact textual excerpt")
    token_count: int
    char_count: int
    text_hash: str = Field(..., description="SHA-256 hash of content")
    chunker_version: str
    embedding_id: Optional[int] = None
    is_active: bool = True
    created_at: datetime
```

---

## 4. GroundTruthLabel Contract

Locked benchmark evaluation records used for quantitative RAG and agent testing.

```python
class GroundTruthLabelModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    dataset_build_id: str
    claim_id: UUID
    denial_event_id: UUID
    requirement_id: str
    expected_status: str = Field(..., description="SUPPORTED, PARTIALLY_SUPPORTED, MISSING, CONFLICTING")
    expected_chunk_ids: List[UUID] = Field(default_factory=list)
    distractor_chunk_ids: List[UUID] = Field(default_factory=list)
    scenario_template_id: str
    is_locked: bool = True
```

---

## 5. AuditEvent Contract

Immutable security and operational event trail.

```python
class AuditEventModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    actor_type: str = Field(..., description="USER, SYSTEM_WORKER, LLM_AGENT")
    actor_user_id: Optional[UUID] = None
    organization_id: UUID
    correlation_id: str
    action: str = Field(..., description="CLAIM_ASSIGNED, INVESTIGATION_STARTED, DRAFT_APPROVED, APPEAL_EXPORTED")
    entity_type: str = Field(..., description="Claim, InvestigationRun, AppealDraftVersion, Export")
    entity_id: UUID
    payload_diff: Optional[dict] = None
    ip_address: Optional[str] = None
    occurred_at: datetime
```
