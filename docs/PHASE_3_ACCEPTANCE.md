# Phase 3 Acceptance Report — Synthetic Data Factory v1 (Organizations & Patients)

**Project:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management  
**Repository:** `C:\dev\Agentic_Denial_Management`  
**Phase:** Phase 3 — Synthetic Data Factory v1: Organizations and Patients  
**Status:** ACCEPTED & GATED  
**Date:** 2026-10-13  
**Alembic Head Revision:** `7c89fee8b001` (Enforce reviewer role on export approval)  
**Generator Version:** `1.0.0`  
**Schema Version:** `2.1`

---

## 1. Executive Summary

Phase 3 establishes the foundation of the **Synthetic Data Factory**, creating a deterministic, reproducible, and verifiable population pipeline for foundational healthcare ecosystem entities:
- **Organizations & Facilities:** Synthetic provider health systems, clinics, surgical centers, and facilities.
- **Practitioners & Users:** Fictional NPI-bearing physicians across surgical and medical specialties, accompanied by system users with assigned roles (`analyst`, `reviewer`, `manager`).
- **Payers & Plans:** Commercial, Medicare Advantage, and Managed Medicaid payers with filing deadlines and tiered health plans (PPO, HMO, EPO).
- **Patient Cohort:** Fictional patient demographics with explicit synthetic identifiers (`MRN-SYNTH-*`), plausible adult ages (18–85), and strict patient-disjoint data partitions (`train_dev` vs `holdout_test`).
- **Insurance Coverages:** Active primary coverage links connecting patients to specific payer plans.
- **Database Integrity Preflight:** Added forward Alembic migration `7c89fee8b001` implementing a strict human reviewer role and active status check for the export approval trigger.

All dataset builds are governed by an immutable manifest (`dataset_builds`) storing seed, profile, generator version, configuration hash (SHA-256), patient counts, and a comprehensive validation report.

---

## 2. Factory Architecture & Module Inventory

The factory is implemented as modular, typed Python packages under `backend/app/data_factory/`:

```
backend/app/data_factory/
├── __init__.py                # Package exports (Pipeline, Profile, Generator version)
├── config.py                  # Profiles (smoke, dev, research, stress), subseed derivation, config hashing
├── pipeline.py                # Transactional orchestrator, dependency-ordered persistence, reset lifecycle
├── validator.py               # 6 automated validation check suites with structured report emission
├── cli.py                     # Command-line interface for generate, validate, and reset operations
└── generators/
    ├── __init__.py
    ├── organizations.py       # Deterministic generator for orgs, facilities, practitioners, payers, plans, users
    ├── identities.py          # Deterministic generator for patients and patient-disjoint partitions
    └── insurance.py           # Deterministic generator for active insurance coverage
scripts/
└── synthetic_factory_cli.py   # Executable CLI entrypoint
```

### Module Responsibilities:
1. `config.py`:
   - Profiles: `smoke` (25 patients), `dev` (1,000 patients), `research` (10,000 patients), `stress` (25,000+ patients).
   - Domain Subseed Derivation: Uses SHA-256 key-stretching on `(master_seed, domain)` so changes in one domain generator do not disrupt random streams in other domains.
   - Canonical Hashing: SHA-256 hash computed over normalized profile parameters and master seed.
2. `generators/organizations.py`:
   - Produces organizations with `TX-SYNTH-*` tax IDs and synthetic NPIs.
   - Attaches facilities with Place of Service (POS) codes (`21`, `22`, `24`, `11`).
   - Generates practitioners with deterministic NPIs, specialties, and credentials.
   - Creates system users with seeded system roles (`analyst`, `reviewer`, `manager`) and default organization memberships.
   - Produces payers with timely filing and appeal filing deadline rules, plus tiered insurance plans.
   - Employs deterministic RFC 4122 UUIDs derived directly from the domain RNG.
3. `generators/identities.py`:
   - Generates patient demographics with `MRN-SYNTH-*` identifiers.
   - Computes deterministic adult birth dates relative to benchmark reference date `2026-01-01`.
   - Enforces an 80/20 `train_dev` vs `holdout_test` partition split based on patient index.
4. `generators/insurance.py`:
   - Generates primary insurance policies with `MEM-SYNTH-*` member IDs and `GRP-SYNTH-*` group numbers.
5. `validator.py`:
   - Executes 6 validation suites: entity counts, foreign key reference integrity, patient-disjoint partitions, synthetic designation compliance, zero real-world PHI/identifiers regex scan, and demographic plausibility.
6. `pipeline.py`:
   - Enforces build isolation and idempotency: prevents accidental re-generation unless `--replace` is specified.
   - Enforces strict foreign-key dependency flush order: Reference Entities → Patients → Coverages → Manifest.
   - Provides safe rollback on validation or transaction failure.
   - Provides clean cascade `reset(build_id)` targeting build-scoped patients and coverages.

---

## 3. Supported Configuration & Determinism Behavior

