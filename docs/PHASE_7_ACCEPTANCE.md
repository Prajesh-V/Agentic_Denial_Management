# Phase 7 Acceptance Report: Hybrid Retrieval & Investigation Indexing Pipeline

**Project:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management: A Human-in-the-Loop Approach  
**Phase:** 7 — Hybrid Retrieval & Investigation Indexing Pipeline  
**Execution Date:** 2026-10-13  
**Status:** **ACCEPTED & READY FOR PHASE 8 GATE**  
**Baseline Commit:** `77e57b5`  
**Core Product Promise:** *AI investigates. Evidence supports. A human decides.*

---

## 1. Executive Summary

Phase 7 implements the reproducible, provenance-preserving **Hybrid Evidence Retrieval & Investigation Indexing Pipeline** for the Agentic Denial Management platform.

The system combines:
1. **Dense Semantic Retrieval:** Local embeddings using `BAAI/bge-small-en-v1.5` (384 dimensions) with L2 normalization and cosine similarity via CPU-based `faiss-cpu`.
2. **Sparse Lexical Retrieval:** Native PostgreSQL full-text search with a GIN expression index on `to_tsvector('english', content)` and `ts_rank` scoring.
3. **Reciprocal Rank Fusion (RRF):** Formula `RRF(d) = Σ 1 / (k + rank_i(d))` with configurable $k=60$ and deterministic tie-breaking.
4. **Relational Scope Enforcement & Patient Isolation:** Mandatory authorization boundary ensuring Patient A can never retrieve Patient B's clinical evidence, claims cannot receive foreign denial context, and shared payer policies are never falsely attributed to individual patients.
5. **Relational Index Tracking:** Synchronized with the canonical `index_builds` table (one of the 40 schema tables) and atomic disk persistence under `data/indexes/`.

All 74 automated tests pass, zero Ruff lints exist, Alembic migration lifecycle is verified, and the smoke dataset `synth_smoke_20261013_v1` was indexed and queried cleanly.

---

## 2. Architecture & Pipeline Design

### 2.1 Component Overview
The retrieval subsystem is structured modularly in `backend/app/retrieval/`:

- `schemas.py`: Pydantic v2 contracts for `RetrievalRequest`, `RetrievalResponse`, `RetrievalResultItem`, `RetrievalScopeContext`, and `IndexBuildManifest`.
- `embedder.py`: `LocalEmbeddingService` wrapping `BAAI/bge-small-en-v1.5` with query prefix conventions (`"Represent this sentence for searching relevant passages: "`), L2 vector normalization, dimension validation, and `MockEmbeddingService` for offline/unit testing.
- `faiss_index.py`: `FAISSVectorIndex` wrapping `faiss.IndexFlatIP(384)`, managing bidirectional mapping between vector positions and canonical `EvidenceChunk.id` UUIDs, with atomic `.faiss` and `manifest.json` file writes and SHA-256 integrity validation.
- `lexical.py`: `PostgresLexicalSearchService` executing parameterized PostgreSQL queries with `to_tsquery('english', :tsquery)` and `ts_rank` scoring, safely handling medical codes (`99213`, `E11.9`), denial codes (`PR-204`, `CO-16`), and SQL injection attempts.
- `scope_filter.py`: `RetrievalScopeFilter` enforcing database-level boundaries for clinical evidence, payer policies, denial contexts, and temporal policy validity windows (`effective_start` to `effective_end`).
- `fusion.py`: `ReciprocalRankFusionEngine` computing RRF scores, generating transparent explanations, and executing deterministic tie-breaking.
- `service.py`: `HybridRetrievalService` orchestrating indexing, validation, and multi-channel retrieval.

```
                          [ RetrievalRequest ]
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                             ▼
       [ Semantic Channel ]              [ Lexical Channel ]
    BAAI/bge-small-en-v1.5 (384d)     PostgreSQL FTS (GIN Index)
     FAISS IndexFlatIP (Cosine)      ts_rank(to_tsvector, tsquery)
                    │                             │
                    ▼                             ▼
         Raw Vector Candidates         Raw Lexical Candidates
                    │                             │
                    └──────────────┬──────────────┘
                                   ▼
                   [ Database Scope Authorization ]
              - Clinical: patient_id == req.patient_id
              - Policy: payer_id == claim.payer_id, patient_id IS NULL
              - Denial: claim_id == req.claim_id, patient_id == req.patient_id
              - Temporal: effective_start <= service_date <= effective_end
                                   │
                                   ▼
                [ Reciprocal Rank Fusion (k=60) ]
                      RRF(d) = Σ 1 / (k + rank)
                                   │
                                   ▼
             [ Provenance Hydration & Explanation ]
                                   │
                                   ▼
                         [ RetrievalResponse ]
```

