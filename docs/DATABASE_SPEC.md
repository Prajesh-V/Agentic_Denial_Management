# Database Specification

## 1. Rule: model the world before generating rows
Do not begin by writing thousands of unrelated JSON files. First agree on a schema and create a single data factory that writes consistent linked records. PostgreSQL is the canonical system of record. Alembic migrations define schema changes; synthetic seeds populate data. Every generated child record must refer to a valid parent.

## 2. Core entities

### Identity and organization
- `organizations`: provider groups, facilities, payers, billing groups and internal customer/tenant boundaries.
- `facilities`: service locations tied to a provider organization.
- `practitioners`: synthetic clinicians and their role/specialty.
- `users`, `roles`, `user_roles`, `organization_memberships`: application access. Synthetic patients are not login users.
- `patients`: synthetic identity, demographic bands and source-system identifier. Use obviously synthetic identifiers.

### Clinical records
- `encounters`: patient, facility, practitioner, type, status, start/end times.
- `conditions`: patient, encounter, code/display, onset/abatement, clinical status.
- `procedures`: patient, encounter, code/display, performed time, status.
- `observations`: patient, encounter, coded measurement, value/unit, effective time, reference range when useful.
- `medication_requests`: patient, encounter, medication code, intent/status, authored date, dosage summary.
- `diagnostic_reports`: patient, encounter, report code/status, effective time, conclusion and linked observations/documents.
- `clinical_documents`: patient, encounter, author, document type, date, plain-text body, source ID, generated provenance.
- `fhir_resources`: resource type, FHIR ID, patient ID, encounter ID where applicable, JSONB payload, FHIR version, profile/validation outcome, source factory IDs.

### Insurance and claims
- `payers`, `payer_plans`, `coverage`: plan/member relationship, effective dates, synthetic policy/member identifiers.
- `service_codes`: code system, code, display, category and provenance/version. Do not scrape or bundle licensed code descriptions without checking license terms.
- `authorizations`: requested/approved services, dates, status, reference number, units and linked patient/coverage/claim where applicable.
- `claims`: internal claim ID, patient, coverage, billing organization, rendering provider, submission/service dates, place of service, total charges, currency, status.
- `claim_lines`: claim, line number, procedure/service code, modifiers, units, charge, diagnosis pointers, service dates and authorization reference.
- `remittances`: synthetic 835-inspired remittance batch metadata, payer, payment date and trace identifiers.
- `remittance_lines`: claim/line reference, paid/allowed/adjustment amounts and reason code references.
- `denial_events`: claim/line, category, reason code(s), payer message, denied amount, received date, appeal deadline, source remittance.
- `payer_policy_versions`: payer/plan, policy key/title, effective dates, synthetic policy text/rules and version metadata.
- `appeals`: claim/denial, status, assigned reviewer and deadline.
- `appeal_draft_versions`: immutable draft body, citation IDs, grounding report, model/prompt versions, author and created time.
- `appeal_decisions`: approve/request revision/reject, reviewer, rationale, timestamp and referenced version.
- `exports`: approved draft, format, file hash/path, actor and time. Export is not payer submission.

### Investigation, retrieval and audit
- `investigation_runs`: run ID, claim/denial, graph thread/checkpoint ID (kept internal), status, start/end, retries, terminal reason and model configuration.
- `retrieval_attempts`: run, attempt number, query plan, applied filters, sources, latency and index version.
- `evidence_chunks`: stable chunk ID, patient, source resource/document, text, temporal bounds, text hash, chunker version, token/character count and active status.
- `evidence_assessments`: run, requirement ID, evidence chunk/resource, status, rationale, conflict flag and scorer/model version.
- `ground_truth_labels`: evaluation case, requirement, expected relevant resources/chunks, expected sufficiency and scenario label. Only the evaluation workflow can edit locked labels.
- `audit_events`: actor/system component, action, object type/ID, timestamp, correlation ID, structured before/after diff where safe and reason.
- `dataset_builds`: generator version, seed, profile, configuration hash, start/end, counts, validation summary and status.
- `index_builds`: corpus/dataset version, embedding model version, chunker version, index files/manifest, row counts and status.

## 3. Required constraints
- Use UUIDs or explicit stable synthetic IDs with a documented mapping strategy. FHIR IDs stay within FHIR ID rules.
- Enforce foreign keys and unique constraints for source identifiers, claim line numbers, version numbers and FHIR `(resource_type, fhir_id)` pairs.
- Use `timestamptz` for event times and store the effective timezone assumptions in generated data metadata.
- Dates must be temporally coherent: encounter cannot end before it starts; service date must align to the claim line; denial occurs after the relevant submission/adjudication event; appeal decision cannot precede appeal creation.
- Use numeric/decimal for currency, never float.
- Version payer-policy content; a denial must reference the policy version used in that synthetic scenario.
- Keep patient scope and organization/tenant scope explicit in relevant rows and indexes.
- Do not hard-delete audit events or approved draft versions through ordinary UI flows.
- Store original synthetic text separately from generated chunks; keep the link back to source.

## 4. Indexes
Add measured indexes for common patterns, including:
- `claims(status, denial_category, service_date)` and queue fields;
- `claims(patient_id, service_date)`;
- `claim_lines(claim_id, line_number)`;
- `denial_events(claim_id, received_at)`;
- `encounters(patient_id, start_time)`;
- resource foreign keys and `(resource_type, fhir_id)`;
- `evidence_chunks(patient_id, source_resource_id)`;
- `investigation_runs(claim_id, created_at)`;
- `audit_events(object_type, object_id, occurred_at)`;
- PostgreSQL full-text index materialization for evidence text after benchmarking.

Do not add dozens of indexes without measuring write cost and query plans.

## 5. FHIR storage strategy
Keep normalized tables for application queries and canonical FHIR JSONB resources for interoperability and exact provenance. They must be created by the same factory/mapping code. They must not drift independently. For each supported FHIR type, document the mapping from domain fields to the FHIR payload, profile/version, required fields and validation tests.

## 6. Database migration and seeding rules
- Every schema change uses Alembic; no manual-only schema changes.
- `seed` is idempotent for a named dataset namespace and seed/profile.
- `reset` requires an explicit target namespace and confirmation; never delete production-like or user-created data silently.
- `validate` is read-only and returns machine-readable failures.
- `rebuild-index` reads canonical records/chunks and regenerates derived indexes.
- Store generator and index manifests inside the database and export them as JSON artifacts for debugging.

## 7. Ownership of state
PostgreSQL holds durable business state. LangGraph checkpoints are workflow-resume data and must not be treated as the only copy of user-facing run information. FAISS is a derived index, not a database of record. Browser local storage may remember safe UI preferences but must not be the source of truth for claims or approvals.
