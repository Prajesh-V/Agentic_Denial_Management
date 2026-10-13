# Security, Privacy and Safety Boundaries

## 1. Data classification
Default corpus is generated synthetic data. Clearly label the app, datasets, records and exports as synthetic/demo/research. Do not use actual names, real patient IDs, live claims, production credentials or copied patient notes as seeds. Never claim synthetic performance establishes real clinical or business performance.

MIMIC or any other credentialed dataset is a separate future integration. It must not be accessed without the individual's required authorization and must follow current dataset-specific licensing and handling terms. Default behavior is local-only; no external LLM/embedding call may receive restricted content.

## 2. Human boundary
- The system supports investigation and drafting, not autonomous medical decisions.
- It never automatically transmits or files an appeal to a payer.
- Approval applies to a specific appeal version and is performed by a permitted human.
- Export is a controlled action, not the same as submission.
- If evidence is insufficient, contradictory or the model is uncertain, the application must communicate that and allow escalation.

## 3. Authentication and authorization
- Enforce server-side roles and organization/patient scopes on every endpoint and retrieval query.
- Suggested roles: analyst (assigned/authorized claims), reviewer (draft decision), manager (queue/team view), auditor (read audit), data_admin (synthetic generation/index operations).
- No role is allowed to bypass patient scoping through filters, alternate endpoints, vector search or direct evidence IDs.
- Use secure session handling; keep secrets out of source control and browser bundles.
- Apply least privilege to database connections, file export paths and background workers.

## 4. Retrieval isolation
- Apply patient/tenant filters before ranking and before returning any candidate to the LLM.
- Verify patient and source IDs again when validating generated citations and before returning source detail.
- Add automated cross-patient and cross-organization red-team tests for structured, lexical and dense routes.
- Similarity scores are not access-control, evidence sufficiency or clinical truth scores.
- Do not pass the whole corpus into an LLM. Provide only the minimum evidence required for the current task.

## 5. Model safety
- Treat retrieved notes and documents as untrusted data. Prompt injection inside a clinical note must not change system rules, permissions or tool access.
- Use typed output schemas and validate them; reject unknown resource IDs, malformed tool arguments and unauthorized requests.
- LLM output cannot set user identity, retry budget, database predicates, review decisions or export permissions.
- Use a local model by default. Configuration may change models, but any hosted provider requires explicit privacy/security approval, data-handling verification and a separate threat review.
- Store model and prompt versions for reproducibility, not hidden chain-of-thought. Audit observable actions and concise rationales rather than internal private reasoning.

## 6. Audit
Record actor/component, event time, correlation ID, object reference, action, state transition, decision, model/index/config versions and export hash where relevant. Avoid writing entire clinical document text, passwords, tokens or unnecessary sensitive text to ordinary logs. Audit records must be access-controlled and protected from normal user deletion.

## 7. Data generation and destructive operations
- Namespace every dataset build.
- Show target profile/build before generation, overwrite or deletion.
- Never reset the only copy of the current dataset without a backup and explicit confirmation.
- A generator seed is reproducibility metadata, not a security secret.
- Keep synthetic records visibly distinct from any future authorized real-world corpus.

## 8. File/export handling
- Export only approved versions.
- Use allow-listed output directories and safe filenames.
- Prevent path traversal and unsafe HTML/script execution in exports.
- Record checksum, actor, time, appeal version and export format.
- Do not include hidden debugging fields or internal checkpoint IDs in user-facing exports.

## 9. Operational safeguards
- Secret management and `.env.example` with placeholders only.
- TLS in deployed environments, secure cookies, CSRF protection where relevant and request size limits.
- Database backups and restore drills; migrations tested before upgrade.
- Rate limits and timeouts on expensive endpoints.
- Worker cancellation, bounded retries and idempotency for jobs.
- Dependency scanning, lockfiles and reproducible builds.
- Health vs readiness status must be distinguished; a live API with a missing index is degraded, not fully ready.

## 10. Claims we must not make without separate evidence
- “HIPAA compliant” or other certification claims.
- “The system guarantees an appeal will be won.”
- “The AI eliminates hallucinations.”
- “Synthetic denial rates represent actual insurers.”
- “The system is FHIR compliant” beyond the specific resources/operations actually validated.
- “MIMIC supplies real insurance-denial/appeal outcome labels.”
- “All frontend animations are accessible” until reduced-motion and keyboard tests pass.