---

## 3. Database Migration & Schema Alignment (ADR-008)

To support performant, index-backed lexical search without adding new tables (preserving the authoritative 40-table invariant):
- **Migration `9e01fee8d001_add_evidence_chunks_fts_index.py`**:
  - `upgrade()`: Creates `ix_evidence_chunks_content_fts` on `evidence_chunks USING gin (to_tsvector('english', content))`.
  - `downgrade()`: Drops `ix_evidence_chunks_content_fts`.
- **Model Registration**: Added `Index("ix_evidence_chunks_content_fts", text("to_tsvector('english', content)"), postgresql_using="gin")` to `EvidenceChunk.__table_args__`.
- **Alembic Lifecycle**: Upgraded cleanly, and verified via `tests/integration/test_alembic_migrations.py` with complete downgrade to `base` and re-upgrade to `head`.

---

## 4. Security & Evidentiary Scope Rules

| Evidentiary Role | Patient Scoping | Payer Scoping | Claim Scoping | Temporal Rule |
|---|---|---|---|---|
| `CLINICAL_SUPPORTING` | Strict (`patient_id == req.patient_id`) | None | Optional | Linked encounter date |
| `PAYER_POLICY` | **Strict NULL** (`patient_id IS NULL`) | Strict (`payer_id == claim.payer_id`) | None | `effective_start <= service_date <= effective_end` |
| `DENIAL_CONTEXT` | Strict (`patient_id == req.patient_id`) | Inferred from claim | Strict (`claim_id == req.claim_id`) | Denial event date |
| `ADMINISTRATIVE` | Permitted (`patient_id == req.patient_id`) | Inferred | Permitted (`claim_id == req.claim_id`) | Service timeline |

- **Fail-Closed Boundary:** Missing `patient_id` or `claim_id` raises `ScopeValidationError`.
- **Cross-Patient Defense:** Injected foreign `patient_id` for an authorized claim is rejected immediately with `Scope contradiction`.
- **No False Attribution:** Payer policies are shared institutional documents and can never be attributed to individual patient files.

---

## 5. Automated Verification & Test Results

The full test suite was executed against the running PostgreSQL container (`denial-postgres`):

```bash
.venv\Scripts\pytest -v tests
```

**Results:**
- **Total Tests:** 74 passed in 27.63s
- **Baseline Schema & Identity:** 5 passed
- **Synthetic Factory Determinism & Constraints:** 13 passed
- **Database Triggers & Composite Keys:** 21 passed
- **Evidence Corpus Ingestion (Phase 6):** 14 passed
- **Hybrid Retrieval & Investigation Indexing (Phase 7):** 18 passed
- **API Health Checks:** 4 passed

### Phase 7 Test Suite Breakdown (`tests/integration/test_hybrid_retrieval.py`):
1. `TestSemanticEmbeddingAndFAISS::test_embedding_dimensions_and_l2_normalization` — PASSED
2. `TestSemanticEmbeddingAndFAISS::test_empty_and_whitespace_text_rejection` — PASSED
3. `TestSemanticEmbeddingAndFAISS::test_faiss_index_mapping_and_inner_product_search` — PASSED
4. `TestSemanticEmbeddingAndFAISS::test_faiss_atomic_save_load_and_hash_integrity` — PASSED
5. `TestSemanticEmbeddingAndFAISS::test_stale_index_detection` — PASSED
6. `TestPostgreSQLLexicalRetrieval::test_lexical_search_policy_and_medical_terms` — PASSED
7. `TestPostgreSQLLexicalRetrieval::test_lexical_search_codes_and_identifiers` — PASSED
8. `TestPostgreSQLLexicalRetrieval::test_sql_injection_and_punctuation_safety` — PASSED
9. `TestReciprocalRankFusion::test_rrf_scoring_accuracy_and_fusion` — PASSED
10. `TestReciprocalRankFusion::test_deterministic_tie_breaking` — PASSED
11. `TestSecurityAndEvidentiaryIntegrity::test_cross_patient_leakage_blocked` — PASSED
12. `TestSecurityAndEvidentiaryIntegrity::test_clinical_supporting_evidence_strictly_same_patient` — PASSED
13. `TestSecurityAndEvidentiaryIntegrity::test_payer_policy_never_patient_owned` — PASSED
14. `TestSecurityAndEvidentiaryIntegrity::test_denial_context_restricted_to_investigated_claim` — PASSED
15. `TestSecurityAndEvidentiaryIntegrity::test_policy_effective_date_enforcement` — PASSED
16. `TestSecurityAndEvidentiaryIntegrity::test_inactive_and_superseded_chunks_rejected` — PASSED
17. `TestEndToEndHybridRetrievalPipeline::test_end_to_end_hybrid_query_stability` — PASSED
18. `TestEndToEndHybridRetrievalPipeline::test_indexing_does_not_mutate_canonical_sources_or_duplicate_chunks` — PASSED

