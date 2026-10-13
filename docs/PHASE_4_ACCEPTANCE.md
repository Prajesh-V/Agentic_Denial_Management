# Phase 4 Acceptance Report — Synthetic Clinical Timelines & FHIR Resource Mapping

**Project:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management  
**Repository:** `C:\dev\Agentic_Denial_Management`  
**Phase:** Phase 4 — Synthetic Clinical Timelines & FHIR Resource Mapping  
**Status:** ACCEPTED & GATED  
**Date:** 2026-10-13  
**Alembic Head Revision:** `7c89fee8b001`  
**Generator Version:** `1.1.0`  
**Schema Version:** `2.1`

---

## 1. Executive Summary

Phase 4 extends the **Synthetic Data Factory** to generate coherent, longitudinal clinical timelines and standardized HL7 FHIR Release 4 (R4) resource representations anchored to the synthetic patient cohort:
- **Encounters:** Ambulatory specialty visits (`AMB`) and inpatient surgical admissions (`IMP`) respecting facility Place of Service (POS) codes and practitioner affiliations.
- **Conditions:** Primary diagnoses and comorbidities coded in ICD-10-CM (`M17.11`, `M48.06`, `I25.10`, `E11.9`, `K63.5`) with onset timestamps preceding or coinciding with encounter periods.
- **Procedures:** Completed interventions coded in AMA CPT (`27447`, `63047`, `93458`, `99214`, `45385`) performed strictly within encounter boundaries.
- **Observations:** Vitals (Heart rate, Blood pressure, BMI, Pain scale) and diagnostic laboratory values (HbA1c, Fasting glucose, Total cholesterol, Creatinine, Hemoglobin) with LOINC codes, numeric quantities, units, and reference ranges.
- **Medication Requests:** Active prescriptions (RxNorm codes, dosage instructions, indications) authored by attending practitioners.
- **Diagnostic Reports:** Radiology and pathology studies (CPT `73562`, `72148`, `78452`, `80053`, `88305`) with structured clinical conclusions.
- **Narrative Clinical Documents:** Rich, mutually consistent clinical consultation notes, operative reports, progress notes, and endoscopy summaries with SHA-256 integrity hashes (`text_hash`) and zero external PHI.
- **FHIR R4 Resources:** Strongly typed, validated JSON representations persisted to `fhir_resources` for all 8 supported resource profiles (`Patient`, `Encounter`, `Condition`, `Procedure`, `Observation`, `MedicationRequest`, `DiagnosticReport`, `DocumentReference`).

All generation is 100% deterministic from the master seed and profile, with no LLM-invented facts during dataset construction.

---

## 2. Factory Architecture & Module Inventory

Phase 4 introduces FHIR serialization and clinical timeline generators while extending existing factory modules:

```
backend/app/
├── fhir/
│   ├── __init__.py                # Package exports (Schemas & Mappers)
│   ├── schemas.py                 # Pydantic v2 models for 8 HL7 FHIR R4 resource types
│   └── mapper.py                  # Deterministic mappers from normalized records to FHIR R4
└── data_factory/
    ├── config.py                  # Generator version 1.1.0, profiles, subseed derivation
    ├── pipeline.py                # Transactional orchestrator, dependency-ordered persistence, cascade reset
    ├── validator.py               # 8 validation suites (counts, FKs, splits, PHI, temporal, FHIR parity)
    └── generators/
        ├── organizations.py       # Reference entities (orgs, facilities, practitioners, payers, plans, users)
        ├── identities.py          # Synthetic patients and patient-disjoint partitions
        ├── insurance.py           # Primary coverage policies
        └── clinical.py            # Clinical timelines (encounters, clinical records, FHIR resources)
scripts/
└── synthetic_factory_cli.py       # CLI interface for generate, validate, reset
```

---

## 3. Timeline Model & Clinical Scenario Registry

Clinical histories are generated from 5 high-fidelity, mutually consistent scenario templates:

