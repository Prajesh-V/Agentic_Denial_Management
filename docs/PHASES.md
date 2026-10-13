# Full Project Phases and Acceptance Gates

## Execution principle
This project is built in dependency order. **Database design and the synthetic data factory come before serious RAG tuning and before claims are made about agent performance.** Frontend design can be explored early, but final frontend integration waits for stable contracts. Do not skip gates to get a pretty demo quickly.

## Phase 0 — Recovery, repository baseline and environment audit
**Goal:** protect surviving work and establish what really exists.
- Inventory source tree, Git state, tests, DB files, retrieval artifacts, local models, Stitch project/screens and current run commands.
- Back up current repository and local data before resetting or regenerating anything.
- Initialize/repair Git only after preserving uncommitted work; create a baseline commit.
- Test current API, claim listing, existing retrievers, schema, seed scripts and UI. Record hardcoded/stubbed paths.
- Pin compatible language/runtime/library versions after inspection.

**Gate:** written audit, backup path, clean baseline commit, smoke-test report, no claimed working component without evidence.

## Phase 1 — Product contract, ERD and system interfaces
**Goal:** agree on the fictional world and the product before mass generation.
- Freeze core users, workflow states, denial categories, evidence requirements and safety boundaries.
- Design ERD and FHIR resource mapping.
- Define dataset profiles, seeds, IDs, event chronology, denial templates and evaluation partitions.
- Freeze API schemas, frontend routes, audit events and job statuses.
- Make Stitch screen plan and visual design tokens.

**Gate:** reviewed ERD, data dictionary, scenario registry, API contract, interface inventory and screen inventory. Do not write the mass generator until model relationships are reviewed.

## Phase 2 — Database foundation
**Goal:** build the durable source of truth.
- Configure PostgreSQL.
- Implement SQLAlchemy 2 models and Alembic migrations.
- Add constraints, foreign keys, numeric money fields, dates, uniqueness, tenant/patient scope columns and measured indexes.
- Add repository/service layer and health checks.
- Create isolated database namespaces for smoke/dev/research/benchmark datasets.

**Gate:** clean database initializes from empty using migrations; rollback/upgrade behavior tested; no manual-only schema.

## Phase 3 — Synthetic Data Factory v1: organizations and patients
**Goal:** create a consistent fictional clinical population.
- Generate organizations, facilities, practitioners, patients and coverage/payer/plan records deterministically.
- Record generator version, seed, profile, counts and configuration hash.
- Build command-line `generate`, `validate` and safe `reset` operations.

**Gate:** same seed/profile reproduces stable logical data; FK and uniqueness checks pass; a smoke profile creates in CI quickly.

## Phase 4 — Synthetic clinical timelines + FHIR resource mapping
**Goal:** generate clinical records that connect coherently.
- Generate encounters and linked conditions, procedures, observations, medication requests, diagnostic reports and documents.
- Produce FHIR R4-shaped resources from canonical records, not a separate independent dataset.
- Validate supported resources against documented FHIR requirements/profiles and capture errors.
- Create synthetic note/report text only from facts in the canonical generated graph.

**Gate:** no orphan resources, patient references resolve, timestamps align, notes do not mention facts missing from the canonical source, mappings and validation reports are reproducible.

## Phase 5 — Synthetic claims, payer policy and denial world
**Goal:** create the linked insurance side, not just clinical records.
- Generate payer plans and versioned synthetic policies with effective dates.
- Generate authorizations, claims, claim lines, code references, remittance/835-inspired records, adjustments and denial events.
- Link each scenario to clinical history, service date, coverage and policy version.
- Generate appeal lifecycle and outcome labels only as synthetic scenario truth.
- Include both valid cases and deliberate edge cases: missing docs, late filing, duplicate line, conflicting dates, no authorization, insufficient evidence and distractors.

**Gate:** financial arithmetic and timelines validate; denial codes/categories are consistent with templates; every denial's patient/claim/policy links resolve. Never claim synthetic rules mirror a specific payer.

## Phase 6 — Dataset quality, gold labels and split isolation
**Goal:** make the data scientifically usable.
- Run integrity, timeline, duplicate, diversity and code-validity checks.
- Create locked gold scenarios with manually reviewed expected evidence/relevance/sufficiency labels.
- Assign train/dev/holdout/test by patient, not by row, to prevent leakage.
- Record distribution summaries and limitations. Do not tune on locked test labels.

**Gate:** validation suite passes; split sets are patient-disjoint; gold case inventory and versioned labels are committed; data-quality report generated.

## Phase 7 — Document ingestion and EvidenceChunk pipeline
**Goal:** turn source records into traceable retrieval units.
- Extract text from synthetic documents and deterministic renderings of structured resources.
- Implement chunking, stable IDs, provenance and text hashes.
- Store chunks and source mapping in PostgreSQL.
- Add resumable batch processing and an index manifest.

**Gate:** every chunk resolves to a same-patient source; rebuild after deleting derived chunk/index artifacts works; no content crosses patient boundaries.

