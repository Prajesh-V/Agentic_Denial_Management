# Agentic Denial Management

**Project title:** Agentic Evidence-Retrieval & Appeal Generation for Insurance Claim Denial Management: A Human-in-the-Loop Approach

**Product principle:** AI investigates. Evidence supports. A human decides.

---

## What the application does
A denial analyst opens a denied claim, sees the payer reason, starts an investigation, reviews which clinical facts were found and where they came from, inspects missing or conflicting evidence, edits an appeal draft, and explicitly approves, requests revision, or rejects it. The application records the entire action trail. It does **not** autonomously submit to an insurer.

---

## Repository Structure

```text
Agentic_Denial_Management/
+-- AGENTS.md                   # Operational guidelines & execution discipline
+-- README.md                   # Project overview and runbook
+-- pyproject.toml              # Python project & dependency configuration
+-- requirements-lock.txt       # Resolved and verified dependency lock
+-- .env.example                # Example configuration template
+-- .env                        # Local ignored configuration
+-- .gitignore                  # Git ignore rules
+-- compose.yaml                # Docker Compose PostgreSQL 18 service
+-- frontend/                   # Next.js 16 App Router (React 19, TypeScript, Tailwind 4)
|   +-- src/app/                # App router pages and layouts
|   +-- package.json            # Frontend dependencies (motion, lucide-react)
+-- backend/                    # FastAPI application & modules
|   +-- app/
|       +-- api/                # API routes and health endpoints
|       +-- core/               # Pydantic Settings & configuration
|       +-- db/                 # Database connection & session factory
|       +-- llm/                # Local Ollama client integration
|       +-- domain/             # Domain entities & types
|       +-- services/           # Business logic & workflows
|       +-- fhir/               # FHIR R4 resource mappings
|       +-- data_factory/       # Deterministic synthetic data generator
|       +-- ingestion/          # Document & note text extraction
|       +-- retrieval/          # Hybrid search (PostgreSQL FTS + FAISS CPU)
|       +-- agent/              # LangGraph investigation workflow
|       +-- audit/              # Immutable audit logging
+-- scripts/                    # Verification & utility scripts
+-- tests/                      # Automated test suite
|   +-- unit/                   # Unit tests (Pytest)
|   +-- integration/            # Integration tests
|   +-- e2e/                    # End-to-end tests
+-- data/                       # Synthetic data foundation
|   +-- raw/                    # Raw templates & config
|   +-- generated/              # Output datasets by namespace
|   +-- manifests/              # Generation manifests & seeds
|   +-- validation/             # Integrity & timeline reports
+-- artifacts/                  # Benchmark & evaluation runs
+-- backups/                    # Local backups
+-- docs/                       # Authoritative project specifications & contracts
    +-- INITIALIZATION_REPORT.md# Full environment verification report
    +-- PRD.md                  # Product requirements document
    +-- ARCHITECTURE.md         # System architecture & data flow
    +-- DATABASE_SPEC.md        # PostgreSQL database & schema specification
    +-- SYNTHETIC_DATA_FACTORY.md# Synthetic data generation factory rules
    +-- DATA_INGESTION.md       # Ingestion & chunking pipeline
    +-- AGENT_WORKFLOW.md       # LangGraph agent investigation flow
    +-- API_SPEC.md             # FastAPI REST endpoints
    +-- FRONTEND_STITCH_SPEC.md # Frontend design tokens & Stitch integration
    +-- PHASES.md               # 16-phase milestone execution plan
    +-- EVALUATION.md           # Retrieval & drafting benchmarks
    +-- SECURITY_AND_SAFETY.md  # Safety, PHI prevention & provenance rules
    +-- PRODUCT_CONTRACT.md     # Phase 1: User roles, lifecycles, denial taxonomy
    +-- ERD.md                  # Phase 1: Full 32-table Mermaid ERD & data dictionary
    +-- SCHEMA_DECISIONS.md     # Phase 1: Architectural storage decisions & constraints
    +-- DATA_CONTRACTS.md       # Phase 1: Pydantic v2 schemas & FHIR R4 definitions
    +-- SYNTHETIC_DATA_FACTORY_DESIGN.md # Phase 1: Factory layout, 12 scenario templates
    +-- INTERFACE_CONTRACTS.md  # Phase 1: REST API, LangGraph state, Stitch screens
    +-- PHASE_1_ACCEPTANCE.md   # Phase 1: Verification audit & stop-gate report
    +-- PHASE_2_ACCEPTANCE.md   # Phase 2: Database foundation verification & acceptance report
    +-- PHASE_2_1_ACCEPTANCE.md # Phase 2.1: Database integrity and security remediation report
```

---

## Phase Execution Progress

| Phase | Description | Status | Reference Artifacts |
|---|---|---|---|
| **Phase 0** | Recovery, Repository Baseline & Environment Audit | **COMPLETED** | `docs/INITIALIZATION_REPORT.md`, `tests/unit/test_health.py` |
| **Phase 1** | Product Contract, ERD and System Interfaces | **COMPLETED** | `docs/PRODUCT_CONTRACT.md`, `docs/ERD.md`, `docs/SCHEMA_DECISIONS.md`, `docs/DATA_CONTRACTS.md`, `docs/SYNTHETIC_DATA_FACTORY_DESIGN.md`, `docs/INTERFACE_CONTRACTS.md`, `docs/PHASE_1_ACCEPTANCE.md` |
| **Phase 2** | Database Foundation (SQLAlchemy 2, Alembic, Migrations) | **COMPLETED** | `docs/PHASE_2_ACCEPTANCE.md`, `backend/alembic/versions/`, `backend/app/db/models/` |
| **Phase 2.1** | Database Integrity & Security Remediation | **COMPLETED** | `docs/PHASE_2_1_ACCEPTANCE.md`, `backend/alembic/versions/6089fee8b997_remediation_integrity_and_security.py` |
| **Phase 3** | Synthetic Data Factory v1: Organizations and Patients | **PENDING AUTHORIZATION** | *Awaiting user approval before proceeding* |

---

## Verified Quickstart

### Prerequisites
- Python 3.12+ (Python 3.14.6 verified)
- Node.js 20+ (Node.js 26.4.0 verified)
- Docker & Docker Compose (Docker 29.7.2 verified)
- Ollama with `qwen3:8b` model installed

### 1. Database
Ensure the `denial-postgres` Docker container is running:
```powershell
docker compose up -d
```
Verify connectivity:
```powershell
docker exec denial-postgres pg_isready -U denial_app -d denial_management
```

### 2. Backend (FastAPI)
Activate the virtual environment and start the development server:
```powershell
.venv\Scripts\activate
uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --reload
```
Interactive API documentation will be available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- Health check: `http://127.0.0.1:8000/api/health/all`

### 3. Frontend (Next.js)
In a separate terminal:
```powershell
cd frontend
npm run dev
```
Open `http://localhost:3000` in your browser.

### 4. Running Tests & Diagnostics
Run the automated test suite:
```powershell
.venv\Scripts\pytest -v
```
Run linter:
```powershell
.venv\Scripts\ruff check .
```
Run API smoke test:
```powershell
.venv\Scripts\python scripts\smoke_test_api.py
```
