# Architecture & Schema Decisions (ADR)

**Project Title:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management  
**Specification Status:** Phase 1 Design & Specification Contract (Authoritative)  
**System of Record:** PostgreSQL 18

---

## 1. Architectural Role of PostgreSQL as Canonical Source of Truth

### Decision
PostgreSQL 18 is the sole, authoritative, durable system of record for all business entities, clinical facts, insurance claims, denial events, agent investigations, draft histories, human decisions, and audit events.

### Rationale
Healthcare revenue cycle systems demand ACID transaction guarantees, strict foreign key constraints, temporal coherence validation, and auditability. LangGraph workflow checkpoints, FAISS vector indexes, or in-memory caches must never hold the sole copy of any user-facing state, clinical record, or appeal draft. If a container restarts, or a vector index becomes corrupted, the system can deterministically reconstruct all derived state directly from PostgreSQL.

---

## 2. Durable vs. Derived State Architecture

| Classification | Entities & Artifacts | Storage Medium | Lifecycle & Invariants |
|---|---|---|---|
| **Durable / Canonical** | Organizations, Patients, Encounters, Conditions, Procedures, Observations, Clinical Documents, Claims, Denials, Draft Versions, Decisions, Audits | PostgreSQL Relational Tables & JSONB | Primary source of truth. Backed up, versioned, strictly immutable or audited on change. |
| **Derived / Rebuildable** | Evidence Chunks, Vector Embeddings, FAISS Index Binary, Full-Text Search TSVectors, Summary Metrics | Derived Tables & Local FAISS Index Files | Derived strictly from canonical rows. Rebuildable deterministically via CLI or Data Lab. |

### Index Build Invariant
Every vector index build must log:
- Canonical dataset build ID
- Embedding model identifier and version (`BAAI/bge-small-en-v1.5`)
- Chunker algorithm version and chunking parameters (chunk size, overlap)
- Row counts, file SHA-256 hashes, and creation timestamp
If an active index build hash does not align with the dataset build ID, the system transitions to a visible `DEGRADED_INDEX` state and prompts for an index rebuild rather than silently returning empty search results.

---

## 3. Dual FHIR Storage Strategy: Normalized Tables + JSONB Payloads

### Decision
The system employs a dual-storage strategy:
1. **Normalized Relational Tables:** `encounters`, `conditions`, `procedures`, `observations`, `medication_requests`, `diagnostic_reports`.
2. **Standard FHIR JSONB Table:** `fhir_resources` storing full HL7 FHIR R4 JSON payloads.

### Rationale
- **Fast Relational Queries:** The application UI (Claims Queue, Investigation Workspace, Patient Chronology) requires fast, index-accelerated relational filtering, sorting, pagination, and multi-table joins (e.g., finding all encounters for a patient between specific dates).
- **Interoperability & Exact Provenance:** Real-world health IT systems interact with EHRs via standard FHIR APIs. Storing canonical FHIR R4 JSON payloads provides standards compliance, simplifies export to external healthcare systems, and preserves exact nested resource structures without lossy ORM transformations.
- **Single Source of Truth:** Both normalized rows and FHIR JSONB records are produced simultaneously by the synthetic data factory mapping module. Neither is created independently, eliminating data drift.

---

## 4. Multi-Tenancy & Patient Isolation Architecture

### Decision
Multi-tenancy and patient scoping are enforced strictly at the database query level in backend Python services, never delegated to client-side parameters or LLM prompt instructions.

### Rationale & Rules
- **Organization Tenant Boundaries:** Every provider entity (`facilities`, `practitioners`, `claims`, `patients`, `audit_events`) contains an `organization_id` foreign key. All database queries from FastAPI handlers filter by the authenticated user's active tenant membership.
- **Strict Patient Scoping:** Every clinical record and `evidence_chunks` row contains a non-nullable `patient_id`.
- **Pre-Retrieval Filtering:** When the LangGraph agent retrieves evidence, the retrieval tool injects `WHERE patient_id = :active_claim_patient_id` directly into the SQL query or FAISS ID filter *before* ranking or cosine similarity calculation.
- **LLM Prompt Boundary Prohibition:** The LLM prompt is never treated as a security boundary. An LLM cannot be asked to "please ignore records from other patients." Unscoped evidence never enters the LLM's prompt context.

---

## 5. Monetary Representation: Exact Decimals

### Decision
All financial quantities (`total_billed_amount`, `billed_amount`, `allowed_amount`, `paid_amount`, `adjustment_amount`, `denied_amount`) are stored using PostgreSQL `NUMERIC(12, 2)` (mapped to Python `decimal.Decimal`). Floating-point types (`FLOAT`, `REAL`, `DOUBLE PRECISION`) are strictly forbidden.

### Rationale
Healthcare billing claims and electronic remittances (835) enforce exact accounting balance:
$$	ext{Billed Amount} = 	ext{Allowed Amount} + 	ext{Contractual Adjustments} = 	ext{Paid Amount} + 	ext{Patient Responsibility} + 	ext{Adjustment}$$
Binary floating-point arithmetic introduces rounding inaccuracies (e.g., $0.1 + 0.2 
eq 0.3$) which compromise audit integrity and cause validation checks to fail.