1. **Orthopedic Knee (Total Knee Arthroplasty):**
   - Primary: `M17.11` (Right knee osteoarthritis, onset 6 months prior).
   - Encounter 1: Ambulatory consultation (`AMB`), pain scale 8/10, X-ray knee (`73562`) showing bone-on-bone medial narrowing, Meloxicam 15 mg.
   - Encounter 2: Inpatient admission (`IMP`), right Total Knee Arthroplasty (`27447`), pre-op Cefazolin 1g IV (`866417`), recovery vitals, operative report.
2. **Spine (Lumbar Stenosis & Decompression):**
   - Primary: `M48.06` (Lumbar spinal stenosis).
   - Encounter 1: Specialty spine consult (`AMB`), straight-leg raise evaluation, lumbar MRI (`72148`) showing L4-L5 canal stenosis, Gabapentin 300 mg.
   - Encounter 2: Ambulatory surgical visit (`AMB`), lumbar laminectomy decompression (`63047`), Cefazolin prophylaxis, operative decompression note.
3. **Cardiovascular (Coronary Artery Disease & Stenting):**
   - Primary: `I25.10` (Atherosclerotic CAD), Secondary: `I10` (Hypertension).
   - Encounter 1: Cardiology clinic (`AMB`), BP 144/88 mmHg, SPECT myocardial perfusion scan (`78452`) showing LAD ischemia, Atorvastatin 80 mg.
   - Encounter 2: Inpatient catheterization (`IMP`), left heart cath and drug-eluting stent placement (`93458`), Clopidogrel 75 mg (`32968`), procedure note.
4. **Endocrine (Type 2 Diabetes Mellitus & Management):**
   - Primary: `E11.9` (Type 2 diabetes mellitus).
   - Encounter 1: Comprehensive evaluation (`AMB`), HbA1c 8.6% (`4548-4`), Fasting glucose 178 mg/dL (`2345-7`), Metformin 1000 mg BID, clinical evaluation note.
   - Encounter 2: Ambulatory follow-up (`AMB`), repeat POC HbA1c 7.4% (improved), SGLT2-inhibitor Empagliflozin 10 mg (`1544460`), progress note.
5. **Gastroenterology (Colorectal Polyp & Colonoscopy):**
   - Primary: `K63.5` (Colyp of colon), Secondary: `K21.9` (GERD).
   - Encounter 1: Pre-procedure consult (`AMB`), baseline labs, Pantoprazole 40 mg (`312320`), pre-procedure note.
   - Encounter 2: Endoscopy center visit (`AMB`), diagnostic and therapeutic colonoscopy with snare polypectomy (`45385`), surgical pathology report (`88305`) confirming tubular adenoma with clear margins, endoscopy findings note.

---

## 4. HL7 FHIR R4 Mapping & Parity

For every normalized database record, a corresponding FHIR R4 JSON payload is constructed, validated against Pydantic v2 schema rules, and persisted into `fhir_resources`:

| Entity | FHIR Resource | Stable Identifier Pattern | Validation Mapping Rule |
|---|---|---|---|
| `Patient` | `Patient` | `pat-{uuid}` | MRN identifier, official name, gender, birth date. |
| `Encounter` | `Encounter` | `enc-{uuid}` | `status="finished"`, `class` coding (`AMB`/`IMP`), start/end period, patient subject. |
| `Condition` | `Condition` | `cond-{uuid}` | `clinicalStatus="active"`, ICD-10 code/display, onset timestamp, patient & encounter references. |
| `Procedure` | `Procedure` | `proc-{uuid}` | `status="completed"`, CPT code/display, performed timestamp, patient & encounter references. |
| `Observation` | `Observation` | `obs-{uuid}` | `status="final"`, LOINC code/display, effective timestamp, Quantity or string value. |
| `MedicationRequest` | `MedicationRequest` | `med-{uuid}` | `status="active"`, `intent="order"`, RxNorm code/display, authoredOn, dosage instruction. |
| `DiagnosticReport` | `DiagnosticReport` | `diag-{uuid}` | `status="final"`, CPT code, effective timestamp, text conclusion. |
| `ClinicalDocument` | `DocumentReference` | `doc-{uuid}` | `status="current"`, LOINC note type, authored date, text attachment matching document body. |

