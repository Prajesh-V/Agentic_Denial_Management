# API Specification

## 1. Contract rules
- FastAPI is the single browser-facing API.
- Use `/api/v1` for the versioned application contract; keep a temporary compatibility layer for existing `/api/...` routes only if Phase 0 finds callers that require it.
- Define request/response models in Pydantic v2 and publish OpenAPI.
- Use consistent error bodies with `code`, `message`, `correlation_id` and safe optional `details`.
- All list endpoints paginate. Sorting/filter fields are allow-listed. Never interpolate user input into SQL.
- Every resource endpoint authorizes organization + patient/claim scope server-side.
- Public APIs expose `run_id`, never internal graph thread IDs, database passwords or vector index paths.

## 2. Authentication and authorization
Provide session/token handling appropriate for the chosen deployment. Prefer secure, HttpOnly cookies for browser sessions with CSRF protection where relevant. Seeded development accounts must be synthetic and disabled outside development. Roles: analyst, reviewer, manager, auditor and data_admin. `data_admin` endpoints are disabled in production unless separately authorized.

## 3. API map
The exact schema/fields must be frozen after Phase 0 inspects existing code and Phase 2 agrees on database models. This is the target contract, not a claim that every route already exists.

### Health and session
- `GET /api/v1/health` — basic process health.
- `GET /api/v1/ready` — dependencies readiness (database, retrieval index, model adapter/worker where required).
- `GET /api/v1/me` — current user and permitted organizations/roles.

### Claims queue
- `GET /api/v1/claims` — paginated query; filters include status, denial category, payer, assigned user, priority, date range and text search.
- `GET /api/v1/claims/{claim_id}` — claim, service lines, coverage, denial events, selected policy version and safe linked clinical summary.
- `POST /api/v1/claims/{claim_id}/assign` — assignment change with audit.
- `PATCH /api/v1/claims/{claim_id}` — only allow-listed workflow fields (priority/status/assignee) with version check.

### Clinical / evidence
- `GET /api/v1/claims/{claim_id}/clinical-context` — patient-scoped structured clinical summary.
- `GET /api/v1/patients/{patient_id}/resources` — paginated permitted FHIR resource references; not a way to enumerate other patients.
- `GET /api/v1/evidence/{evidence_id}` — source text, source IDs, dates, patient and retrieval provenance.

### Investigations
- `POST /api/v1/claims/{claim_id}/investigations` — create a run; support idempotency key. Return `run_id`, state and status URL.
- `GET /api/v1/investigations/{run_id}` — status/result summary.
- `GET /api/v1/investigations/{run_id}/trace` — ordered nodes/tool calls/attempt statuses with safe metadata.
- `GET /api/v1/investigations/{run_id}/evidence` — retrieved evidence and assessment.
- `GET /api/v1/investigations/{run_id}/appeal` — latest draft plus versions/grounding result.
- `POST /api/v1/investigations/{run_id}/cancel` — cancel where safe.

### Human review and export
- `POST /api/v1/appeals/{appeal_id}/versions` — create new version from an edit/revision.
- `POST /api/v1/appeals/{appeal_id}/review` — approve, request revision or reject a specific version.
- `POST /api/v1/appeals/{appeal_id}/export` — export approved version only; output file reference/hash and audit ID. This is not payer submission.

### Audit, metrics and data lab
- `GET /api/v1/audit-events` — filters and pagination, gated by auditor/manager role.
- `GET /api/v1/operations/metrics` — backend-observed counts/latency/failures, never fake UI metrics.
- `POST /api/v1/admin/datasets` — queue deterministic synthetic dataset build, restricted to data_admin in development/research.
- `GET /api/v1/admin/datasets/{build_id}` — counts/validation/job status.
- `POST /api/v1/admin/datasets/{build_id}/validate` — run/re-run validations.
- `POST /api/v1/admin/datasets/{build_id}/reindex` — queue index build.
- `GET /api/v1/admin/indexes/{index_build_id}` — build status and manifest.

## 4. Asynchronous jobs
Bulk data generation, corpus ingestion, index rebuilding and a potentially long investigation should return a resource/run ID rather than hold an HTTP request open. The UI should poll or use server-sent events/websocket only if the implementation supports authenticated delivery reliably. Progress is derived from backend events, not a client timer.

## 5. Example investigation response

```json
{
  "run_id": "run_demo_000123",
  "claim_id": "CLM-DEMO-000123",
  "status": "queued",
  "status_url": "/api/v1/investigations/run_demo_000123",
  "created_at": "2026-01-12T10:00:00Z"
}
```

The example is illustrative and synthetic. The actual schema should use the selected ID/time conventions consistently.

## 6. State-transition validation
Reject invalid actions with a typed error: cannot approve a draft that failed grounding validation; cannot approve a stale version if a newer version exists; cannot export an unapproved draft; cannot act on a claim outside the caller's scope. Use optimistic concurrency for editable claims/drafts/reviews.

## 7. Test contract
For each route test valid request, invalid payload, no authentication, insufficient role, wrong organization/patient, not found, duplicate/idempotent request, database failure and normal success. Add browser integration tests against a real local API instance and synthetic database.