---

## 6. Temporal Coherence & Chronological Validation

### Decision
Database schemas enforce chronological sanity via PostgreSQL `CHECK` constraints, and the synthetic data factory verifies timeline consistency prior to database commit.

### Temporal Invariants
1. **Encounter Chronology:** `encounters.end_time >= encounters.start_time`.
2. **Clinical Onset:** `conditions.onset_time` must be within or prior to the associated encounter window.
3. **Service & Claim Dates:** Service start date $\le$ Service end date $\le$ Claim submission date.
4. **Adjudication & Denial:** Claim submission date $\le$ Remittance adjudication date $\le$ Denial event date.
5. **Appeal & Deadlines:** Denial event date $\le$ Appeal creation date $\le$ Appeal decision date $\le$ Export date.
6. **Timely Filing Constraints:** Appeal creation date $\le$ Denial event appeal deadline.

---

## 7. Draft Immutability & Audit Integrity

### Decision
`appeal_draft_versions` and `audit_events` are strictly append-only. Updates (`UPDATE`) and deletions (`DELETE`) on these tables are blocked at the application service level.

### Rationale
When an analyst edits an appeal draft, the system does not overwrite the existing draft; it writes a new record with `version_number = N + 1`. This preserves the exact draft snapshot that the AI generated, enables side-by-side visual diffing, and ensures that supervisory approvals link to an immutable SHA-256 hash of the approved text.

---

## 8. Database Migrations & Versioning Strategy

### Decision
All PostgreSQL schema changes must be authored as version-controlled Alembic migrations under `backend/alembic/versions/`.

### Migration Rules
- Zero manual DDL execution (`CREATE TABLE`, `ALTER TABLE`) directly against the database.
- Every migration must provide both a robust `upgrade()` and a clean `downgrade()` function.
- Test suites must execute migration rollback and upgrade cycles against a fresh database container to verify reproducibility.

---

## 9. Phase 2 Architectural & Consistency Reconciliations

Prior to SQLAlchemy model and Alembic migration implementation, the following 7 consistency issues were audited and resolved:

### 9.1 Authoritative Table Inventory Reconciliation (40 Tables)
The initial Phase 1 summary referenced 32 tables as an informal grouping. The exhaustive, authoritative table inventory consists of **40 relational tables** across four core domains:
1. **Identity, Organization & Access (8):** `organizations`, `facilities`, `practitioners`, `users`, `roles`, `user_roles`, `organization_memberships`, `patients`.
2. **Clinical Records & FHIR (8):** `encounters`, `conditions`, `procedures`, `observations`, `medication_requests`, `diagnostic_reports`, `clinical_documents`, `fhir_resources`.
3. **Insurance, Claims & Denials (16):** `payers`, `payer_plans`, `coverage`, `service_codes`, `authorizations`, `claims`, `claim_diagnoses`, `claim_lines`, `remittances`, `remittance_lines`, `denial_events`, `payer_policy_versions`, `appeals`, `appeal_draft_versions`, `appeal_decisions`, `exports`.
4. **Investigation, Retrieval, Evaluation & Audit (8):** `investigation_runs`, `retrieval_attempts`, `evidence_chunks`, `evidence_assessments`, `ground_truth_labels`, `audit_events`, `dataset_builds`, `index_builds`.

### 9.2 Claim Diagnoses Table (`claim_diagnoses`)
To resolve `claim_lines.diagnosis_pointers` into a normalized, enforceable relationship, the `claim_diagnoses` table is introduced:
- Stores diagnosis pointers 1 through 12 matching standard CMS-1500 Box 21 / 837 claim header standards.
- Links `claim_id` to `diagnosis_code` and optional `condition_id`.
- Enforces `UNIQUE(claim_id, diagnosis_pointer)`.

### 9.3 Service Code Integrity & Surrogate Identification
`service_codes` possesses surrogate primary key `id` (UUID) with `UNIQUE(system, code)`. Foreign references (`claim_lines.service_code_id`, `authorizations.service_code_id`) link directly to `service_codes.id`, eliminating composite key ambiguity while preserving standard code strings for display.

### 9.4 Polymorphic Evidence Provenance Enforcement
`evidence_chunks` supports polymorphic clinical sources while enforcing relational integrity via explicit nullable foreign keys:
- `clinical_document_id` (FK -> `clinical_documents.id`)
- `diagnostic_report_id` (FK -> `diagnostic_reports.id`)
- `observation_id` (FK -> `observations.id`)
- `encounter_id` (FK -> `encounters.id`)
- `condition_id` (FK -> `conditions.id`)
- `procedure_id` (FK -> `procedures.id`)
- `fhir_resource_id` (FK -> `fhir_resources.id`)
- Database `CHECK` constraint guarantees at least one canonical source foreign key is non-null.

