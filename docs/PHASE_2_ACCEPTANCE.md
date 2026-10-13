# Phase 2 Acceptance Gate & Database Foundation Report

**Project Title:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management: A Human-in-the-Loop Approach  
**Phase:** Phase 2 — Database Foundation  
**Status:** COMPLETE — READY FOR PHASE 3  
**Date of Audit:** October 13, 2026  
**System of Record:** PostgreSQL 18.6 (`denial-postgres` Docker container)

---

## 1. Executive Summary

In strict accordance with `AGENTS.md`, `docs/PHASES.md`, and the Phase 2 implementation authorization, the durable database foundation for the platform has been implemented, validated, and frozen.

PostgreSQL 18 is now fully configured as the canonical system of record with **40 relational tables** mapped via typed SQLAlchemy 2 declarative models and managed by version-controlled Alembic migrations.

All database constraints (temporal coherence, non-negative monetary amounts, valid claim diagnosis pointer ranges), composite foreign keys for tenant and patient isolation, and explicit polymorphic provenance foreign keys are verified with automated tests.

---

## 2. Authoritative Table Inventory Reconciliation (40 Tables)

During the Step 1 specification audit, the table count was reconciled from the informal 32-entity summary to an exact, authoritative count of **40 relational tables** across four core domains:

```text
Domain 1: Identity, Organization & Access (8 Tables)
├── organizations              - Healthcare provider organizations / billing groups (tenants)
├── facilities                 - Service locations / sites of care
├── practitioners              - Rendering clinicians (MD, DO, NP)
├── users                      - Application login users (analysts, reviewers, managers)
├── roles                      - System RBAC role definitions
├── user_roles                 - User-to-role assignment junction table
├── organization_memberships   - User-to-organization tenancy junction table
└── patients                   - Synthetic patient demographic identities

Domain 2: Clinical Records & FHIR (8 Tables)
├── encounters                 - Inpatient, outpatient, emergency visits
├── conditions                 - Diagnoses and active clinical problems (ICD-10)
├── procedures                 - Surgical and clinical interventions (CPT/HCPCS)
├── observations               - Labs, vitals, qualitative diagnostic findings (LOINC)
├── medication_requests        - Drug prescriptions and orders (RxNorm)
├── diagnostic_reports         - Radiology and pathology interpretive reports
├── clinical_documents         - Narrative clinical notes (Operative, H&P, Progress Notes)
└── fhir_resources             - Validated HL7 FHIR R4 JSON payloads

Domain 3: Insurance, Claims & Denials (16 Tables)
├── payers                     - Commercial, Medicare Advantage, Medicaid payers
├── payer_plans                - Specific insurance benefit plan products
├── coverage                   - Member insurance policy coverage periods
├── service_codes              - Standard billing codes with surrogate UUIDs
├── authorizations             - Prior authorization approvals and reference numbers
├── claims                     - Health insurance billing claims (837-inspired)
├── claim_diagnoses            - Normalized claim header diagnoses (pointers 1..12)
├── claim_lines                - Individual billable service lines with charge amounts
├── remittances                - Electronic Remittance Advice (835) transaction batches
├── remittance_lines           - Line-level adjudication, paid/allowed amounts, CARC/RARC
├── denial_events              - First-class claim denials requiring RCM investigation
├── payer_policy_versions      - Versioned payer clinical coverage policy text & criteria
├── appeals                    - Appeal process lifecycle containers
├── appeal_draft_versions      - Immutable append-only appeal draft snapshots
├── appeal_decisions           - Human supervisory review decisions (Approve/Reject)
└── exports                    - Audited export artifacts (PDF/Markdown)

Domain 4: Investigation, Retrieval, Evaluation & Audit (8 Tables)
├── investigation_runs         - LangGraph agent investigation executions
├── retrieval_attempts         - Forensic log of each search attempt & latency
├── evidence_chunks            - Atomic retrieval units with explicit provenance FKs
├── evidence_assessments       - Evaluation of policy requirements against chunks
├── ground_truth_labels        - Locked benchmark annotations for RAG evaluation
├── audit_events               - Immutable security and operational event trail
├── dataset_builds             - Synthetic data generator run metadata and manifests
└── index_builds               - FAISS vector and lexical search build manifests
```

---

## 3. Key Design Decisions & Invariant Implementations

### 3.1 Claim Diagnoses Normalization (`claim_diagnoses`)
`claim_lines.diagnosis_pointers` is an array of integer pointers pointing to header diagnoses on CMS-1500 / 837 claims. The `claim_diagnoses` table normalizes this relationship:
- Pointers are constrained to $1 \le 	ext{pointer} \le 12$ via `CheckConstraint`.
- `UniqueConstraint("claim_id", "diagnosis_pointer")` prevents duplicate pointer assignment.

