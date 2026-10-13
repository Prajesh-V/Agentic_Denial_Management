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