## Phase 8 — Hybrid retrieval engine
**Goal:** make retrieval real before adding agent complexity.
- Implement structured FHIR/domain lookup.
- Implement PostgreSQL lexical search and local embeddings + persistent FAISS dense search.
- Implement weighted RRF; begin with 0.4 lexical / 0.6 dense only as a starting experiment, not an immutable truth.
- Apply patient/org/time/resource filters in backend code before returning results.
- Detect missing/corrupt indexes and report degraded state rather than silently returning no evidence.
- Benchmark top-k and fusion weights on dev only.

**Gate:** retrieval methods return actual evidence; tests prove source provenance, patient isolation and index rebuild; baseline precision/recall/latency measured before tuning.

## Phase 9 — Evaluation harness and deterministic baseline
**Goal:** create trustworthy measurements before an LLM agent can make results look better than they are.
- Evaluate simple structured lookup, lexical-only, dense-only, hybrid retrieval, and a single-pass non-agent baseline.
- Version query sets, labels, configs and outputs.
- Report precision/recall at K, MRR/nDCG where relevant, coverage, latency and subgroup/scenario breakdowns.

**Gate:** repeatable report and locked test protocol; no test-set tuning; failures manually inspected and categorized.

## Phase 10 — LangGraph investigation agent
**Goal:** implement the stateful reasoning loop on top of proven retrieval tools.
- Add typed state and denial interpretation.
- Add requirement templates and plan/retrieve/evaluate/replan conditional flow.
- Add retries with hard-coded server budget and terminal states.
- Add checkpoint/resume and safe cancellation.
- Use fake model tests for control flow and real Ollama integration tests separately.

**Gate:** graph scenario suite passes; no unbounded loops; errors distinct from missing evidence; restart/resume works; wrong-patient retrieval is blocked.

## Phase 11 — Appeal drafting, grounding and human decisions
**Goal:** finish the core product workflow.
- Generate versioned, cited drafts from evidence.
- Validate every citation and patient/run association deterministically.
- Implement review states, revision requests, concurrent version checks, approval and rejection.
- Export only an approved draft and audit each export.

**Gate:** unsupported/unknown citations rejected; human actions are server-authoritative; export gate enforced by tests.

## Phase 12 — Full API, auth, audit and background jobs
**Goal:** harden backend delivery.
- Complete FastAPI v1 contracts, authentication, roles, organization scope and rate/size limits where appropriate.
- Run long generation, ingestion/indexing and investigation tasks through an observable job model/worker when needed.
- Add structured logging/correlation IDs, readiness checks, cancellation, idempotency and retry behavior.
- Ensure the browser cannot directly reach DB, FAISS files or Ollama.

**Gate:** full API contract tests; role/patient boundary tests; startup/shutdown and worker-restart tests; no fake endpoints.

## Phase 13 — Stitch designs and animated frontend implementation
**Goal:** build a distinctive production-quality interface on stable contracts.
- Populate actual Stitch project with verified screens: Command Center, Claims Queue, Investigation Workspace, Evidence Detail, Appeals & Review, Audit Trail, Data Lab, System Status.
- Use the design spec and a deliberate mix of component/template references.
- Implement Next.js + TypeScript + Tailwind + Motion; create a project-owned design system.
- Connect frontend to actual FastAPI endpoints; add error/loading/empty states and reduced-motion support.

**Gate:** screen IDs are retrievable; no frontend fake data in live mode; all primary flows work via actual API; responsive/accessibility/animation QA passes.

## Phase 14 — Integration, security and scale testing
**Goal:** test the complete system as a system.
- Run end-to-end claim → investigation → evidence → draft → review → export.
- Run performance tests at smoke/dev/research profiles and a controlled stress profile.
- Test index corruption/rebuild, model unavailable, database unavailable, worker crash, stale draft, denied permission, wrong patient, malformed output and interrupted graph.
- Run accessibility checks, keyboard-only paths and reduced-motion mode.
- Audit secrets, logs, exports, dependency versions, migration and backup procedures.

**Gate:** release checklist has evidence for every critical control; blockers are fixed or explicitly declared before demo/release.

## Phase 15 — Packaging, operation and research release
**Goal:** make a clean setup reproducible.
- Document local setup for the selected Windows environment.
- Add versioned environment examples, seed commands, migration commands, model pull/check steps and dataset/index build steps.
- Provide one non-destructive smoke command and a documented reset command requiring a target namespace.
- Add backup/restore guide, runbook, limitations and benchmark reproduction instructions.
- Create tagged release and baseline commit.

**Gate:** another developer can clone the repo, follow setup and reproduce the same synthetic benchmark without undocumented manual work.

## Phase sequencing summary
```text
Audit → Contracts/ERD → Database → Factory → Clinical/FHIR data
→ Claims/denials → Validation/gold splits → Chunks/ingestion
→ Hybrid retrieval → Baseline evaluation → LangGraph agent
→ Grounded appeal + human review → API/auth/jobs
→ Stitch + frontend → E2E/security/performance → Release
```

Frontend visual exploration can run alongside data architecture, but implementation and integration must use verified designs and stable API contracts.
