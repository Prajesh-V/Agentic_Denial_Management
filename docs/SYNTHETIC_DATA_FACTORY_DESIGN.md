# Synthetic Data Factory Design & Scenario Registry

**Project Title:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management  
**Specification Status:** Phase 1 Design & Specification Contract (Authoritative)  
**System Module:** `backend/app/synthetic/`

---

## 1. Architectural Principles: "One World, One Source of Truth"

The synthetic data factory is a first-class subsystem designed to generate a realistic, cohesive, longitudinal simulation of a healthcare provider and revenue cycle ecosystem. 

### Mandatory Generation Invariants
1. **Single Directed Graph:** The factory creates a canonical domain graph in memory. Every child record references an existing valid parent.
2. **Deterministic Reproducibility:** Re-running the generator with the identical generator version, seed, and profile produces logically identical records, keys, and values.
3. **No Disconnected Datasets:** Clinical notes, FHIR payloads, claim lines, remittance events, and evidence chunks are derived from the exact same domain graph.
4. **Visible Synthetic Watermarking:** Every patient, claim, provider, and document is explicitly flagged with `is_synthetic = True` and uses clearly synthetic identifiers (e.g., `MRN-SYNTH-XXXXXX`).

---

## 2. Factory Layout & Component Architecture

```text
backend/app/synthetic/
├── config.py             # Profile parameters, seed management, generation targets
├── factory.py            # Master orchestration pipeline
├── identities.py         # Synthetic demographics, patient identities, MRNs
├── organizations.py      # Provider systems, facilities, practitioners, payers, plans
├── clinical.py           # Longitudinal encounters, conditions, labs, procedures
├── insurance.py          # Member coverage policies, prior authorizations
├── claims.py             # Medical claims (837), claim lines, fee schedules
├── denials.py            # 835 Remittances, CARC/RARC codes, denial events
├── documents.py          # Clinical narrative note templates (Operative, Progress, H&P)
├── fhir_mapping.py       # Canonical translation to FHIR R4 JSON payloads
├── scenarios/            # Registry of 12 scenario generator templates
│   ├── base.py           # Abstract scenario definition
│   ├── med_necessity.py  # MED_NEC_01 scenario implementation
│   ├── prior_auth.py     # PA_MISS_02 scenario implementation
│   └── ...               # (Remaining 10 scenario modules)
└── validation.py         # Integrity, chronology, math, and zero-leakage test suite
```

---

## 3. Seeded PRNG & Determinism Protocol

To ensure bitwise determinism and prevent cross-generator state pollution:
- The generator accepts a single 64-bit integer `seed` (e.g., `20261013`).
- Subsystem generators initialize isolated Python `random.Random(seed_i)` and NumPy `np.random.default_rng(seed_i)` instances derived from the master seed via SHA-256 key stretching:
  $$	ext{seed}_{	ext{identities}} = 	ext{Hash}(	ext{master\_seed} \parallel 	ext{"identities"})$$
  $$	ext{seed}_{	ext{clinical}} = 	ext{Hash}(	ext{master\_seed} \parallel 	ext{"clinical"})$$
  $$	ext{seed}_{	ext{claims}} = 	ext{Hash}(	ext{master\_seed} \parallel 	ext{"claims"})$$
- Generative text is produced via structured templates populated by deterministic facts, never through unseeded, temperature-sampled external LLM generation during dataset compilation.

---

## 4. Scaled Data Profiles

| Profile Name | Patient Count | Claim Count | Execution Target | Intended Usage |
|---|---|---|---|---|
| **`smoke`** | 25 | 50 – 100 | < 5 seconds | Rapid CI/CD verification and local developer unit tests. |
| **`dev`** | 1,000 | 2,000 – 5,000 | ~ 30 seconds | Full end-to-end development, UI exploration, and join validation. |
| **`research`** | 10,000 | 25,000 – 50,000 | ~ 5 minutes | Retrieval benchmark evaluation, RRF tuning, and agent testing. |
| **`stress`** | 25,000+ | 75,000+ | ~ 20 minutes | Latency testing, index build benchmarks, memory limits. |

---

## 5. Authoritative Denial Scenario Registry (12 Core Templates)

Each scenario defines the clinical preconditions, billing parameters, denial triggers, expected supporting evidence, negative distractors, and expected sufficiency outcomes:

### Scenario 1: Medical Necessity (`MED_NEC_01`)
- **Clinical Preconditions:** Patient has severe osteoarthritis of right knee (`M17.11`). Failed 6 months of conservative therapy (physical therapy, NSAIDs, intra-articular steroid injections).
- **Claim:** Total Knee Arthroplasty (`27447`). Total charge $14,500.
- **Denial:** CARC `CO-50` (These are non-covered services because this is not deemed a medical necessity by the payer).
- **Expected Evidence:** (1) Physical therapy progress notes proving >= 6 weeks compliance; (2) Orthopedic clinic note recording steroid injection dates; (3) Weight-bearing X-ray radiology report showing Kellgren-Lawrence Grade 4 severe joint space narrowing.
- **Distractors:** Prior routine annual wellness visit note, unrelated dermatology consult note.
- **Expected Status:** `SUPPORTED`.

### Scenario 2: Prior Authorization Missing / Invalid (`PA_MISS_02`)
- **Clinical Preconditions:** Patient diagnosed with lumbar disc herniation with radiculopathy (`M51.26`).
- **Claim:** Lumbar spine MRI with and without contrast (`72149`). Total charge $2,200.
- **Denial:** CARC `PR-197` (Precertification/authorization/notification/pre-treatment absent).
- **Expected Evidence:** Authorization reference was granted for non-contrast MRI (`72148`), not contrast-enhanced (`72149`), resulting in code mismatch, OR authorization expired 3 days before procedure.
- **Expected Status:** `PARTIALLY_SUPPORTED` / `MISSING`.

### Scenario 3: Missing or Incomplete Documentation (`DOC_INCOMP_03`)
- **Clinical Preconditions:** Patient underwent laparoscopic cholecystectomy (`47562`).
- **Claim:** Outpatient hospital surgical facility fee + surgeon fee. Total charge $8,900.
- **Denial:** CARC `CO-252` / RARC `N382` (Missing Operative Report).
- **Expected Evidence:** Operative report exists in EHR with surgeon electronic signature, surgical indications, and detailed narrative of gallbladder removal.
- **Expected Status:** `SUPPORTED` (once retrieved, documentation satisfies ADR request).

### Scenario 4: Coding / Documentation Mismatch (`CODE_MISMATCH_04`)
- **Clinical Preconditions:** Patient treated for mild superficial abrasion.
- **Claim:** Billed high-complexity comprehensive laceration repair (`13101`) instead of simple repair (`12001`).
- **Denial:** CARC `CO-16` / RARC `M62` (Diagnosis/procedure code inconsistency).
- **Expected Evidence:** Emergency department physician note describes a simple 1.5 cm superficial wound closed with Dermabond adhesive.
- **Expected Status:** `CONFLICTING` (evidence proves billed code was inappropriate).

### Scenario 5: Duplicate or Bundled Service (`DUP_BUNDLE_05`)
- **Clinical Preconditions:** Colonoscopy performed with biopsy (`45380`) and separate polyp snare excision (`45385`) at distinct anatomical sites.
- **Claim:** Both codes billed without modifier `59` or `XS`.
- **Denial:** CARC `CO-97` (The benefit for this service is included in the payment/allowance for another service/procedure).
- **Expected Evidence:** Endoscopy operative report details distinct polyp at cecum removed by snare and separate suspicious lesion in sigmoid colon biopsied with forceps.
- **Expected Status:** `SUPPORTED` (supports appeal requesting addition of anatomical modifier `XS`).

### Scenario 6: Eligibility / Coverage Timing (`ELIG_TIMING_06`)
- **Clinical Preconditions:** Patient treatment date 2025-11-15.
- **Claim:** Outpatient cardiology consultation (`99204`).
- **Denial:** CARC `PR-27` (Expenses incurred after coverage terminated).
- **Expected Evidence:** Insurance verification logs and payer 271 eligibility transaction response confirming active coverage through 2025-12-31.
- **Expected Status:** `SUPPORTED`.

### Scenario 7: Untimely Filing (`UNTIMELY_07`)
- **Clinical Preconditions:** Service date 2025-03-01. Claim initial transmission date 2025-05-10 (within 90-day window). Payer rejected for untimely filing claiming received in November.
- **Claim:** Outpatient MRI.
- **Denial:** CARC `CO-29` (Time limit for filing has expired).
- **Expected Evidence:** Electronic clearinghouse 999 implementation acknowledgment and 277CA claim acknowledgment timestamped 2025-05-10.
- **Expected Status:** `SUPPORTED`.