### 3.2 Service Code Unambiguity
`service_codes` uses a surrogate UUID `id` with `UniqueConstraint("system", "code")`. Foreign references (`claim_lines.service_code_id`, `authorizations.service_code_id`) link directly to `service_codes.id`, eliminating composite foreign key ambiguity while caching the code string for direct inspection.

### 3.3 Explicit Polymorphic Evidence Provenance
PostgreSQL cannot enforce traditional foreign keys across polymorphic targets. `evidence_chunks` resolves this by providing explicit nullable foreign keys:
- `clinical_document_id` (FK -> `clinical_documents.id`)
- `diagnostic_report_id` (FK -> `diagnostic_reports.id`)
- `observation_id` (FK -> `observations.id`)
- `condition_id` (FK -> `conditions.id`)
- `procedure_id` (FK -> `procedures.id`)
- `fhir_resource_id` (FK -> `fhir_resources.id`)
This guarantees genuine database-level referential integrity without orphan chunks.

### 3.4 Database-Enforced Tenant & Patient Isolation
To prevent cross-patient or cross-tenant data leakage at the relational layer:
1. **Tenant Isolation:** `patients` enforces `UNIQUE(id, organization_id)`. `claims` enforces composite foreign key `FOREIGN KEY (patient_id, organization_id) REFERENCES patients(id, organization_id)`. A claim cannot link to a patient from another organization.
2. **Patient Isolation:** `encounters` enforces `UNIQUE(id, patient_id)`. Child clinical records enforce `FOREIGN KEY (encounter_id, patient_id) REFERENCES encounters(id, patient_id)`. A condition, procedure, or note cannot link to an encounter belonging to a different patient.

---

## 4. Database Preservation & Environment Audit

- **Container Status:** The existing container `denial-postgres` was preserved without recreation, reset, or restart.
- **Data Protection:** The primary database `denial_management` was verified clean before applying migrations and upgraded directly to `head` (40 application tables + `alembic_version`).
- **Isolated Disposable Test Database:** All migration rollback testing (`upgrade` -> `downgrade` -> `re-upgrade`) was executed against an isolated temporary database `denial_management_test`. The primary database was never downgraded.
- **Secret Management:** Database connection URLs are injected dynamically from Pydantic settings; zero secrets are stored in `alembic.ini` or committed files.

---

## 5. Verification & Test Evidence

### 5.1 Test Execution Suite (`pytest`)
All 15 unit and integration tests passed:
```text
tests/integration/test_alembic_migrations.py::test_alembic_migration_lifecycle PASSED [  6%]
tests/integration/test_database_schema.py::test_encounter_temporal_coherence_constraint PASSED [ 13%]
tests/integration/test_database_schema.py::test_claim_negative_amount_constraint PASSED [ 20%]
tests/integration/test_database_schema.py::test_claim_diagnosis_pointer_range_constraint PASSED [ 26%]
tests/integration/test_database_schema.py::test_tenant_isolation_composite_foreign_key PASSED [ 33%]
tests/integration/test_database_schema.py::test_patient_isolation_clinical_composite_foreign_key PASSED [ 40%]
tests/integration/test_database_schema.py::test_evidence_chunk_canonical_provenance PASSED [ 46%]
tests/unit/test_health.py::test_health_liveness PASSED                   [ 53%]
tests/unit/test_health.py::test_root_endpoint PASSED                     [ 60%]
tests/unit/test_health.py::test_database_connection PASSED               [ 66%]
tests/unit/test_health.py::test_ollama_connection PASSED                 [ 73%]
tests/unit/test_models.py::test_authoritative_table_inventory_count PASSED [ 80%]
tests/unit/test_models.py::test_table_names_match_authoritative_list PASSED [ 86%]
tests/unit/test_models.py::test_tables_have_primary_keys PASSED          [ 93%]
tests/unit/test_models.py::test_tenant_and_patient_composite_foreign_keys PASSED [100%]

============================= 15 passed in 2.01s ==============================
```

### 5.2 Code Quality & Linting (`ruff`)
```text
.venv\Scriptsuff check .
All checks passed!
```

### 5.3 API Readiness Smoke Test (`scripts/smoke_test_api.py`)
- `GET /` -> HTTP 200 OK
- `GET /api/health` -> HTTP 200 OK
- `GET /api/health/db` -> HTTP 200 OK (`PostgreSQL 18.6 connected`)
- `GET /api/health/llm` -> HTTP 200 OK (`qwen3:8b available`)
- `GET /api/health/all` -> HTTP 200 OK

---

## 6. Phase 2 Completion Gate

> **GATE STATUS: PHASE 2 COMPLETE.**  
> In strict compliance with `AGENTS.md` and `docs/PHASES.md`:  
> - **The durable database schema has been created via Alembic migrations.**  
> - **All constraints, indexes, and isolation invariants are tested and passing.**  
> - **No bulk synthetic data has been generated yet.**  
>  
> The system now pauses and awaits authorization before beginning **Phase 3: Synthetic Data Factory v1: Organizations and Patients**.
