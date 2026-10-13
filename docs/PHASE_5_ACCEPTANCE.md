# Phase 5 Acceptance Report — Synthetic Claims, Payer Policy & Denial World

**Project:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management: A Human-in-the-Loop Approach  
**Repository:** `C:\dev\Agentic_Denial_Management`  
**Phase:** Phase 5 — Synthetic Claims, Payer Policy & Denial World  
**Status:** ACCEPTED & GATED  
**Date:** 2026-10-13  
**Alembic Head Revision:** `7c89fee8b001`  
**Generator Version:** `1.2.0`  
**Schema Version:** `2.1`

---

## 1. Executive Summary

Phase 5 completes the synthetic revenue-cycle generation subsystem by connecting existing patient clinical timelines (encounters, conditions, procedures, observations, notes) to:
- **Payer Policies:** Fictional, versioned clinical coverage criteria (`PayerPolicyVersion`) governing medical necessity, documentation mandates, coding rules, and pre-service authorizations.
- **Prior Authorizations:** Synthetic authorization records (`Authorization`) in `approved`, `expired`, `denied`, and `pending` states.
- **Claims & Claim Diagnoses:** Institutional and professional claims (`Claim`, `ClaimDiagnosis`, `ClaimLine`) with unique claim control numbers, line items, service codes, modifiers, units, and diagnosis pointers.
- **Electronic Remittance Advice (ERA / 835):** Adjudicated remittances (`Remittance`, `RemittanceLine`) balancing allowed, paid, and adjustment amounts.
- **Denial Events:** Granular line-level and whole-claim denial events (`DenialEvent`) representing all **12 authoritative denial categories** (`MED_NEC_01` through `CLIN_CONFLICT_12`) with authentic CARC/RARC codes, denial reasons, and statutory appeal deadlines.

All monetary amounts are reconciled with exact 2-decimal arithmetic. Resetting a build preserves shared reference entities (payers, plans, organizations, facilities, practitioners, service codes, and policies) while cascading clean deletions across build-owned claims, lines, remittances, and denials.

---

## 2. Generator Modules and Architecture

Phase 5 introduces `backend/app/data_factory/generators/claims.py` and extends the pipeline orchestrator and validator:

| Module | Role & Responsibility |
|---|---|
| `backend/app/data_factory/generators/claims.py` | Generates standard service codes, synthetic payer policies, authorizations, claims, claim diagnoses, claim lines, remittances, remittance lines, and denial events covering all 12 categories. |
| `backend/app/data_factory/pipeline.py` | Orchestrates transactional multi-table persistence, reconciles shared `ServiceCode` and `PayerPolicyVersion` reference entities, and provides cascade reset. |
| `backend/app/data_factory/validator.py` | Enforces exact claim and remittance financial reconciliation, foreign key constraints, temporal coherence, and 12-category denial coverage. |
| `backend/app/data_factory/cli.py` | CLI interface displaying revenue-cycle counts upon generation and validation. |
| `backend/app/data_factory/config.py` | Incremented `GENERATOR_VERSION` to `1.2.0` with deterministic domain subseed derivation. |

---

## 3. Build Ownership and Safe Reset Strategy

### 3.1 Build-Owned vs. Shared Reference Entities

| Classification | Database Tables | Lifecycle on Single Build Reset |
|---|---|---|
| **Build-Owned Records** | `claims`, `claim_lines`, `claim_diagnoses`, `authorizations`, `remittances`, `remittance_lines`, `denial_events`, `patients`, `coverage`, clinical records, `fhir_resources`, `dataset_builds` | **Deleted** (cascaded by `patient_id` / `claim_id` / `build_id`). |
| **Shared Reference Data** | `organizations`, `facilities`, `practitioners`, `payers`, `payer_plans`, `users`, `user_roles`, `service_codes`, `payer_policy_versions` | **Preserved** (reused idempotently across builds; never deleted on build reset). |

### 3.2 Reset Deletion Order
The `reset(build_id)` method executes child-to-parent deletion:
1. `DenialEvent` (where `claim_id` in build claims)
2. `RemittanceLine` (where `claim_line_id` in build claim lines)
3. `Remittance` (where `id` in build remittances)
4. `ClaimDiagnosis` (where `claim_id` in build claims)
5. `ClaimLine` (where `claim_id` in build claims)
6. `Claim` (where `patient_id` in build patients)
7. `Authorization` (where `coverage_id` in build coverages)
8. Clinical and FHIR records (FHIR, documents, reports, meds, observations, procedures, conditions, encounters)
9. `Coverage` & `Patient`
10. `DatasetBuild`

