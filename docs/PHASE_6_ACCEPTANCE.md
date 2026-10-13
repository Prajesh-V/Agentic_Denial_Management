# Phase 6 Acceptance Report: Evidence Corpus Ingestion & Document Processing Pipeline

**Project:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management: A Human-in-the-Loop Approach  
**Phase:** 6 — Evidence Corpus Ingestion & Document Processing Pipeline  
**Execution Date:** 2026-10-13  
**Status:** **ACCEPTED & READY FOR PHASE 7 GATE**  
**Core Product Promise:** *AI investigates. Evidence supports. A human decides.*

---

## 1. Executive Summary

Phase 6 implements the complete, deterministic, and provenance-preserving **Evidence Corpus Ingestion and Document Processing Pipeline** for the Agentic Denial Management platform.

The system ingests canonical synthetic clinical documents, diagnostic conclusions, structured clinical records, shared payer coverage policy criteria, and claim-level denial adjudication events from PostgreSQL. It processes and normalizes the texts safely, decomposes them into ordered, section-aware `EvidenceChunk` records with character offsets, deterministic token counts, and SHA-256 hashes, and guarantees strict patient isolation and tenant scoping through database check constraints and composite foreign keys.

All operations were validated against the existing baseline build `synth_smoke_20261013_v1`, preserving all 40 canonical tables, historical synthetic records, and full test suite compatibility.

---

## 2. Finalized Corpus-Source Architecture

### 2.1 The 40-Table Architecture Preservation (ADR-007)
Rather than introducing a 41st table (e.g. `payer_policy_chunks`) that would fragment downstream hybrid retrieval and violate the authoritative 40-table inventory contract tested in `tests/unit/test_models.py`, `EvidenceChunk` was extended through a forward-only Alembic migration (`8d90fee8c001_extend_evidence_chunks_corpus`):
- `patient_id` was made `nullable=True` exclusively for shared `PAYER_POLICY` documents.
- Scope columns were added: `dataset_build_id`, `evidentiary_role`, `payer_id`, `payer_policy_version_id`, `claim_id`, `denial_event_id`, `section_name`, `source_text_offset`, `source_text_length`, and `metadata` (`JSONB`).
- Strict composite foreign keys were retained for all clinical records (`fk_chunk_clinical_doc_patient`, `fk_chunk_diag_report_patient`, etc.), guaranteeing zero cross-patient foreign key leakage.
- New relational constraints were established:
  - `fk_chunk_denial_claim`: `(denial_event_id, claim_id) -> denial_events(id, claim_id)`
  - `fk_chunk_claim_patient`: `(claim_id, patient_id) -> claims(id, patient_id)`
  - `fk_chunk_payer_policy_version`: `payer_policy_version_id -> payer_policy_versions(id)`
  - `fk_chunk_payer`: `payer_id -> payers(id)`

### 2.2 Evidentiary Roles & Scopes
Every chunk is classified into one of four immutable roles:
1. `CLINICAL_SUPPORTING`: Patient-scoped evidence authored by clinicians. `patient_id` is mandatory; `payer_id`, `payer_policy_version_id`, and `denial_event_id` are strictly prohibited.
2. `PAYER_POLICY`: Payer-scoped shared documents. `patient_id` is strictly `NULL`; `payer_id` and `payer_policy_version_id` are mandatory. Never attributed to an individual patient.
3. `DENIAL_CONTEXT`: Claim-adjudication context. `patient_id`, `claim_id`, and `denial_event_id` are mandatory. Clearly delineated as explanation for denial rather than clinical truth.
4. `ADMINISTRATIVE`: Encounter and billing operational context.

These invariants are enforced at the PostgreSQL engine level via check constraint `ck_chunk_scope_consistency`.

---

## 3. Modular Source Adapters

Implemented modular adapters under `backend/app/ingestion/adapters/`:
- **`ClinicalDocumentAdapter`**: Extracts narrative consultation notes, progress notes, and operative reports. Extracts section headers (`CHIEF COMPLAINT:`, `HISTORY OF PRESENT ILLNESS:`, `PHYSICAL EXAMINATION:`, `ASSESSMENT AND PLAN:`, etc.) into structured `DocumentSection` objects.
- **`DiagnosticReportAdapter`**: Extracts diagnostic findings, statuses, and conclusions (e.g. standing radiograph reports, MRI interpretations).
- **`StructuredClinicalAdapter`**: Extracts and deterministically formats `Observation` (vital signs, lab results with reference ranges), `Condition` (clinical status, onset), and `Procedure` (performed time, status) into retrievable narrative representations.
- **`PayerPolicyAdapter`**: Extracts synthetic payer policy version texts and parses numbered policy sections (`1. DESCRIPTION:`, `2. COVERAGE CRITERIA:`, etc.) and structured requirements criteria (`requirements_spec`). Strictly payer-scoped (`patient_id = None`).
- **`DenialContextAdapter`**: Extracts adjudication records for denied claims, including CARC/RARC codes, denied amounts, appeal deadlines, and adjudication findings.

---

## 4. Deterministic Normalization & Chunking

### 4.1 Safe Text Normalization (`SafeTextNormalizer`)
- Unicode NFKC normalization.
- Linebreak normalization (`\r\n` -> `\n`).
- Strips trailing whitespace per line while preserving indentation.
- Collapses excessive newlines (3+ -> 2).
- Zero rewriting, summarization, or hallucination via LLM.
- Preserves dates, negation words, dosages, and CPT/ICD-10 codes.
- Rejects empty, None, or whitespace-only documents with explicit `ValueError`.