### 9.5 Database-Level Tenant & Patient Isolation Invariants
To prevent cross-patient or cross-tenant foreign key leakage:
- `patients` has `UNIQUE(id, organization_id)`.
- `claims` enforces composite foreign key `FOREIGN KEY (patient_id, organization_id) REFERENCES patients(id, organization_id)`.
- `encounters` has `UNIQUE(id, patient_id)`.
- Child clinical records (`conditions`, `procedures`, `observations`, `medication_requests`, `diagnostic_reports`, `clinical_documents`) enforce composite foreign key `FOREIGN KEY (encounter_id, patient_id) REFERENCES encounters(id, patient_id)`.
- Database engine blocks cross-patient associations at commit time.

### 9.6 Evidence Corpus Ingestion Schema Architecture & Scope Invariants (ADR-007)
- **Problem Statement:** Phase 6 requires ingesting patient-scoped clinical narratives/structured records, shared payer-scoped coverage policies, and claim-scoped denial adjudication events into an evidence corpus. Payer policies are shared across all patients covered by that payer and must never be falsely attributed to an individual patient.
- **Architectural Trade-Off Evaluated:**
  - *Option A:* Introduce a 41st table `payer_policy_chunks` separate from `evidence_chunks`. Rejected because it fragments downstream hybrid retrieval, requires complex polymorphic foreign key arrays in `evidence_assessments.supporting_chunk_ids`, and violates the strict 40-table inventory contract tested in `test_models.py`.
  - *Option B (Chosen):* Extend `evidence_chunks` to support polymorphic corpus documents with explicit scoping columns and database-level scope check constraints (`ck_chunk_scope_consistency`).
- **Schema Details (Migration `8d90fee8c001_extend_evidence_chunks_corpus`):**
  - Columns Added: `dataset_build_id`, `evidentiary_role`, `payer_id`, `payer_policy_version_id`, `claim_id`, `denial_event_id`, `section_name`, `source_text_offset`, `source_text_length`, `metadata` (JSONB).
  - Scope Check Constraint (`ck_chunk_scope_consistency`):
    - `PAYER_POLICY`: `patient_id IS NULL AND payer_id IS NOT NULL AND payer_policy_version_id IS NOT NULL AND claim_id IS NULL AND denial_event_id IS NULL`.
    - `CLINICAL_SUPPORTING`: `patient_id IS NOT NULL AND payer_id IS NULL AND payer_policy_version_id IS NULL AND denial_event_id IS NULL`.
    - `DENIAL_CONTEXT`: `patient_id IS NOT NULL AND claim_id IS NOT NULL AND denial_event_id IS NOT NULL AND payer_policy_version_id IS NULL`.
  - Uniqueness & Supersession: `uq_evidence_chunk_source_version_idx` on `(source_resource_id, chunker_version, chunk_index)` and partial unique index `ix_evidence_chunk_active_source` on `(source_resource_id, chunk_index) WHERE is_active = TRUE`.
  - Zero Patient Leakage: All clinical composite foreign keys (`fk_chunk_clinical_doc_patient`, `fk_chunk_diag_report_patient`, etc.) and claim foreign keys (`fk_chunk_claim_patient`, `fk_chunk_denial_claim`) remain strictly enforced by PostgreSQL.

---

## ADR-008: PostgreSQL GIN Expression Index for Lexical Full-Text Search

- **Date:** 2026-10-13
- **Status:** **ACCEPTED**
- **Context:**
  Phase 7 requires implementing sparse lexical retrieval alongside dense semantic vector retrieval (`BAAI/bge-small-en-v1.5` + `faiss-cpu`) over canonical `evidence_chunks.content`. Lexical queries must match medical terminology, clinical procedure codes, ICD-10 diagnosis codes (e.g., `E11.9`), CPT codes (e.g., `99213`), and payer denial reasons (e.g., `PR-204`, `CO-16`, `N115`) while enforcing strict patient and payer scoping.
- **Decision:**
  Create a PostgreSQL GIN expression index on `to_tsvector('english', content)` named `ix_evidence_chunks_content_fts` via forward Alembic migration `9e01fee8d001_add_evidence_chunks_fts_index.py`.
- **Alternatives Considered:**
  1. *External Search Service (Elasticsearch / Meilisearch):* Rejected. Violates the local zero-external-dependency requirement and introduces secondary index synchronization overhead.
  2. *Dedicated `tsvector` Column:* Rejected. Increases table storage and write amplification when an expression GIN index achieves the identical query plan.
  3. *PostgreSQL GIN Expression Index (Chosen):* Preserves the strict 40-table architectural invariant (`test_models.py`), requires zero table storage modifications, and leverages PostgreSQL native `to_tsquery` and `ts_rank` ranking functions with parameterized SQL.
- **Integrity & Scoping:**
  - Lexical queries apply parameterized scope filters (`patient_id`, `payer_id`, `claim_id`, `evidentiary_role`, `is_active = TRUE`) directly in SQL.
  - Zero cross-patient leakage: clinical documents are query-restricted to the authorized patient ID.
  - Forward migration `9e01fee8d001` passed complete downgrade and upgrade lifecycle tests.
