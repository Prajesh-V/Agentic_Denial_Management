# Evaluation and Research Protocol

## 1. Purpose
Measure whether retrieval finds the right evidence and whether the full workflow handles missing/conflicting evidence safely. Never infer real appeal success, clinical correctness or operational savings from synthetic data alone.

## 2. Dataset partitions
- `smoke`: quick CI and developer checks; not a benchmark.
- `train/dev`: create and tune synthetic scenarios/configuration.
- `holdout`: tune/selection checkpoint not used for final repeated parameter search.
- `locked_test`: patient-disjoint, locked, versioned labels for final reported results.
- `adversarial`: targeted malformed and edge cases, reported separately.

Partition by patient so all of one synthetic patient's records/cases remain in one split. If a single patient can appear across organizations, enforce a consistent global split assignment.

## 3. Retrieval metrics
- **Precision@K:** among the top K returned items, proportion judged relevant.
- **Recall@K:** among all known relevant items, proportion retrieved in top K.
- **MRR:** how early the first relevant result appears.
- **nDCG@K:** ranking quality when relevance has more than two levels.
- **Evidence coverage:** requirements for which at least one adequate source was found / all requirements.
- **Patient leakage rate:** proportion of returned evidence from a patient/tenant outside the active case; target is zero.
- **Provenance completeness:** results with valid source identifiers and metadata.
- **Latency:** p50/p95 total and per-stage timings, with warm/cold behavior reported separately.

## 4. Agent and generation metrics
- denial-category accuracy and requirement-set precision/recall;
- evidence sufficiency classification accuracy, including conflict/missing states;
- retry trigger appropriateness and recovery rate (define denominator clearly);
- terminal-state correctness;
- citation validity and citation coverage;
- unsupported-factual-claim rate based on adjudicated draft assertions;
- groundedness review by human raters;
- review-gate reachability (workflow can reach review) is not the same as human approval rate;
- human edit distance/edit rate and review time in a user study, if conducted;
- model calls per run, token/time/memory usage, failure rate and cost where applicable.

## 5. Required baselines
Compare on the same cases and retrieval corpus:
1. structured FHIR/domain lookup only;
2. lexical retrieval only;
3. dense retrieval only;
4. hybrid retrieval without agent retries;
5. single-pass LLM + retrieval;
6. agentic retrieval with bounded replanning;
7. ablation without dense retrieval, without lexical retrieval, and without replanning.

This separates improvements from simply using a different dataset or more LLM calls.

## 6. Ground-truth design
Every locked case specifies:
- claim/denial facts;
- versioned denial requirement template;
- expected relevant resources/chunks;
- optional irrelevant distractors and conflicting sources;
- expected status per requirement;
- expected terminal outcome (draft allowed or insufficient/needs review);
- synthetic scenario template version and reviewer provenance.

Gold labels must be manually reviewed against canonical source records. If labels were automatically derived, say so and do not treat them as independent ground truth.

## 7. Reproducibility
Each run stores code commit, dataset build ID, generator version/seed/profile, split version, index build, embedding model, chunker version, retrieval weights/top-k, model tag, prompt/schema version, inference settings, hardware/runtime details, start/end and metric script version. Preserve raw per-case outputs and failure classifications.

## 8. Reporting rules
- Always report denominator and sample size.
- Label all synthetic-only findings as synthetic-only.
- Include confidence intervals or uncertainty where sample size supports them; otherwise say sample is too small.
- Do not compare metrics from incompatible datasets/splits/index versions.
- Don't call a valid citation “correct evidence” automatically; validity is an existence/scope check, while relevance and factual support need separate measures.
- Do not state a benchmark number from a previous implementation as current until rerun against the current code and data.

## 9. Failure analysis
Classify errors as data generation error, missing ground truth, extraction/chunking error, lexical miss, semantic miss, ranking/fusion miss, wrong scope, stale index, interpretation error, requirement error, sufficiency error, draft grounding error, model/service error, UI/API integration error or human workflow error. Every tuning iteration should address a known failure class rather than blindly changing RRF weights.

## 10. Release gates
A release does not pass because average recall is high. It must also pass safety tests for patient leakage, invalid citations, approval bypass, export bypass, stale draft approval, index unavailable behavior, model unavailable behavior, role permissions and audit completeness.
