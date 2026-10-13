import time
import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from backend.app.db.models.identity import Patient
from backend.app.db.models.investigation import EvidenceChunk
from backend.app.ingestion.adapters import (
    BaseSourceAdapter,
    ClinicalDocumentAdapter,
    DenialContextAdapter,
    DiagnosticReportAdapter,
    PayerPolicyAdapter,
    StructuredClinicalAdapter,
)
from backend.app.ingestion.chunker import DeterministicEvidenceChunker
from backend.app.ingestion.schemas import (
    CanonicalSourceType,
    ChunkPayload,
    IngestionManifest,
)
from backend.app.ingestion.validator import EvidenceCorpusValidator


class EvidenceIngestionPipeline:
    """End-to-end evidence corpus ingestion and processing pipeline.
    
    Guarantees deterministic chunking, strict scoping, provenance preservation,
    idempotent re-runs, and atomic transactional commits.
    """

    PROCESSOR_VERSION = "processor_v1_20261013"

    def __init__(self, session: Session) -> None:
        self.session = session
        self.adapters: dict[str, BaseSourceAdapter] = {
            CanonicalSourceType.CLINICAL_DOCUMENT.value: ClinicalDocumentAdapter(),
            CanonicalSourceType.DIAGNOSTIC_REPORT.value: DiagnosticReportAdapter(),
            CanonicalSourceType.OBSERVATION.value: StructuredClinicalAdapter(),
            CanonicalSourceType.PAYER_POLICY_VERSION.value: PayerPolicyAdapter(),
            CanonicalSourceType.DENIAL_EVENT.value: DenialContextAdapter(),
        }

    def ingest(
        self,
        dataset_build_id: str,
        source_types: list[str] | None = None,
        chunker_version: str = "v1.0",
        chunk_size: int = DeterministicEvidenceChunker.DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DeterministicEvidenceChunker.DEFAULT_CHUNK_OVERLAP,
        dry_run: bool = False,
        reprocess: bool = False,
    ) -> IngestionManifest:
        """Executes ingestion for a dataset build."""
        start_time = time.time()
        run_id = f"ingest_{dataset_build_id}_{int(start_time)}"

        manifest = IngestionManifest(
            run_id=run_id,
            dataset_build_id=dataset_build_id,
            processor_version=self.PROCESSOR_VERSION,
            chunker_version=chunker_version,
            started_at=datetime.now(UTC),
        )

        chunker = DeterministicEvidenceChunker(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            version=chunker_version,
        )

        target_adapters = self.adapters
        if source_types:
            target_adapters = {k: v for k, v in self.adapters.items() if k in source_types}

        all_chunks_to_insert: list[ChunkPayload] = []

        try:
            for adapter in target_adapters.values():
                docs = adapter.extract(self.session, dataset_build_id=dataset_build_id)
                manifest.sources_discovered += len(docs)

                for doc in docs:
                    if source_types and doc.source_type.value not in source_types:
                        manifest.sources_skipped += 1
                        continue

                    if not doc.normalized_content:
                        manifest.sources_skipped += 1
                        manifest.rejection_reasons["empty_document"] = (
                            manifest.rejection_reasons.get("empty_document", 0) + 1
                        )
                        continue

                    manifest.sources_processed += 1
                    manifest.by_source_type[doc.source_type.value] = (
                        manifest.by_source_type.get(doc.source_type.value, 0) + 1
                    )
                    manifest.by_evidentiary_role[doc.evidentiary_role.value] = (
                        manifest.by_evidentiary_role.get(doc.evidentiary_role.value, 0) + 1
                    )

                    doc_chunks = chunker.chunk_document(doc)
                    manifest.chunks_generated += len(doc_chunks)
                    all_chunks_to_insert.extend(doc_chunks)

            # Process chunks with idempotency & supersession
            for cp in all_chunks_to_insert:
                existing_active = (
                    self.session.query(EvidenceChunk)
                    .filter_by(
                        source_resource_id=cp.source_id,
                        chunk_index=cp.chunk_index,
                        is_active=True,
                    )
                    .first()
                )

                if existing_active:
                    if (
                        existing_active.chunker_version == cp.chunker_version
                        and existing_active.text_hash == cp.text_hash
                        and not reprocess
                    ):
                        manifest.chunks_skipped_duplicate += 1
                        continue
                    else:
                        # Supersede existing active chunk
                        existing_active.is_active = False
                        manifest.chunks_superseded += 1
                        if not dry_run:
                            self.session.flush()

                # Build new active chunk
                new_chunk = EvidenceChunk(
                    id=uuid.uuid4(),
                    dataset_build_id=cp.dataset_build_id or dataset_build_id,
                    evidentiary_role=cp.evidentiary_role.value,
                    patient_id=cp.patient_id,
                    payer_id=cp.payer_id,
                    payer_policy_version_id=cp.payer_policy_version_id,
                    claim_id=cp.claim_id,
                    denial_event_id=cp.denial_event_id,
                    source_resource_type=cp.source_type.value,
                    source_resource_id=cp.source_id,
                    encounter_id=cp.encounter_id,
                    clinical_document_id=cp.source_id if cp.source_type == CanonicalSourceType.CLINICAL_DOCUMENT else None,
                    diagnostic_report_id=cp.source_id if cp.source_type == CanonicalSourceType.DIAGNOSTIC_REPORT else None,
                    observation_id=cp.source_id if cp.source_type == CanonicalSourceType.OBSERVATION else None,
                    condition_id=cp.source_id if cp.source_type == CanonicalSourceType.CONDITION else None,
                    procedure_id=cp.source_id if cp.source_type == CanonicalSourceType.PROCEDURE else None,
                    section_name=cp.section_name,
                    source_text_offset=cp.source_text_offset,
                    source_text_length=cp.source_text_length,
                    effective_date=cp.effective_date,
                    chunk_index=cp.chunk_index,
                    content=cp.content,
                    token_count=cp.token_count,
                    char_count=cp.char_count,
                    text_hash=cp.text_hash,
                    chunker_version=cp.chunker_version,
                    is_active=True,
                    metadata_=cp.metadata,
                )

                if not dry_run:
                    self.session.add(new_chunk)
                manifest.chunks_persisted += 1

            if not dry_run:
                self.session.flush()

                # Validate persisted chunks before committing
                validator = EvidenceCorpusValidator(self.session)
                val_result = validator.validate_corpus(dataset_build_id=dataset_build_id)
                if not val_result["passed"]:
                    self.session.rollback()
                    manifest.errors = [{"validation_errors": val_result["violations"]}]
                    manifest.validation_passed = False
                    raise ValueError(f"Corpus validation failed with {val_result['violation_count']} violations")

                self.session.commit()
                manifest.validation_passed = True
            else:
                self.session.rollback()
                manifest.validation_passed = True

        except Exception as e:
            self.session.rollback()
            manifest.validation_passed = False
            manifest.errors.append({"error": str(e)})
            raise

        finally:
            end_time = time.time()
            manifest.completed_at = datetime.now(UTC)
            manifest.duration_seconds = round(end_time - start_time, 3)

        return manifest

    def reset_build_chunks(self, dataset_build_id: str) -> int:
        """Safely removes evidence chunks belonging to a dataset build, leaving canonical sources intact."""
        build_patient_ids = [
            p.id for p in self.session.query(Patient.id).filter(Patient.dataset_build_id == dataset_build_id).all()
        ]

        query = self.session.query(EvidenceChunk).filter(
            (EvidenceChunk.dataset_build_id == dataset_build_id)
            | (EvidenceChunk.patient_id.in_(build_patient_ids))
        )
        count = query.count()
        query.delete(synchronize_session=False)
        self.session.commit()
        return count