### Scenario 8: Non-Covered Service / Policy Exclusion (`NON_COV_08`)
- **Clinical Preconditions:** Patient received experimental biological therapy for off-label oncology indication.
- **Claim:** J-code infusion billing.
- **Denial:** CARC `PR-96` (Non-covered charge(s)).
- **Expected Evidence:** Policy exclusion explicitly excludes drug for this indication; no prior clinical trial exemption exists.
- **Expected Status:** `MISSING` (correctly non-appealable).

### Scenario 9: Units / Modifier Inconsistency (`UNITS_MOD_09`)
- **Clinical Preconditions:** Patient received 4 units of specialized IVIG infusion over 8 hours.
- **Claim:** Billed 40 units due to clerical transposition error.
- **Denial:** CARC `CO-151` (Payment adjusted because the number of units exceeds the maximum allowable).
- **Expected Evidence:** Medication Administration Record (MAR) confirms 4 standard units administered.
- **Expected Status:** `CONFLICTING` (supports clerical rebilling, not full appeal).

### Scenario 10: Coordination of Benefits (COB) (`COB_OTHER_10`)
- **Clinical Preconditions:** Patient has Commercial PPO primary and Medicaid secondary.
- **Claim:** Billed Medicaid without primary EOB attached.
- **Denial:** CARC `PR-22` (This care may be covered by another payer).
- **Expected Evidence:** Commercial PPO 835 remittance detailing paid $450 and member co-pay $50.
- **Expected Status:** `SUPPORTED` (supplies required primary EOB to secondary payer).

### Scenario 11: Insufficient Information / ADR (`INSUF_INFO_11`)
- **Clinical Preconditions:** Complex multi-level spinal fusion.
- **Claim:** Major inpatient surgery claim.
- **Denial:** CARC `CO-252` (Additional documentation required).
- **Expected Evidence:** Full clinical record bundle: pre-op consult, imaging, intraoperative neuromonitoring logs, discharge summary.
- **Expected Status:** `SUPPORTED`.

### Scenario 12: Conflicting Clinical Evidence (`CLIN_CONFLICT_12`)
- **Clinical Preconditions:** Biopsy performed for suspected malignancy.
- **Claim:** Billed surgical excision for malignant neoplasm (`11604`).
- **Denial:** CARC `CO-50` (Medical necessity).
- **Expected Evidence:** Surgeon progress note asserts "highly aggressive malignant melanoma", but surgical pathology report states "completely benign seborrheic keratosis".
- **Expected Status:** `CONFLICTING` (triggers mandatory supervisor escalation).

---

## 6. Patient-Disjoint Partitioning Strategy

To eliminate data leakage between agent training/prompt tuning and benchmark evaluation:
- Partitioning is assigned strictly at the **Patient** level (`patients.split_group`), never by individual claims or encounters.
- All encounters, claims, clinical notes, and denial events for a single patient belong entirely to that patient's assigned split.

### Split Proportions
1. **`train_dev` (60%):** Open for exploratory RRF weight tuning, prompt experimentation, and agent development.
2. **`holdout` (15%):** Intermediate checkpoint testing during development iterations.
3. **`locked_test` (20%):** Immutable benchmark evaluation partition. Labels are locked in `ground_truth_labels` with `is_locked = True`. Strictly prohibited from prompt tuning or automated hyperparameter search.
4. **`adversarial` (5%):** Target edge cases (missing notes, conflicting dates, malformed inputs) to evaluate agent safety and escalation behavior.

---

## 7. Automated Validation Suite & Quality Gates

The factory is accepted only when all automated validation checks pass with zero errors:

1. **Relational Integrity Gate:** Zero orphan foreign keys. Every encounter, condition, claim line, and denial event links to an existing parent.
2. **Chronological Coherence Gate:** Zero temporal violations. (Encounter end $\ge$ start; service date $\le$ submission $\le$ denial $\le$ appeal).
3. **Financial Arithmetic Gate:** All claim line amounts sum exactly to `total_billed_amount`. All remittance lines balance:
   $$	ext{Allowed} + 	ext{Adjustment} = 	ext{Billed}$$
4. **Scenario Conformance Gate:** Every generated denial event precisely instantiates its assigned scenario template and links to an active policy version.
5. **Zero Cross-Patient Leakage Gate:** In automated chunking and retrieval smoke tests, exactly 0.0% of returned evidence chunks originate from a patient other than the target claim patient.