---

## 4. The 12 Authoritative Denial Categories Coverage Matrix

All 12 categories specified in `docs/PRODUCT_CONTRACT.md` are deterministically generated with concrete operational triggering conditions:

| Code | Category Name | CARC | RARC | Service Code | Triggering Scenario & Policy Mechanism | Billed | Denied | Claim Status |
|---|---|---|---|---|---|---|---|---|
| `MED_NEC_01` | Medical Necessity | 50 | N115 | `27447` (TKA) | Lack of >= 3 months conservative therapy trial under policy `POL-SYNTH-ORTHO-001`. | $3,500.00 | $3,500.00 | `DENIED` |
| `PA_MISS_02` | Prior Auth Missing/Invalid | 197 | N54 | `63047` (Spine) | Authorization expired 5 days prior to date of service under policy `POL-SYNTH-SPINE-002`. | $4,200.00 | $4,200.00 | `DENIED` |
| `DOC_INCOMP_03` | Incomplete Documentation | 252 | N29 | `63047` (Spine) | Operative report detailing decompressed margins missing from submission package. | $4,200.00 | $4,200.00 | `DENIED` |
| `CODE_MISMATCH_04` | Coding Mismatch | 11 | M64 | `95250` (CGM) | Primary diagnosis pointer set to `I10` (Hypertension) instead of diabetes diagnosis. | $225.00 | $225.00 | `DENIED` |
| `DUP_BUNDLE_05` | Duplicate / Bundled Service | 97 | M15 | `77003` (Fluoro) | Incidental fluoroscopy bundled into primary procedure `63047` under NCCI edits without modifier 59. | $3,880.00 | $480.00 | `PARTIALLY_DENIED` |
| `ELIG_TIMING_06` | Eligibility Timing | 27 | N30 | `99214` (E&M) | Coverage intentionally terminated 15 days prior to encounter service date. | $225.00 | $225.00 | `DENIED` |
| `UNTIMELY_07` | Untimely Filing | 29 | N382 | `99215` (E&M) | Claim submission timestamp 215 days post-service, exceeding payer 90-day filing limit. | $225.00 | $225.00 | `DENIED` |
| `NON_COV_08` | Non-Covered Service / Exclusion | 96 | N425 | `0488T` (Biologic) | Experimental Category III cartilage graft excluded from benefit plan booklet. | $2,900.00 | $2,900.00 | `DENIED` |
| `UNITS_MOD_09` | Units / Modifier Inconsistency | 151 | M51 | `J9999` (HCPCS) | Billed 4 units exceeding CMS Medically Unlikely Edit (MUE) daily allowance of 1 unit. | $450.00 | $337.50 | `PARTIALLY_DENIED` |
| `COB_OTHER_10` | Coordination of Benefits | 22 | N102 | `27447` (TKA) | Payer asserts secondary status; submitted directly without primary payer Explanation of Benefits. | $3,500.00 | $3,500.00 | `DENIED` |
| `INSUF_INFO_11` | Insufficient Info / ADR | 16 | N257 | `45385` (Endo) | Additional Documentation Request (ADR) issued for itemized endoscopic flowsheet. | $1,850.00 | $1,850.00 | `DENIED` |
| `CLIN_CONFLICT_12` | Conflicting Clinical Evidence | 272 | N381 | `92928` (PCI) | Attending consultation notes contradict lesion severity and anatomy in catheterization report. | $5,580.00 | $5,580.00 | `DENIED` |

*Note: Claim 12 also includes a secondary line denied under `DUP_BUNDLE_05`, validating multiple denial events on a single claim.*

---

## 5. Financial & Temporal Validation Rules

Exact decimal arithmetic and temporal order invariants enforced:
1. **Header Total Reconciles Line Total:** `Claim.total_billed_amount == sum(line.billed_amount for line in lines)`.
2. **Remittance Total Reconciles Line Payments:** `Remittance.total_paid_amount == sum(line.paid_amount for line in lines)`.
3. **Line Balance Reconciliation:** For every line, `line.billed_amount == remit_line.paid_amount + remit_line.adjustment_amount`.
4. **Denial Bounds:** `0.00 <= denial_event.denied_amount <= line.billed_amount`.
5. **Temporal Coherence:**
   - `Claim.service_end_date >= Claim.service_start_date`
   - `Claim.submission_date.date() >= Claim.service_start_date`
   - `DenialEvent.denial_date >= Claim.service_start_date`
   - `DenialEvent.appeal_deadline >= DenialEvent.denial_date`
   - `Authorization.effective_end >= Authorization.effective_start`