---

## 5. Generated Entity Counts & Demonstration (Smoke Profile)

The smoke profile (`seed=20261013`, `build_id=synth_smoke_20261013_v1`) was executed against the primary PostgreSQL database:
```powershell
python scripts/synthetic_factory_cli.py generate --profile smoke --seed 20261013 --replace
python scripts/synthetic_factory_cli.py validate --build-id synth_smoke_20261013_v1
```

### Manifest Attributes:
- **Build ID:** `synth_smoke_20261013_v1`
- **Generator Version:** `1.1.0`
- **Seed:** `20261013`
- **Configuration Hash:** `810140d8e3a6db26b1c1bb25bfb5d650485f218dabf1df47f7839042e93f2ceb`
- **Validation Passed:** `True`

### Actual Entity Row Counts in Database:
```
  organizations: 2 (shared reference)
  facilities: 4 (shared reference)
  practitioners: 8 (shared reference)
  payers: 3 (shared reference)
  payer_plans: 6 (shared reference)
  patients: 25
  coverage: 25
  encounters: 50
  conditions: 50
  procedures: 25
  observations: 125
  medication_requests: 50
  diagnostic_reports: 25
  clinical_documents: 50
  fhir_resources: 400
  dataset_builds: 1
```

### FHIR Resource Breakdown (400 Total):
- `Observation`: 125
- `MedicationRequest`: 50
- `ClinicalDocument` (`DocumentReference`): 50
- `Condition`: 50
- `Encounter`: 50
- `Patient`: 25
- `DiagnosticReport`: 25
- `Procedure`: 25

### Evaluation Partition Disjointness:
- `train_dev`: 20 patients (80%)
- `holdout_test`: 5 patients (20%)
- `partition_leakage`: 0

---

## 6. Automated Validation Suites & Test Results

The test suite contains **40 tests**, all passing:
```powershell
pytest -v tests
============================= 40 passed in 3.81s ==============================
```

### Test Coverage Highlights:
1. `test_identical_seed_produces_identical_canonical_data`: Verifies bit-for-bit identical canonical logical records and FHIR payloads across separate runs.
2. `test_different_seeds_produce_divergent_data`: Verifies divergent timestamps, IDs, MRNs, and document hashes across distinct seeds.
3. `test_valid_dataset_passes_all_checks`: Verifies all 8 validation suites pass on the smoke dataset.
4. `test_clinical_temporal_contradiction_detected`: Verifies negative test where `start_time > end_time` triggers validation failure.
5. `test_clinical_cross_patient_leakage_detected`: Verifies negative test where condition references an encounter belonging to a different patient triggers validation failure.
6. `test_document_hash_tampering_detected`: Verifies tampering with document narrative fails validation.
7. `test_patient_disjoint_partitions_strict`: Verifies train and holdout sets have strictly 0 overlapping patient IDs.
8. `test_zero_phi_leakage_in_clinical_documents`: Verifies notes containing simulated SSN patterns fail validation.
9. `test_pipeline_generate_and_cascade_reset`: Verifies cascade deletion of clinical and FHIR records on reset without deleting shared reference entities.
10. `test_failed_generation_leaves_no_partial_records`: Verifies transactional rollback on generation error.
11. Unit & Schema Tests (29 tests): All database schema constraints, Alembic migrations, and API health endpoints passing.

### Static Analysis:
- `ruff check .` passed with 0 errors.

---

## 7. Known Limitations & Next Scope

### Limitations:
- Claims, claim lines, 835 remittance advice, and denial events are not yet generated (Phase 5 scope).
- Retrieval indexing (PostgreSQL FTS, local embeddings, FAISS indexes) is not yet built (Phase 7-8 scope).
- Appeal drafting and agent reasoning loops are deferred to Phases 10-11.

### Next Scope (Phase 5):
- **Synthetic Claims, Payer Policy, and Denial World**: Generating payer policies, prior authorizations, 837 claims, claim lines, 835 remittances, and 12 distinct denial event scenarios anchored to the clinical encounters created in Phase 4.
