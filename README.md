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
¦   +-- src/app/                # App router pages and layouts
¦   +-- package.json            # Frontend dependencies (motion, lucide-react)
+-- backend/                    # FastAPI application & modules
¦   +-- app/
¦       +-- api/                # API routes and health endpoints
¦       +-- core/               # Pydantic Settings & configuration
¦       +-- db/                 # Database connection & session factory
¦       +-- llm/                # Local Ollama client integration
¦       +-- domain/             # Domain entities & types
¦       +-- services/           # Business logic & workflows
¦       +-- fhir/               # FHIR R4 resource mappings
¦       +-- data_factory/       # Deterministic synthetic data generator
¦       +-- ingestion/          # Document & note text extraction
¦       +-- retrieval/          # Hybrid search (PostgreSQL FTS + FAISS CPU)
¦       +-- agent/              # LangGraph investigation workflow
¦       +-- audit/              # Immutable audit logging
+-- scripts/                    # Verification & utility scripts
+-- tests/                      # Automated test suite
¦   +-- unit/                   # Unit tests (Pytest)
¦   +-- integration/            # Integration tests
¦   +-- e2e/                    # End-to-end tests
+-- data/                       # Synthetic data foundation
¦   +-- raw/                    # Raw templates & config
¦   +-- generated/              # Output datasets by namespace
¦   +-- manifests/              # Generation manifests & seeds
¦   +-- validation/             # Integrity & timeline reports
+-- artifacts/                  # Benchmark & evaluation runs
+-- backups/                    # Local backups
+-- docs/                       # Authoritative project specifications
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
```

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