---

## 6. Live Smoke Demonstration (`synth_smoke_20261013_v1`)

### 6.1 Index Build Execution
```bash
python scripts/rebuild_retrieval_index.py --dataset synth_smoke_20261013_v1 --force
```
- **Index ID:** `idx_bge_small_v1_synth_smoke_20261013_v1`
- **Embedding Model:** `BAAI/bge-small-en-v1.5` (384 dimensions)
- **Active Chunks Indexed:** 545 (460 clinical supporting, 72 shared payer policies, 13 denial contexts)
- **FAISS File Hash:** `846fb8254f09aaf9...`
- **Corpus Fingerprint:** `16650cb7c5a76ca0...`
- **Status:** `READY`

### 6.2 Index Validation Execution
```bash
python scripts/validate_retrieval_index.py --dataset synth_smoke_20261013_v1
```
- **Valid:** `True`
- **Stale:** `False`
- **Vector Count:** `545`

### 6.3 Hybrid Query Demonstration
**Query:** `"conservative therapy medical necessity"`  
**Target Claim:** `48be70ea-d00f-4897-b2b7-af639cae53a6` (Denied: `MED_NEC_01`, CARC 50, RARC N115)  
**Target Patient:** `f1070ec6-3aea-4a57-8a68-e169044e8747`  

```text
[Rank #1] Score: 0.032266 | Role: PAYER_POLICY
Source: PayerPolicyVersion (ID: d353e1b8-334b-41b6-be7e-1d8d8068f9e4)
  - Semantic Rank #1 (Cosine Sim: 0.7100)
  - Lexical Rank #3 (ts_rank: 0.0456)
Text Snippet:
  3. EXCLUSIONS: Procedures performed without prior authorization or without documented radiographic and conservative therapy trials will be denied as not medically necessary....
Explanation: Retrieved via hybrid fusion (Fused rank #1, RRF score: 0.032266). Matched both channels: Semantic rank #1 (sim: 0.710), Lexical rank #3 (ts_rank: 0.046). Role: PAYER_POLICY from PayerPolicyVersion.

[Rank #2] Score: 0.032002 | Role: PAYER_POLICY
Source: PayerPolicyVersion (ID: d353e1b8-334b-41b6-be7e-1d8d8068f9e4)
  - Semantic Rank #3 (Cosine Sim: 0.6658)
  - Lexical Rank #2 (ts_rank: 0.0494)

[Rank #3] Score: 0.031281 | Role: CLINICAL_SUPPORTING
Source: ClinicalDocument (ID: f4e9a52d-c20b-4454-9bde-89cabc7c13b0)
  - Semantic Rank #2 (Cosine Sim: 0.6973)
  - Lexical Rank #6 (ts_rank: 0.0304)
Text Snippet:
  CHIEF COMPLAINT: Chronic, severe right knee pain refractory to conservative therapy....
Explanation: Retrieved via hybrid fusion (Fused rank #3, RRF score: 0.031281). Matched both channels: Semantic rank #2 (sim: 0.697), Lexical rank #6 (ts_rank: 0.030). Role: CLINICAL_SUPPORTING from ClinicalDocument.
```

---

## 7. Known Limitations & Phase 8 Boundaries

1. **Retrieval Only:** Phase 7 does not generate appeal letters, execute multi-step investigation graphs, or submit appeals.
2. **Local CPU Embedding:** Real `BAAI/bge-small-en-v1.5` embeddings execute locally on CPU via `sentence-transformers`. Index building takes ~15 seconds for 545 chunks on typical developer hardware.
3. **No Autonomous Decision-Making:** Retrieval scores are ranking heuristics, not coverage determinations. The core rule remains: *AI investigates. Evidence supports. A human decides.*

---

## 8. Acceptance Sign-off

- [x] Baseline verified before changes (`77e57b5`).
- [x] Dense semantic retrieval with `BAAI/bge-small-en-v1.5` and `faiss-cpu` operational.
- [x] Sparse lexical retrieval with PostgreSQL GIN expression index operational.
- [x] Reciprocal Rank Fusion (RRF) with configurable $k=60$ operational.
- [x] Relational patient, tenant, claim, and payer isolation strictly enforced.
- [x] 40-table architecture preserved.
- [x] 74 automated tests passing without skips or regressions.
- [x] Zero Ruff errors across codebase.
- [x] Migration `9e01fee8d001` lifecycle tested.
- [x] Acceptance gate satisfied.
