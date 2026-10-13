import logging

"""Unified hybrid evidence retrieval service orchestrating embedding, FAISS indexing, lexical FTS, and RRF."""

from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.core.config import get_settings
from backend.app.db.models import EvidenceChunk, IndexBuild
from backend.app.ingestion.schemas import EvidentiaryRole
from backend.app.retrieval.embedder import BaseEmbeddingService, LocalEmbeddingService
from backend.app.retrieval.faiss_index import FAISSVectorIndex
from backend.app.retrieval.fusion import FusedCandidate, ReciprocalRankFusionEngine
from backend.app.retrieval.lexical import PostgresLexicalSearchService
from backend.app.retrieval.schemas import (
    IndexBuildManifest,
    RetrievalChannel,
    RetrievalRequest,
    RetrievalResponse,
    RetrievalResultItem,
    RetrievalScopeContext,
)
from backend.app.retrieval.scope_filter import RetrievalScopeFilter

logger = logging.getLogger(__name__)


class HybridRetrievalService:
    """Production service for evidence corpus indexing, validation, and hybrid retrieval."""

    def __init__(
        self,
        session: Session,
        embedder: BaseEmbeddingService | None = None,
        index_dir: Path | None = None,
    ) -> None:
        self.session = session
        settings = get_settings()
        self.embedder = embedder or LocalEmbeddingService(model_name=settings.EMBEDDING_MODEL_NAME)
        self.index_dir = index_dir or (Path(__file__).resolve().parents[3] / settings.FAISS_INDEX_DIR)
        self.scope_filter = RetrievalScopeFilter(session)
        self.lexical_service = PostgresLexicalSearchService(session)

    def _get_active_chunks_for_build(self, dataset_build_id: str) -> list[EvidenceChunk]:
        """Fetch all active chunks belonging to the dataset build plus shared payer policies."""
        stmt = (
            select(EvidenceChunk)
            .where(
                EvidenceChunk.is_active == True,
                (
                    (EvidenceChunk.dataset_build_id == dataset_build_id)
                    | (EvidenceChunk.evidentiary_role == EvidentiaryRole.PAYER_POLICY.value)
                ),
            )
            .order_by(EvidenceChunk.id.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def build_index(
        self,
        dataset_build_id: str,
        index_id: str | None = None,
        chunker_version: str = "v1.0",
        force: bool = False,
    ) -> IndexBuildManifest:
        """Build a dense FAISS vector index for the target dataset build and shared policies."""
        index_id = index_id or f"idx_bge_small_v1_{dataset_build_id}"
        self.index_dir.mkdir(parents=True, exist_ok=True)

        # Check existing IndexBuild record
        existing = self.session.execute(
            select(IndexBuild).where(IndexBuild.id == index_id)
        ).scalars().first()

        if existing and not force and existing.status == "READY":
            # Verify existing files on disk
            try:
                _loaded_index, manifest = FAISSVectorIndex.load(self.index_dir, index_id)
                return manifest
            except Exception as err:
                logger.debug("Existing index load failed, proceeding to rebuild: %s", err)

        chunks = self._get_active_chunks_for_build(dataset_build_id)
        if not chunks:
            raise ValueError(f"No active evidence chunks found for dataset build '{dataset_build_id}'.")

        texts = [c.content for c in chunks]
        chunk_ids = [c.id for c in chunks]
        corpus_hashes = [c.text_hash for c in chunks]

        # 1. Generate embeddings
        vectors = self.embedder.encode_texts(texts)

        # 2. Build FAISS index
        faiss_index = FAISSVectorIndex(dimension=self.embedder.dimension)
        faiss_index.add_vectors(vectors, chunk_ids)

        # 3. Save atomically to disk
        manifest = faiss_index.save(
            index_dir=self.index_dir,
            index_id=index_id,
            dataset_build_id=dataset_build_id,
            chunker_version=chunker_version,
            corpus_hashes=corpus_hashes,
        )

        # 4. Upsert IndexBuild record in PostgreSQL
        if existing:
            existing.dataset_build_id = dataset_build_id
            existing.embedding_model = manifest.embedding_model
            existing.embedding_dimension = manifest.embedding_dimension
            existing.chunker_version = chunker_version
            existing.chunk_count = manifest.chunk_count
            existing.faiss_index_path = str(self.index_dir / f"{index_id}.faiss")
            existing.faiss_index_hash = manifest.faiss_index_hash
            existing.status = "READY"
            existing.built_at = datetime.now(UTC)
        else:
            new_record = IndexBuild(
                id=index_id,
                dataset_build_id=dataset_build_id,
                embedding_model=manifest.embedding_model,
                embedding_dimension=manifest.embedding_dimension,
                chunker_version=chunker_version,
                chunk_count=manifest.chunk_count,
                faiss_index_path=str(self.index_dir / f"{index_id}.faiss"),
                faiss_index_hash=manifest.faiss_index_hash,
                status="READY",
                built_at=datetime.now(UTC),
            )
            self.session.add(new_record)

        self.session.commit()
        return manifest

    def validate_index(
        self,
        dataset_build_id: str,
        index_id: str | None = None,
    ) -> dict[str, Any]:
        """Validate integrity and freshness of the persisted vector index against live PostgreSQL state."""
        index_id = index_id or f"idx_bge_small_v1_{dataset_build_id}"

        errors: list[str] = []
        try:
            _faiss_index, manifest = FAISSVectorIndex.load(self.index_dir, index_id)
        except Exception as e:
            return {
                "valid": False,
                "is_stale": False,
                "index_id": index_id,
                "errors": [f"Index load error: {e}"],
            }

        chunks = self._get_active_chunks_for_build(dataset_build_id)
        current_chunk_ids = {c.id for c in chunks}
        current_corpus_fingerprint = FAISSVectorIndex.compute_corpus_fingerprint([c.text_hash for c in chunks])

        is_stale = False
        if current_corpus_fingerprint != manifest.corpus_fingerprint:
            is_stale = True
            errors.append(
                f"Corpus fingerprint mismatch (index: {manifest.corpus_fingerprint[:12]}, "
                f"live DB: {current_corpus_fingerprint[:12]})"
            )

        if len(current_chunk_ids) != manifest.chunk_count:
            is_stale = True
            errors.append(f"Active chunk count mismatch (index: {manifest.chunk_count}, live DB: {len(current_chunk_ids)})")

        return {
            "valid": len(errors) == 0,
            "is_stale": is_stale,
            "index_id": index_id,
            "dataset_build_id": dataset_build_id,
            "chunk_count": manifest.chunk_count,
            "embedding_dimension": manifest.embedding_dimension,
            "faiss_index_hash": manifest.faiss_index_hash,
            "errors": errors,
        }

    def retrieve(
        self,
        request: RetrievalRequest,
        dataset_build_id: str = "synth_smoke_20261013_v1",
        index_id: str | None = None,
    ) -> RetrievalResponse:
        """Execute hybrid evidence retrieval respecting authorization and evidentiary scopes."""
        start_time = datetime.now(UTC)

        # 1. Authoritative scope resolution
        base_scope = RetrievalScopeContext(
            claim_id=request.claim_id,
            patient_id=request.patient_id,
            tenant_id=request.tenant_id,
            payer_id=request.payer_id,
            service_date=request.service_date,
            allowed_roles=request.allowed_roles,
        )
        resolved_scope = self.scope_filter.resolve_context(base_scope)

        semantic_candidates: list[tuple[UUID, float, int]] = []
        lexical_candidates: list[tuple[UUID, float, int]] = []

        # 2. Semantic retrieval channel (if requested)
        if request.channel in (RetrievalChannel.HYBRID, RetrievalChannel.SEMANTIC):
            index_id = index_id or f"idx_bge_small_v1_{dataset_build_id}"
            try:
                faiss_index, _manifest = FAISSVectorIndex.load(self.index_dir, index_id)
                query_vec = self.embedder.encode_query(request.query)
                raw_semantic = faiss_index.search(query_vec, top_k=max(request.limit * 4, 40))

                # Filter raw semantic candidates strictly through database scope filter
                raw_ids = [cid for cid, _score, _rank in raw_semantic]
                valid_db_chunks = self.scope_filter.filter_chunks(raw_ids, resolved_scope)

                # Re-rank filtered semantic candidates 1..N
                filtered_rank = 1
                for cid, score, _orig_rank in raw_semantic:
                    if cid in valid_db_chunks:
                        semantic_candidates.append((cid, score, filtered_rank))
                        filtered_rank += 1
            except Exception as e:
                if request.channel == RetrievalChannel.SEMANTIC:
                    raise RuntimeError(f"Semantic retrieval failed: {e}") from e
                # In HYBRID mode, log failure and proceed with lexical-only fallback

        # 3. Lexical retrieval channel (if requested)
        if request.channel in (RetrievalChannel.HYBRID, RetrievalChannel.LEXICAL):
            raw_lexical = self.lexical_service.search(
                query=request.query,
                scope=resolved_scope,
                top_k=max(request.limit * 4, 40),
            )
            lexical_candidates = raw_lexical

        # 4. Fusion or Channel Selection
        fused_candidates: list[FusedCandidate] = []
        rrf_engine = ReciprocalRankFusionEngine(k=request.rrf_k)

        if request.channel == RetrievalChannel.HYBRID:
            fused_candidates = rrf_engine.fuse(
                semantic_results=semantic_candidates,
                lexical_results=lexical_candidates,
                limit=request.limit,
                min_score=request.min_score,
            )
        elif request.channel == RetrievalChannel.SEMANTIC:
            # Wrap semantic directly
            for cid, score, rank in semantic_candidates[:request.limit]:
                fused_candidates.append(
                    FusedCandidate(
                        chunk_id=cid,
                        fused_score=score,
                        fused_rank=rank,
                        semantic_rank=rank,
                        semantic_score=score,
                    )
                )
        elif request.channel == RetrievalChannel.LEXICAL:
            # Wrap lexical directly
            for cid, score, rank in lexical_candidates[:request.limit]:
                fused_candidates.append(
                    FusedCandidate(
                        chunk_id=cid,
                        fused_score=score,
                        fused_rank=rank,
                        lexical_rank=rank,
                        lexical_score=score,
                    )
                )

        # 5. Hydrate final candidate records with full canonical provenance
        final_chunk_ids = [fc.chunk_id for fc in fused_candidates]
        chunks_map = self.scope_filter.filter_chunks(final_chunk_ids, resolved_scope)

        results: list[RetrievalResultItem] = []
        for fc in fused_candidates:
            chunk = chunks_map.get(fc.chunk_id)
            if chunk is None:
                continue

            role = EvidentiaryRole(chunk.evidentiary_role)
            explanation = rrf_engine.generate_explanation(
                candidate=fc,
                role=role,
                source_type=chunk.source_resource_type,
            )

            provenance = {
                "source_resource_type": chunk.source_resource_type,
                "source_resource_id": str(chunk.source_resource_id),
                "encounter_id": str(chunk.encounter_id) if chunk.encounter_id else None,
                "clinical_document_id": str(chunk.clinical_document_id) if chunk.clinical_document_id else None,
                "diagnostic_report_id": str(chunk.diagnostic_report_id) if chunk.diagnostic_report_id else None,
                "observation_id": str(chunk.observation_id) if chunk.observation_id else None,
                "condition_id": str(chunk.condition_id) if chunk.condition_id else None,
                "procedure_id": str(chunk.procedure_id) if chunk.procedure_id else None,
                "payer_policy_version_id": str(chunk.payer_policy_version_id) if chunk.payer_policy_version_id else None,
                "claim_id": str(chunk.claim_id) if chunk.claim_id else None,
                "denial_event_id": str(chunk.denial_event_id) if chunk.denial_event_id else None,
                "text_hash": chunk.text_hash,
            }

            results.append(
                RetrievalResultItem(
                    chunk_id=chunk.id,
                    source_resource_type=chunk.source_resource_type,
                    source_resource_id=chunk.source_resource_id,
                    evidentiary_role=role,
                    chunker_version=chunk.chunker_version,
                    chunk_index=chunk.chunk_index,
                    content=chunk.content,
                    section_name=chunk.section_name,
                    source_text_offset=chunk.source_text_offset,
                    source_text_length=chunk.source_text_length,
                    text_hash=chunk.text_hash,
                    patient_id=chunk.patient_id,
                    payer_id=chunk.payer_id,
                    payer_policy_version_id=chunk.payer_policy_version_id,
                    claim_id=chunk.claim_id,
                    denial_event_id=chunk.denial_event_id,
                    effective_date=chunk.effective_date,
                    semantic_rank=fc.semantic_rank,
                    semantic_score=fc.semantic_score,
                    lexical_rank=fc.lexical_rank,
                    lexical_score=fc.lexical_score,
                    fused_rank=fc.fused_rank,
                    fused_score=fc.fused_score,
                    explanation=explanation,
                    provenance=provenance,
                )
            )

        duration_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000.0

        return RetrievalResponse(
            query=request.query,
            claim_id=resolved_scope.claim_id,
            patient_id=resolved_scope.patient_id,
            channel=request.channel,
            total_candidates=len(results),
            results=results,
            retrieval_metadata={
                "duration_ms": round(duration_ms, 2),
                "semantic_candidates_count": len(semantic_candidates),
                "lexical_candidates_count": len(lexical_candidates),
                "payer_id": str(resolved_scope.payer_id) if resolved_scope.payer_id else None,
                "service_date": str(resolved_scope.service_date) if resolved_scope.service_date else None,
                "dataset_build_id": dataset_build_id,
            },
        )
