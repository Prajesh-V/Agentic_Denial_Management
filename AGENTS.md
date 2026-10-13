# Antigravity Operating Rules — Full Project

## Mission
Build a complete, locally reproducible **Agentic Evidence-Retrieval & Appeal Generation platform for insurance-claim denial management**. This is no longer an MVP brief. It is a phased engineering program whose success depends on a coherent synthetic healthcare-and-claims database, reliable retrieval, a bounded agent workflow, human review, and a premium frontend.

The product promise is: **AI investigates. Evidence supports. A human decides.**

## Read before every phase
1. `README.md`
2. `docs/PRD.md`
3. `docs/ARCHITECTURE.md`
4. `docs/DATABASE_SPEC.md`
5. `docs/SYNTHETIC_DATA_FACTORY.md`
6. `docs/DATA_INGESTION.md`
7. `docs/AGENT_WORKFLOW.md`
8. `docs/API_SPEC.md`
9. `docs/FRONTEND_STITCH_SPEC.md`
10. `docs/PHASES.md`
11. `docs/EVALUATION.md`
12. `docs/SECURITY_AND_SAFETY.md`

These files are the source of truth. When code conflicts with them, do not silently change either side: describe the conflict, propose the smallest correction, and record the approved decision.

## Mandatory execution discipline
- Work in the phase order in `docs/PHASES.md`.
- Before changing code, inspect the repository, current tests, environment and current phase status.
- Create or verify a Git repository and a clean baseline commit before significant changes. Back up uncommitted work first; never reset, force-checkout, or delete data to make a task easier.
- Make small changes, run the relevant tests, inspect outputs, and then commit.
- A phase is not complete because files were written. Its acceptance checks must pass and evidence must be recorded in `docs/PHASES.md` or a linked test report.
- Do not claim a service, Stitch screen, dataset, benchmark, route or integration exists unless it can be retrieved or tested.
- Do not invent metric results, FHIR compliance, clinical validity, HIPAA compliance or payer outcomes.
- Do not build the next phase while a required earlier acceptance gate is failing unless the user explicitly approves a documented exception.

## Data rules
- All generated patients, claims, notes, coverage, payer plans, denials, authorizations, appeals and outcomes are synthetic.
- Generate all linked business and clinical records from a single versioned synthetic-data factory. Do not independently hand-write different copies of the same fact into unrelated files or tables.
- Every generated dataset must record generator version, seed, profile, code-set versions, creation timestamp, row counts and validation report.
- Use deterministic seeds. Re-running the same generator version, seed and profile must reproduce the same logical records.
- Enforce foreign keys, patient/tenant scope, timeline consistency, and known ground-truth labels.
- Keep training/development/holdout partitions patient-disjoint. Never tune on the locked test set.
- Synthetic data must look operationally realistic but must be visibly labelled synthetic. Do not imply it is actual payer or patient data.
- Never download, copy, upload or send credentialed MIMIC data unless access is authorized and the data-handling rules in `docs/SECURITY_AND_SAFETY.md` are followed.

## Backend rules
- PostgreSQL is the intended system of record. Schema changes go through Alembic migrations.
- FastAPI is the public application API. The browser must not connect directly to PostgreSQL, the embedding index, or Ollama.
- Validate all request/response payloads with Pydantic and document API behavior in OpenAPI.
- Keep business rules deterministic where possible. The LLM may propose interpretations, search plans, evidence assessments and draft text; Python code owns permissions, retries, IDs, state transitions, evidence provenance, validation and exports.
- Retrieval must apply patient/tenant filters before results are exposed. Do not rely on an LLM prompt as an access-control boundary.
- Indexes are derived artifacts and must be rebuildable from the canonical database. Never make an unrecoverable FAISS file the only copy of clinical text or metadata.
- Never automatically transmit appeals to a payer. Export is allowed only after explicit human authorization and must be audited.

## Frontend / design rules
- Use Google Stitch before implementing a new screen or materially changing visual design. Keep actual screen IDs/URLs in the project notes when available; never fabricate them.
- The design should feel like a polished, dark, music-product-inspired workspace (Spotify-like in rhythm and motion, not a clone of Spotify). Do not use Spotify logos, product names, icons or copyrighted art.
- Use real backend state. No fake loading progress, fake analytics, random claim data or decorative “agent is thinking” animation that misrepresents the actual workflow.
- Motion should clarify state or provide feedback. Respect `prefers-reduced-motion`, provide focus states, and never let animation prevent immediate reading or operating of clinical evidence.
- Do not blindly copy a whole template. Audit its license and dependencies, take only useful patterns, adapt them to the design system, and document its source.
- No generic generated dashboard, excessive glow, endlessly moving background, unbounded parallax, or animation on every text element merely for spectacle.

## Local model rules
- Use Ollama with a configurable model provider; Qwen3-8B is the initial local candidate, not a hard-coded promise of quality.
- Use local embeddings by default for the synthetic corpus. Do not send clinical records to a hosted embedding/model API by default.
- Model name, base URL, timeout, temperature, max output tokens and structured-output mode must be configurable.
- Tests must use deterministic fake providers where the test is about logic, and separate integration tests for real Ollama.

## Definition of done
A feature is done only when code, test coverage, visible behavior, data provenance, error behavior, accessibility implications and documentation have all been checked. Every major user journey must have success, empty, loading, validation, failure and permission-denied states.
