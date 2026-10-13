# Product Requirements Document

## 1. Product statement
Build a full healthcare revenue-cycle workflow application that helps a denial-management specialist investigate an insurance claim denial by collecting patient-scoped clinical evidence, checking evidence coverage against the denial reason, preparing an auditable appeal draft, and obtaining explicit human review.

## 2. The problem in plain language
When an insurer denies a claim, staff often need to find relevant notes, diagnoses, tests, treatment history, authorization records and policy requirements, then explain why a claim should be reconsidered. This is time-consuming and fragmented. The product organizes that investigation; it does not decide a medical truth or guarantee an appeal win.

## 3. Primary users
- **Denial analyst:** investigates assigned claims, reviews evidence and edits drafts.
- **Reviewer / senior specialist:** approves, requests revisions or rejects drafts.
- **RCM manager:** monitors queue, workload, stuck cases and reason trends.
- **Auditor / compliance reviewer:** examines evidence provenance, model/tool actions and human decisions.
- **Data administrator:** generates/validates synthetic datasets, rebuilds indexes and runs benchmarks in non-production environments.

## 4. Core user journey
1. Sign in and view a role-filtered claims queue.
2. Search, filter, sort, assign and open a claim.
3. Inspect service lines, coverage, payer response, denial reason, dates and policy version.
4. Start an investigation; the backend records a run and produces explicit status changes.
5. The agent converts the denial into structured evidence requirements.
6. Retrieval searches only the relevant patient's authorized evidence using structured lookup and hybrid text retrieval.
7. The evaluator labels each requirement supported, partially supported, missing or conflicting, with source references.
8. If needed, a bounded retry revises the search plan. At exhaustion, stop and explain what remains missing.
9. If the configured sufficiency rules permit drafting, create an evidence-grounded appeal draft.
10. A human inspects citations, edits, approves, requests revision or rejects.
11. Export a review-approved document and record the action. Never send it to a payer automatically.

## 5. Functional requirements

### Claims and insurance workflow
- Claims queue with pagination, sorting, search and combined filters.
- Claim header and claim lines with code, units, service date, charge and adjustment/allowed/paid values where applicable.
- Coverage/payer/plan and authorization context.
- Denial events with reason/category, CARC/RARC-like fields, source remittance reference, dates and status lifecycle.
- Assignment, priority, due date and notes with explicit audit history.

### Clinical record and FHIR
- Patient-scoped view of encounters, conditions, procedures, observations, medications, diagnostic reports and clinical documents.
- FHIR R4-compatible resource shapes for the supported subset, with explicit declared scope. Do not call a home-grown subset a fully conformant FHIR server without formal validation.
- Every evidence item resolves to the source resource/document and its patient.

### Investigation and retrieval
- Explicit investigation states and a trace of steps/tool calls.
- Structured evidence requirements per denial category.
- Lexical + dense retrieval, metadata filters, rank fusion and retrieval provenance.
- Evidence assessments include rationale, source IDs, relevant dates and any uncertainty/conflict.
- Bounded retry count controlled by backend code.
- Missing/conflicting evidence is a valid terminal result, not a reason to invent records.

### Draft and human review
- Draft versions are immutable snapshots; edits create a new version.
- Citations are navigable to actual source items.
- Grounding validator rejects unknown evidence IDs and unsupported references.
- Approve, request revision and reject require an authenticated reviewer with permission.
- Export is enabled only for an approved draft, and the export action is auditable.

### Synthetic Data Lab
- Select a dataset profile, seed and generator version.
- Generate a new dataset in a named namespace; do not overwrite active data by default.
- Show generation status, record counts, failed integrity checks and reproducibility metadata.
- Validate timelines, links, FHIR shapes, claim/denial logic, evidence labels and split isolation.
- Rebuild chunks, lexical indexes and vector indexes from canonical source data.

### Audit and operations
- Searchable event trail for claim changes, investigations, retrievals, drafts, human decisions, exports, ingestion and dataset generation.
- Health/readiness checks for database, model endpoint, retrieval index and worker queue.
- Explicit empty, loading, failed, partial and permission-denied states.

## 6. Non-functional requirements
- Patient and organization scoping enforced server-side for every relevant query.
- Database migrations and seeded fixtures are reproducible.
- API contracts are typed and versioned.
- Long-running generation, embedding and investigation jobs do not hold a browser request open indefinitely.
- Search and queue endpoints are paginated; no unbounded response containing all patients/records.
- Accessible keyboard workflow, visible focus, high contrast and reduced-motion support.
- UI animations feel fluid but never obscure critical data or misrepresent actual progress.
- Testable from a clean checkout using documented commands.
- Observability includes structured logs, correlation IDs, timing and failure state without logging sensitive free text unnecessarily.

## 7. Product experience
The frontend should feel as polished and fluid as a modern music application: dark shell, strong hierarchy, persistent navigation, a memorable accent color, rich transitions and responsive controls. It must still behave like professional healthcare operations software: precise tables, explicit provenance, readable detail panels, stable status labels and minimal visual distraction. It is inspired by the general interaction quality of Spotify, not a copied Spotify interface or brand.

## 8. Success criteria
- A clean build can generate a deterministic dataset from a documented seed.
- Data integrity validators pass, with zero orphaned required foreign keys and zero cross-patient evidence leaks in test fixtures.
- A synthetic claim can be investigated end-to-end with an auditable trace.
- Retrieval index can be deleted and rebuilt from canonical database data.
- Evidence labels and citations are evaluated against human-authored ground truth.
- Every draft-changing and approval/rejection action is captured in the audit trail.
- Frontend primary flows pass browser tests with the real API, not browser-side mock claims.
- Performance, quality and error thresholds are measured and documented before claiming production readiness.

## 9. Out of scope unless separately approved
- Real payer connectivity or automatic 835 ingestion from a live clearinghouse.
- Autonomous submission, medical decision making or guaranteed appeal outcomes.
- Production use of real patient information before legal/security review and authorization.
- Claiming the synthetic rules replicate any specific insurer's actual adjudication logic.
- Treating generated narrative text as actual medical advice.