### Profile Definitions:
| Profile | Orgs | Facilities/Org | Practitioners/Org | Payers | Plans/Payer | Patients | Split Ratio (Train:Holdout) |
|---|---:|---:|---:|---:|---:|---:|---|
| `smoke` | 2 | 2 | 4 | 3 | 2 | 25 | 80% / 20% (20 / 5) |
| `dev` | 5 | 3 | 8 | 6 | 3 | 1,000 | 80% / 20% (800 / 200) |
| `research` | 10 | 4 | 10 | 10 | 4 | 10,000 | 80% / 20% (8,000 / 2,000) |
| `stress` | 15 | 5 | 15 | 12 | 5 | 25,000 | 80% / 20% (20,000 / 5,000) |

### Determinism Verification:
- **Rule 1 (Identical Seed):** Given `seed=20261013` and profile `smoke`, repeated execution generates 100% bit-for-bit identical canonical logical records (IDs, MRNs, names, birth dates, tax IDs, member numbers).
- **Rule 2 (Divergent Seed):** Changing master seed to `99998888` produces divergent patient names, MRNs, and IDs.
- **Rule 3 (Domain Isolation):** Modifying identities generation parameters leaves organizational subseed sequence unaffected.

---

## 4. Preflight Reviewer Role Guard (Migration `7c89fee8b001`)

During preflight inspection, the `fn_enforce_export_approval()` export-trigger was audited. The previous version only verified that *some* approval row existed for the appeal, but did not guarantee:
1. The approving user is a valid, active user.
2. The approving user possesses an authorized human reviewer role (`reviewer`, `senior_specialist`, `manager`, `rcm_manager`).

### Forward Migration Implemented:
- Revision ID: `7c89fee8b001`
- Seeds default system roles: `analyst`, `reviewer`, `manager`, `auditor`, `data_admin`.
- Updates `fn_enforce_export_approval()` to join `appeal_decisions` -> `users` -> `user_roles` and enforce:
  ```sql
  AND ad.decision = 'APPROVE'
  AND u.is_active = TRUE
  AND lower(ur.role_id) IN ('reviewer', 'senior_specialist', 'manager', 'rcm_manager')
  ```
- Migration verified against isolated disposable database and successfully applied to primary database.

---

## 5. Generated Entity Types & Smoke Test Counts

The factory was executed against the primary local PostgreSQL database with the `smoke` profile (`seed=20261013`, `build_id=synth_smoke_20261013_v1`):

```json
{
    "build_id": "synth_smoke_20261013_v1",
    "generator_version": "1.0.0",
    "profile": "smoke",
    "seed": 20261013,
    "configuration_hash": "1d0f6f35c113125c0a52046771e8585387241aa83ec8d295f7545c59b6a195fb",
    "validation_passed": true,
    "actual_counts": {
        "organizations": 2,
        "facilities": 4,
        "practitioners": 8,
        "payers": 3,
        "plans": 6,
        "patients": 25,
        "coverages": 25
    },
    "split_counts": {
        "train_dev": 20,
        "holdout_test": 5,
        "partition_leakage": 0
    }
}
```

---

## 6. Automated Validation Suites & Test Results

The comprehensive test suite contains **30 tests**, all passing:

```
tests/integration/test_alembic_migrations.py::test_alembic_migration_lifecycle PASSED
tests/integration/test_database_schema.py (20 constraint & trigger tests) PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataFactoryDeterminism::test_identical_seed_produces_identical_canonical_data PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataFactoryDeterminism::test_different_seeds_produce_divergent_data PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataValidationRules::test_valid_dataset_passes_all_checks PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataValidationRules::test_cross_organization_leakage_detected PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataValidationRules::test_patient_disjoint_partitions_strict PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataValidationRules::test_zero_phi_leakage_detection PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataPipelineLifecycle::test_invalid_profile_configuration_fails PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataPipelineLifecycle::test_pipeline_generate_and_idempotency PASSED
tests/integration/test_synthetic_factory.py::TestSyntheticDataPipelineLifecycle::test_failed_generation_leaves_no_partial_records PASSED
```

### Static Analysis:
- `ruff check .` passed with 0 errors.

---

## 7. Database Preservation & Cleanup Strategy

1. **Non-Destructive Operations:** Neither the database nor container was dropped or downgraded. Primary database is preserved at Alembic head `7c89fee8b001`.
2. **Build Isolation:** Builds are tagged with `dataset_build_id`. Multiple builds can coexist without colliding.
3. **Safe Reset:** The `pipeline.reset(build_id)` method removes only patients and coverages tied to that specific build ID, plus the build manifest row. It does not delete unreferenced system organizations or other builds.
4. **CLI Support:** Full lifecycle supported via `python scripts/synthetic_factory_cli.py [generate|validate|reset]`.

---

## 8. Known Limitations & Next Scope

### Current Limitations:
- Clinical encounters, diagnoses, medications, and procedure histories are not generated in this phase.
- Claims, claim lines, 835 remittance advice, and denial events are not generated in this phase.
- FHIR R4 JSON serialization and FAISS embedding indexes are intentionally deferred.

### Next Scope (Phase 4):
- **Synthetic Clinical Timelines & FHIR Resource Mapping**: Generating longitudinal clinical encounters, conditions, observations, procedures, and clinical notes anchored strictly to the canonical patient records created in Phase 3.
