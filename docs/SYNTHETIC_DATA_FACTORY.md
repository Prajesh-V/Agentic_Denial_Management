# Synthetic Data Factory — Build a Realistic Fictional Healthcare World

## 1. Objective
Create a *linked, high-variety simulation* of a provider/RCM/payer ecosystem, not a folder of disconnected example JSON files. It should feel like records created over time by several systems. All entities are fictional, reproducible and clearly marked as synthetic.

The factory is a first-class subsystem and must be implemented before retrieval tuning or agent evaluation.

## 2. One world, one source of truth
The factory creates a canonical domain graph, then derives:
1. relational PostgreSQL rows;
2. FHIR R4-shaped resource JSON;
3. clinical document text;
4. claim line / denial / remittance / appeal events;
5. expected evidence labels for evaluation;
6. deterministic dataset manifests.

Never generate a patient in one script, a different version of the same patient's facts in a separate FHIR script, and a third inconsistent version inside claim fixtures.

## 3. Generated world model

```text
Provider organizations ── Facilities ── Practitioners
                                      │
Synthetic patients ── Coverage / Payer / Plan / Policy versions
        │                             │
        ├── Encounters ── Conditions / Observations / Procedures / Medications
        │        │
        │        └── Clinical documents / reports / notes
        │
        └── Claims ── Claim lines ── Authorization references
                          │
                          └── Remittance events ── Denial events
                                                     │
                                                     └── Appeal lifecycle + synthetic outcome
```

## 4. Realistic variation dimensions
The generator should vary and connect dimensions rather than simply randomize text:
- provider type, specialty, facility, organization and claim submitter;
- patient age bands and demographic categories appropriate for synthetic data, without using them as real risk labels;
- visit setting, encounter frequency, longitudinal history and care gaps;
- common chronic and acute condition combinations, medications, tests, procedures and notes;
- claim type, number of lines, diagnosis pointers, modifiers/units, billed/allowed/paid/adjusted values;
- payer and plan families, effective policy versions, prior authorization requirements, medical-necessity documentation criteria and timely-filing rules;
- denial category, code family, payer explanation, denied amount, evidence availability and deadline;
- appeal complexity, missing documentation, conflicting note dates, irrelevant distractor records and successful/unsuccessful synthetic adjudication outcomes;
- complete and incomplete histories, no-document cases, multi-encounter histories and repeated claims over time.

The generator may use real public standard codes only when the chosen source and license terms are verified. For policy text, payer names, denial messages and outcomes, use clearly synthetic entities/text unless a public source with an explicit license is approved. Do not imply the distribution of synthetic denial reasons matches any insurer's real denial rate unless calibrated from a lawful, documented dataset.

## 5. Denial scenario templates
Create a versioned registry of scenario templates. Minimum categories:
- medical necessity;
- prior authorization missing/invalid;
- missing or incomplete documentation;
- coding/documentation mismatch;
- duplicate or bundled service;
- eligibility/coverage timing;
- untimely filing;
- non-covered service/policy exclusion;
- units/modifier/claim-line inconsistency;
- coordination-of-benefits/other coverage information;
- insufficient information / payer request;
- conflicting clinical evidence.

Each scenario template defines:
- required input records and preconditions;
- claim/policy/denial relationships;
- evidence requirements and expected evidence sources;
- which resources are relevant, distractors, conflicting or intentionally missing;
- expected result (supported/partial/missing/conflict);
- safe terminal behavior;
- scenario seed and template version.

These are simulated rules for evaluation, not claims about the real decisions of any payer.

## 6. Data profiles
Implement profiles as configuration files, not separate hardcoded generators.

| Profile | Suggested target | Purpose |
|---|---:|---|
| `smoke` | 25 patients, 50–100 claims | Fast developer feedback and CI |
| `dev` | 1,000 patients, a few thousand claims | Full end-to-end development, edge cases and realistic joins |
| `research` | 10,000 patients, tens of thousands of claims, a large clinical resource corpus | Retrieval benchmark and moderate-scale workflow experiments |
| `stress` | Configurable 25,000+ patients and 50,000+ claims, only after research profile validates | Measure generation, DB, index, latency and memory limits |

These are planning targets. Actual counts depend on relations per patient and should be emitted in the manifest; do not promise exact totals before measuring. Developers must be able to generate a small profile quickly without accidentally running the research/stress profile.

## 7. Reproducibility requirements
Every build records:
- generator version and code commit;
- seed (integer/string);
- profile name and fully resolved configuration hash;
- public terminology sources/versions and license notes, if used;
- timestamp, software versions and locale/timezone assumptions;
- counts by entity/resource type;
- validation report and errors/warnings;
- stable source-to-FHIR ID mapping;
- patient-level data-split assignment.

For the same generator version and seed, identity, linkage and facts should reproduce. If some operation cannot be bitwise deterministic (for example a model-generated narrative), do not use it in the core factory; generate controlled text from structured facts or persist the source output and hash.

## 8. Clinical timeline coherence
- Build encounters first, then create facts anchored to those encounters.
- Conditions have onset and optional abatement dates that align with the timeline.
- Procedures and tests have service/effective dates and plausible relation to the encounter.
- Reports refer only to existing observations/procedures/patients.
- Medications have ordered/start/end dates that do not contradict the generated timeline.
- Documents mention only facts that exist in the canonical graph and use consistent dates.
- Claims refer to existing coverage/provider/patient and service records; service dates align with claim lines.
- Denial reason and expected evidence requirements are derived from the scenario template and linked policy version.
- Appeal outcome is a synthetic label produced by the generator and must never be described as an actual payer outcome.

## 9. Quality gates
The factory is accepted only when automated validation checks:
- no orphan foreign keys;
- unique IDs and valid FHIR resource identifiers;
- no encounter, service, denial or appeal chronology contradictions;
- consistent financial arithmetic within defined rounding policy;
- denial code/category/policy/template compatibility;
- expected evidence labels match the known generated ground truth;
- no evidence chunk crosses patient boundaries;
- split sets are patient-disjoint;
- each scenario category is present in requested proportions within documented tolerances;
- no duplicate source records except when a duplicate is intentionally part of a test scenario;
- no actual personal information is used in factory seeds or narrative templates.

Validation outputs JSON and a human-readable summary. The pipeline must fail visibly if critical checks fail.

## 10. Suggested implementation layout

```text
backend/app/synthetic/
  config.py
  factory.py
  identities.py
  organizations.py
  clinical.py
  insurance.py
  claims.py
  denials.py
  documents.py
  fhir_mapping.py
  scenarios/
  validation.py
scripts/
  generate_dataset.py
  validate_dataset.py
  export_dataset_manifest.py
```

Names may be adapted after repository inspection, but responsibilities must remain separated. Each generator accepts a configuration/seed and returns a structured build report. It must not hide all behavior in one giant script.

## 11. Synthea's role
Synthea is an optional source of synthetic clinical records, useful for a comparison corpus or importing more varied generated histories. It does not generate our entire custom payer/claims/denial/appeal workflow. Our factory remains the canonical source for linked claim-denial ground truth. If Synthea is imported, map records through a documented adapter, keep source attribution and version, and never overwrite our handcrafted golden scenarios.