### 4.2 Deterministic Evidence Chunker (`DeterministicEvidenceChunker`)
- **Version:** Default `v1.0`.
- **Target Chunk Size:** 600 characters.
- **Chunk Overlap:** 80 characters.
- **Section-Aware:** Chunks along parsed section boundaries first; splits long sections at natural paragraph (`\n\n`), newline (`\n`), or sentence boundaries (`. `).
- **Offsets:** Records precise character offset `source_text_offset` and `source_text_length` relative to the document text.
- **Token Estimation:** Deterministic regex-based token counter (`\w+|[^\w\s]`).
- **Hashing:** Re-computable SHA-256 text hash for every individual chunk.

---

## 5. Idempotent Ingestion & CLI Management

Provided CLI commands via `scripts/ingest_corpus.py`:
- Ingestion with dry-run support: `python scripts/ingest_corpus.py --dataset <build-id> --dry-run`
- Live ingestion: `python scripts/ingest_corpus.py --dataset <build-id>`
- Selective source ingestion: `python scripts/ingest_corpus.py --dataset <build-id> --source-types ClinicalDocument,PayerPolicyVersion`
- Comprehensive corpus validation: `python scripts/ingest_corpus.py --dataset <build-id> --validate`
- Build-safe cleanup: `python scripts/ingest_corpus.py --dataset <build-id> --reset`

### Idempotency and Supersession Guarantees:
- Re-running the ingestion pipeline on unchanged sources produces `chunks_persisted = 0` and increments `chunks_skipped_duplicate` with zero duplicate rows.
- Reprocessing with an updated chunker version (e.g. `v2.0`) supersedes existing active chunks (`is_active = False`) and creates new active chunks with updated versioning and provenance intact.
- Calling `--reset` deletes only chunks belonging to the specified build, leaving canonical patients, claims, and policies completely intact.

---

## 6. Demonstration on Baseline Dataset (`synth_smoke_20261013_v1`)

Actual execution results on the canonical smoke dataset:

```text
==================================================
EVIDENCE CORPUS INGESTION MANIFEST
==================================================
Run ID:                 ingest_synth_smoke_20261013_v1_1791908399
Dataset Build:          synth_smoke_20261013_v1
Processor Version:      processor_v1_20261013
Chunker Version:        v1.0
Duration (s):           1.189s
Validation Passed:      True
--------------------------------------------------
Sources Discovered:     306
Sources Processed:      306
Sources Skipped:        0
Chunks Generated:       545
Chunks Persisted:       473
Chunks Skipped (Dupe):  72 (Shared Payer Policies already ingested)
Chunks Superseded:      0

Documents Processed by Source Type:
  - ClinicalDocument:   50
  - DiagnosticReport:   25
  - Observation:        125
  - Condition:          50
  - Procedure:          25
  - PayerPolicyVersion: 18
  - DenialEvent:        13

Documents by Evidentiary Role:
  - CLINICAL_SUPPORTING: 275
  - PAYER_POLICY:        18
  - DENIAL_CONTEXT:      13
```

### Idempotent Re-Run Verification:
```text
Run ID:                 ingest_synth_smoke_20261013_v1_1791908409
Duration (s):           1.049s
Validation Passed:      True
Sources Discovered:     306
Sources Processed:      306
Chunks Generated:       545
Chunks Persisted:       0
Chunks Skipped (Dupe):  545
Chunks Superseded:      0
```

### Selected Chunks Verification:
1. **Clinical Evidence Chunk (`c1e08f1a-f115-448b-bda6-de09e37d400f`)**:
   - `evidentiary_role`: `CLINICAL_SUPPORTING`
   - `clinical_document_id`: points to canonical document `8b03013d-9173-4481-8362-47bf3508611c`
   - `patient_id`: `a9d25b6a-12ba-4a18-bfbe-eb57ce2e0883` (matches document patient perfectly)
   - `payer_id` / `policy_version_id`: strictly `None`
   - `section_name`: `HISTORY`
2. **Payer Policy Chunk (`a0fff7df-57b3-447e-b5f7-cdfc23053b37`)**:
   - `evidentiary_role`: `PAYER_POLICY`
   - `payer_policy_version_id`: points to `d353e1b8-334b-41b6-be7e-1d8d8068f9e4` (`POL-SYNTH-ORTHO-001 v1.0`)
   - `payer_id`: `ce762692-dbfb-4be3-b690-3e2f6a8aed82`
   - `patient_id`: strictly `None` (zero patient contamination)
3. **Denial Context Chunk (`8debaa24-7ec4-4b15-a7d0-04c3d06767a2`)**:
   - `evidentiary_role`: `DENIAL_CONTEXT`
   - `denial_event_id`: points to `dd59e07e-b1f6-4752-9985-04e1bf99bf2f`
   - `claim_id`: points to `48be70ea-d00f-4897-b2b7-af639cae53a6`
   - `denial_category`: `MED_NEC_01` (CARC 50 / RARC N115)

---

## 7. Automated Test Suite Verification

### Full Test Execution:
```bash
pytest -v tests
```
**Result:** `56 passed in 5.67s` (42 baseline tests + 14 Phase 6 integration tests).

### Code Style & Linter:
```bash
ruff check .
```
**Result:** `All checks passed!`

### API Smoke Health Check:
```bash
python scripts/smoke_test_api.py
```
**Result:** `All API endpoints responded with HTTP 200 and healthy payloads!`

---

## 8. Known Limitations & Non-Goals in Phase 6

- Vector embeddings and FAISS index construction are strictly reserved for Phase 7 (Hybrid Retrieval).
- Lexical indices (e.g. BM25 / PostgreSQL full-text search) will be built in Phase 7.
- No autonomous LLM summarization or agentic retrieval workflows were executed.