---

## 6. Persisted Database Inventory — Primary Smoke Build (`synth_smoke_20261013_v1`)

Actual database verification of the smoke build in the running PostgreSQL instance:

```text
============================================================
PHASE 5 DATABASE BREAKDOWN REPORT
============================================================

1. Claims by Status:
  PAID                : count=13, total_billed=$23,600.00
  DENIED              : count=10, total_billed=$26,405.00
  PARTIALLY_DENIED    : count= 2, total_billed=$1,155.00
  ----------------------------------------------------------
  TOTAL CLAIMS        : count=25, total_billed=$51,160.00

2. Line-Level Inventory:
  Claim Lines         : count=32
  Claim Diagnoses     : count=50

3. Denial Events by Category (All 12):
  CLIN_CONFLICT_12   | CARC 272  | RARC N381  | count= 1 | denied=$5,100.00
  COB_OTHER_10       | CARC 22   | RARC N102  | count= 1 | denied=$3,500.00
  CODE_MISMATCH_04   | CARC 11   | RARC M64   | count= 1 | denied=$225.00
  DOC_INCOMP_03      | CARC 252  | RARC N29   | count= 1 | denied=$4,200.00
  DUP_BUNDLE_05      | CARC 97   | RARC M15   | count= 2 | denied=$960.00
  ELIG_TIMING_06     | CARC 27   | RARC N30   | count= 1 | denied=$225.00
  INSUF_INFO_11      | CARC 16   | RARC N257  | count= 1 | denied=$1,850.00
  MED_NEC_01         | CARC 50   | RARC N115  | count= 1 | denied=$3,500.00
  NON_COV_08         | CARC 96   | RARC N425  | count= 1 | denied=$2,900.00
  PA_MISS_02         | CARC 197  | RARC N54   | count= 1 | denied=$4,200.00
  UNITS_MOD_09       | CARC 151  | RARC M51   | count= 1 | denied=$337.50
  UNTIMELY_07        | CARC 29   | RARC N382  | count= 1 | denied=$225.00
  ----------------------------------------------------------
  TOTAL DENIAL EVENTS : count=13, total_denied=$27,222.50

4. Authorizations by Status:
  approved            : count=22
  expired             : count= 1
  denied              : count= 1
  ----------------------------------------------------------
  TOTAL AUTHORIZATIONS: count=24

5. Remittances:
  Remittances (835)   : count=25, total_paid=$22,392.50
  Remittance Lines    : count=32

6. Catalogs & Policies:
  Service Codes (CPT/HCPCS): 11
  Payer Policy Versions:     18 (6 policies x 3 payers)
```

---

## 7. Verification Results

### 7.1 Automated Integration & Unit Tests
```text
C:\dev\Agentic_Denial_Management\.venv\Scripts\pytest -v tests
============================= 42 passed in 4.12s ==============================
```
- Migration lifecycle: PASS
- Check and Foreign Key constraints: PASS
- Canonical determinism & seed divergence: PASS
- Clinical & FHIR timeline coherence: PASS
- All 12 denial categories coverage: PASS
- Financial arithmetic reconciliation: PASS
- Safe cascade reset & build isolation: PASS

### 7.2 Linter Audit
```text
C:\dev\Agentic_Denial_Management\.venv\Scripts\ruff check .
All checks passed!
```

### 7.3 API Health Smoke Test
```text
/api/health         : status=200, json={'status': 'ok', 'app': 'Agentic Denial Management', 'version': '0.1.0'}
/api/health/db      : status=200, json={'status': 'connected', 'database': 'denial_management'}
/api/health/llm     : status=200, json={'status': 'connected', 'base_url': 'http://127.0.0.1:11434'}
```

---

## 8. Database Preservation Checks & Limitations

- **Container & Database:** PostgreSQL 18 container `denial-postgres` remained operational on port 5432; volume preserved.
- **Migration Head:** Migration head remains stable at `7c89fee8b001` (no schema change needed; all composite keys and relations were established in Phase 2).
- **Scope Limit:** No evidence chunks, embeddings, vector indexes, appeal drafts, or LLM agent runs were created.

**STOP GATE: Phase 5 is fully implemented, verified, and accepted.**
