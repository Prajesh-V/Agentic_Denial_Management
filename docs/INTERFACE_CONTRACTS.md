# System Interface Contracts & API Specifications

**Project Title:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management  
**Specification Status:** Phase 1 Design & Specification Contract (Authoritative)  
**API Prefix:** `/api/v1`

---

## 1. REST API Specification (FastAPI Application Layer)

All endpoints require authentication, validate payloads via Pydantic v2, return standard error wrappers, and enforce server-side organization and patient scoping.

### 1.1 Error Response Envelope
Every non-2xx response adheres to the standardized envelope:
```json
{
  "error": {
    "code": "PERMISSION_DENIED",
    "message": "User does not have access to patient or organization scope.",
    "correlation_id": "req-98f2b4c1-8412-4e9b-b461-8973b1849a21",
    "details": {
      "required_role": "reviewer",
      "active_role": "analyst"
    }
  }
}
```

### 1.2 Health & Session Endpoints
- `GET /api/v1/health`
  - Response: `{"status": "ok", "timestamp": "2026-10-13T12:00:00Z"}`
- `GET /api/v1/ready`
  - Response: `{"status": "ready", "dependencies": {"database": "connected", "llm": "available", "index": "ready"}}`
- `GET /api/v1/me`
  - Response: Active authenticated user details, assigned roles, and permitted provider organizations.

### 1.3 Claims Queue Endpoints
- `GET /api/v1/claims`
  - Query Params: `page` (int), `limit` (int), `status` (str), `denial_category` (str), `priority` (str), `assigned_to` (UUID), `search` (str), `sort_by` (str).
  - Response: Paginated list of claim summaries matching tenant filters.
- `GET /api/v1/claims/{claim_id}`
  - Response: Comprehensive claim detail including service lines, remittance adjudication records, active denial events, and patient summary.
- `POST /api/v1/claims/{claim_id}/assign`
  - Request: `{"assigned_user_id": "usr-..."}`
  - Response: Updated claim assignment with audit correlation ID.
- `PATCH /api/v1/claims/{claim_id}`
  - Request: Allow-listed status/priority updates with optimistic concurrency version check.

### 1.4 Clinical & Evidence Endpoints
- `GET /api/v1/claims/{claim_id}/clinical-context`
  - Response: Patient-scoped summary of encounters, conditions, procedures, observations, and notes.
- `GET /api/v1/patients/{patient_id}/resources`
  - Response: Paginated list of FHIR R4 resource headers scoped to the patient.
- `GET /api/v1/evidence/{evidence_id}`
  - Response: Full textual content, source row ID, document title, effective date, retrieval method, and rank provenance.

### 1.5 Investigation Endpoints
- `POST /api/v1/claims/{claim_id}/investigations`
  - Request: `{"idempotency_key": "idem-12345", "max_retries": 2}`
  - Response (202 Accepted): `{"run_id": "run-01hm9...", "status": "queued", "status_url": "/api/v1/investigations/run-01hm9..."}`
- `GET /api/v1/investigations/{run_id}`
  - Response: High-level status, progress state, elapsed time, retries used, terminal outcome.
- `GET /api/v1/investigations/{run_id}/trace`
  - Response: Chronological list of graph node steps, tool executions, latencies, and search plans.
- `GET /api/v1/investigations/{run_id}/evidence`
  - Response: Retrieved evidence chunks and evaluated requirements with sufficiency statuses.
- `GET /api/v1/investigations/{run_id}/appeal`
  - Response: Latest appeal draft text, cited chunk IDs, grounding report, and reviewer decision status.
- `POST /api/v1/investigations/{run_id}/cancel`
  - Response: Immediate cancellation acknowledgment.

### 1.6 Human Review & Export Endpoints
- `POST /api/v1/appeals/{appeal_id}/versions`
  - Request: `{"subject_line": "...", "body_text": "...", "citations": [...]}`
  - Response: Created `appeal_draft_versions` record with incremented version number.
- `POST /api/v1/appeals/{appeal_id}/review`
  - Request: `{"draft_version_id": "ver-...", "decision": "APPROVE", "rationale": "All Kellgren Grade 4 criteria satisfied."}`
  - Response: Locked decision record with audit event.
- `POST /api/v1/appeals/{appeal_id}/export`
  - Request: `{"draft_version_id": "ver-...", "export_format": "PDF"}`
  - Response: Export artifact path, SHA-256 hash, and download URL.

---

## 2. LangGraph Investigation State & Node Contracts

The reasoning loop is orchestrated as a stateful, typed LangGraph workflow:

```python
from typing import TypedDict, List, Dict, Optional, Any
from uuid import UUID

class InvestigationState(TypedDict):
    # Identity & Scope
    run_id: str
    claim_id: UUID
    patient_id: UUID
    organization_id: UUID
    denial_event_id: UUID
    
    # Denial Interpretation
    denial_category: str
    denial_reason_text: str
    policy_version_id: Optional[UUID]
    
    # Requirement Planning & Budget
    evidence_requirements: List[Dict[str, Any]]
    current_attempt: int
    max_retries: int
    active_search_plan: List[Dict[str, Any]]
    
    # Evidence & Sufficiency
    retrieved_chunk_ids: List[UUID]
    retrieved_evidence_items: List[Dict[str, Any]]
    requirement_assessments: Dict[str, Dict[str, Any]]
    missing_requirements: List[str]
    conflicting_requirements: List[str]
    
    # Appeal Synthesis & Grounding
    draft_subject: Optional[str]
    draft_body: Optional[str]
    draft_citations: List[Dict[str, Any]]
    grounding_valid: bool
    grounding_errors: List[str]
    
    # Terminal State
    terminal_state: str
    terminal_reason: Optional[str]
```

### Graph Node Contracts
1. **`interpret_denial_node`:** Accepts claim denial text -> Outputs normalized `denial_category` and maps to active `payer_policy_versions`.
2. **`build_requirements_node`:** Accepts category -> Loads deterministic requirement templates specifying required clinical facts.
3. **`plan_retrieval_node`:** Synthesizes structured queries with explicit patient ID filters and date ranges.
4. **`retrieve_evidence_node`:** Calls backend `HybridRetriever` tool -> Injects patient-scoped results into state.
5. **`evaluate_coverage_node`:** Assesses each requirement as `SUPPORTED`, `PARTIALLY_SUPPORTED`, `MISSING`, or `CONFLICTING`.
6. **`replan_node`:** If requirements are `MISSING` and `current_attempt < max_retries`, generates alternate search queries targeting different document sections.
7. **`draft_appeal_node`:** Synthesizes structured appeal narrative, citing solely retrieved `EvidenceChunk` IDs.
8. **`grounding_validation_node`:** Deterministically validates that 100% of cited chunk IDs exist, belong to the active patient, and are present in the current run's evidence list.

---

## 3. Hybrid Retrieval Engine Contract

The retrieval engine combines lexical full-text search with local dense embeddings via Reciprocal Rank Fusion (RRF):

```text
                                 ┌──> PostgreSQL Full-Text Search (TSVector) ──> Lexical Ranked List
Query + Patient Scope Filter ────┤
                                 └──> Local Embeddings + FAISS Flat Index   ──> Dense Ranked List
                                                                                        │
                                                                                        ▼
                                                                     Reciprocal Rank Fusion (RRF)
                                                                                        │
                                                                                        ▼
                                                                  Patient-Scoped EvidenceChunks
```

$$	ext{RRF Score}(d) = w_{	ext{lex}} \cdot rac{1}{k + r_{	ext{lex}}(d)} + w_{	ext{dense}} \cdot rac{1}{k + r_{	ext{dense}}(d)}$$
Where $k = 60$, initial $w_{	ext{lex}} = 0.4$, initial $w_{	ext{dense}} = 0.6$.

---

## 4. Frontend View-Model Contracts & Google Stitch Screen Mapping

The frontend operates under the "Nocturne Clinical Studio" design language:
- Shell: Deep charcoal background (`#0D1117`), graphite surfaces (`#161B22`), subtle borders (`#30363D`).
- Accents: Emerald (`#2EA043`) for supported/approved, Amber (`#D29922`) for review required, Crimson (`#F85149`) for denied/conflicting.
- Typography: Inter for UI controls, JetBrains Mono for Claim IDs, MRNs, and CPT codes.

### 8 Core Screens Mapped to Google Stitch
1. **Command Center (`/dashboard`):** Workload summary, assigned claims count, overdue review deadlines, system readiness indicators.
2. **Claims Queue (`/claims`):** Paginated data table, interactive filter rail (status, denial category, priority), fast keyboard row selection.
3. **Investigation Workspace (`/investigations/[id]`):** Split-pane workbench: claim context (left), agent reasoning trace & requirements (center), retrieved evidence drawer (right).
4. **Evidence Detail (`/evidence/[id]`):** Formatted clinical source document view with cited segment highlighting and provenance breadcrumbs.
5. **Appeals & Review (`/appeals/[id]`):** Side-by-side appeal draft editor, clickable inline citations, version selector, and human decision modal (Approve / Revision / Reject).
6. **Audit Trail (`/audit`):** Forensic activity timeline with actor, action tag, correlation ID, and expandable before/after state diff.
7. **Data Lab (`/admin/data-lab`):** Synthetic dataset generator interface, profile selector, seed configuration, validation results, and index rebuild buttons.
8. **System Status (`/status`):** Real-time health monitors for FastAPI, PostgreSQL container, Ollama local model, and FAISS index files.
