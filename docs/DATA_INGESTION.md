# Data Ingestion and Evidence-Corpus Pipeline

## 1. Purpose
The ingestion pipeline turns canonical clinical records and documents into a searchable evidence corpus while preserving a path back to the original record. It does not replace the source database.

## 2. Inputs
- Canonical synthetic clinical rows in PostgreSQL.
- FHIR R4-shaped JSON resources derived from those same rows.
- Synthetic notes, diagnostic reports, treatment records, authorization records and policy text.
- Optional external synthetic corpus imports through explicit adapters (for example Synthea), never by silently mixing sources.

## 3. Pipeline

```text
Canonical database + generated FHIR + documents
                    ↓
          Validate source and scope
                    ↓
          Extract usable text/fields
                    ↓
      Normalize / redact synthetic identifiers
                    ↓
            Split into EvidenceChunks
                    ↓
    Store chunk text + provenance in PostgreSQL
                    ↓
             Generate embeddings locally
                    ↓
       Build/update FAISS + lexical materialization
                    ↓
       Run index-integrity and retrieval smoke tests
                    ↓
              Mark index version READY
```

## 4. EvidenceChunk contract
Every chunk should contain at least:
- stable `chunk_id`;
- `dataset_build_id` and source system;
- `patient_id` and organization/tenant scope;
- `resource_type`, `fhir_resource_id` and internal source row/document ID;
- encounter/service/effective date where available;
- document section/source field and chunk order;
- exact chunk text and text hash;
- token/character count;
- chunker version;
- embedding model/version and vector identifier once indexed;
- index build version and current/retired status.

Do not return text alone with no provenance. Do not use a generated summary as if it were the original note. If a summary is added, label it as a derived summary and retain source references.

## 5. Chunking rules
- Keep short structured resources intact when they fit the retrieval context; render a deterministic text representation with resource IDs and dates.
- Split long clinical documents by headings/sections when possible, then by a size limit with overlap if needed.
- Keep dates, section labels and source IDs close to their text.
- Do not merge content from different patients, documents or authorization scopes into one chunk.
- Avoid duplicate overlap causing one source to dominate ranking; record parent document and chunk order.
- Chunking code must be versioned and re-runnable.

## 6. Embedding rules
- Initial candidate: local `BAAI/bge-small-en-v1.5`; evaluate on our domain-specific retrieval set before freezing it.
- Persist model ID/version, dimensions, normalized-vector setting, input text hash and build version.
- Generate embeddings in batches with progress, error capture, resumability and memory limits.
- Never treat an embedding as a decision or evidence sufficiency score; it is a retrieval representation only.
- If the embedding model changes, rebuild the vectors and index into a new version, validate it, and then switch the active pointer.

## 7. Index lifecycle and recovery
- PostgreSQL keeps canonical source rows, chunk text, source metadata and index manifests.
- FAISS files are derived build artifacts and can be deleted and rebuilt.
- A build writes to a new temporary/versioned path; only mark `READY` and switch the active index after validation passes.
- Store file hashes, counts, embedding model, corpus version and creation time.
- On missing/corrupt index: mark retrieval degraded, log the exact cause and offer a rebuild command. Never silently return `[]` and label it “no evidence found.”
- After restore from backup or regenerated data, run `validate_dataset`, regenerate chunks if needed, rebuild embeddings/indexes, and run a smoke-retrieval suite.

## 8. Source adapters
Implement a shared `CorpusIngestor` interface for built-in synthetic data and optional external synthetic sources. Each adapter must produce the same canonical EvidenceChunk input contract but preserve the original source type and ID. MIMIC import, if ever enabled, must be credential-gated, local-only by default, separately namespaced and documented. It is not required for this project's database to work.

## 9. Ingestion command contract
Provide documented commands (actual CLI names may be adjusted consistently):

```text
python scripts/validate_dataset.py --profile smoke
python scripts/ingest_corpus.py --dataset <build-id> --dry-run
python scripts/ingest_corpus.py --dataset <build-id>
python scripts/rebuild_retrieval_index.py --dataset <build-id> --index-version <version>
python scripts/validate_retrieval_index.py --index-version <version>
```

Bulk operations should be resumable and observable. Commands that change data must print their target dataset and require an explicit target/profile; destructive resets require confirmation.
