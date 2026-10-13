"""Comprehensive automated integration and unit tests for Phase 7 Hybrid Evidence Retrieval."""

import uuid
from datetime import date

import numpy as np
import pytest
from sqlalchemy import func, select

from backend.app.db.models import (
    Claim,
    Coverage,
    DenialEvent,
    EvidenceChunk,
    PayerPlan,
    PayerPolicyVersion,
)
from backend.app.db.session import SessionLocal
from backend.app.ingestion.schemas import EvidentiaryRole
from backend.app.retrieval.embedder import MockEmbeddingService
from backend.app.retrieval.faiss_index import FAISSVectorIndex
from backend.app.retrieval.fusion import ReciprocalRankFusionEngine
from backend.app.retrieval.lexical import PostgresLexicalSearchService
from backend.app.retrieval.schemas import (
    RetrievalChannel,
    RetrievalRequest,
    RetrievalScopeContext,
)
from backend.app.retrieval.scope_filter import RetrievalScopeFilter, ScopeValidationError
from backend.app.retrieval.service import HybridRetrievalService


@pytest.fixture
def db_session():
    """Provides a database session rolled back after test."""
    session = SessionLocal()
    yield session
    session.rollback()
    session.close()


@pytest.fixture
def smoke_claim_context(db_session):
    """Retrieve an authoritative denied claim from the canonical smoke build."""
    claim = db_session.execute(
        select(Claim).join(DenialEvent).order_by(Claim.created_at.asc()).limit(1)
    ).scalars().first()
    assert claim is not None, "Smoke dataset must contain at least one denied claim."

    cov = db_session.execute(
        select(Coverage).where(Coverage.id == claim.coverage_id)
    ).scalars().first()
    plan = db_session.execute(
        select(PayerPlan).where(PayerPlan.id == cov.payer_plan_id)
    ).scalars().first()

    return {
        "claim_id": claim.id,
        "patient_id": claim.patient_id,
        "payer_id": plan.payer_id,
        "service_date": claim.service_start_date,
    }


class TestSemanticEmbeddingAndFAISS:
    """Tests for vector embedding generation, L2 normalization, FAISS indexing, and validation."""

    def test_embedding_dimensions_and_l2_normalization(self):
        embedder = MockEmbeddingService(dimension=384)
        texts = ["Patient presents with severe joint effusion.", "Pre-authorization request for lumbar MRI."]
        vectors = embedder.encode_texts(texts)

        assert vectors.shape == (2, 384)
        for vec in vectors:
            norm = np.linalg.norm(vec)
            assert np.isclose(norm, 1.0, atol=1e-5), f"Expected unit norm 1.0, got {norm}"

    def test_empty_and_whitespace_text_rejection(self):
        embedder = MockEmbeddingService(dimension=384)
        with pytest.raises(ValueError, match="Empty text"):
            embedder.encode_texts(["Valid clinical text", "   ", "Another valid text"])

        with pytest.raises(ValueError, match="Query string cannot be empty"):
            embedder.encode_query("   ")

    def test_faiss_index_mapping_and_inner_product_search(self):
        embedder = MockEmbeddingService(dimension=384)
        cid1 = uuid.uuid4()
        cid2 = uuid.uuid4()
        cid3 = uuid.uuid4()

        texts = [
            "Total knee arthroplasty failure with osteolysis.",
            "Diabetes mellitus clinical review.",
            "Hypertension routine checkup.",
        ]
        vectors = embedder.encode_texts(texts)

        index = FAISSVectorIndex(dimension=384)
        index.add_vectors(vectors, [cid1, cid2, cid3])
        assert index.total_vectors == 3

        query_vec = embedder.encode_query("knee arthroplasty")
        results = index.search(query_vec, top_k=2)

        assert len(results) == 2
        top_cid, top_score, top_rank = results[0]
        assert top_rank == 1
        assert top_cid in (cid1, cid2, cid3)
        assert -1.0 <= top_score <= 1.0

    def test_faiss_atomic_save_load_and_hash_integrity(self, tmp_path):
        embedder = MockEmbeddingService(dimension=384)
        cids = [uuid.uuid4(), uuid.uuid4()]
        vectors = embedder.encode_texts(["Doc 1", "Doc 2"])

        index = FAISSVectorIndex(dimension=384)
        index.add_vectors(vectors, cids)

        index_id = "test_idx_v1"
        corpus_hashes = ["hash1", "hash2"]
        index.save(
            index_dir=tmp_path,
            index_id=index_id,
            dataset_build_id="test_build",
            chunker_version="v1.0",
            corpus_hashes=corpus_hashes,
        )

        assert (tmp_path / f"{index_id}.faiss").exists()
        assert (tmp_path / f"{index_id}_manifest.json").exists()

        # Load back and verify
        loaded_index, loaded_manifest = FAISSVectorIndex.load(tmp_path, index_id)
        assert loaded_index.total_vectors == 2
        assert loaded_manifest.chunk_count == 2
        assert loaded_index.chunk_ids == cids

    def test_stale_index_detection(self, tmp_path, db_session):
        service = HybridRetrievalService(session=db_session, embedder=MockEmbeddingService(384), index_dir=tmp_path)
        # Create an artificial index with outdated manifest
        manifest = service.build_index("synth_smoke_20261013_v1", index_id="test_stale_idx", force=True)

        val_before = service.validate_index("synth_smoke_20261013_v1", index_id="test_stale_idx")
        assert val_before["valid"] is True
        assert val_before["is_stale"] is False

        # Alter the manifest file with a corrupted fingerprint to simulate out-of-sync corpus
        man_path = tmp_path / "test_stale_idx_manifest.json"
        content = man_path.read_text(encoding="utf-8").replace(manifest.corpus_fingerprint, "tampered_fingerprint_123")
        man_path.write_text(content, encoding="utf-8")

        val_after = service.validate_index("synth_smoke_20261013_v1", index_id="test_stale_idx")
        assert val_after["is_stale"] is True
        assert any("Corpus fingerprint mismatch" in err for err in val_after["errors"])


class TestPostgreSQLLexicalRetrieval:
    """Tests for safe parameterized FTS, medical/billing code matching, and SQL injection safety."""

    def test_lexical_search_policy_and_medical_terms(self, db_session, smoke_claim_context):
        lexical = PostgresLexicalSearchService(session=db_session)
        scope = RetrievalScopeContext(
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            payer_id=smoke_claim_context["payer_id"],
        )

        results = lexical.search(query="conservative therapy", scope=scope, top_k=5)
        assert len(results) > 0
        _top_cid, top_score, top_rank = results[0]
        assert top_rank == 1
        assert top_score > 0.0

    def test_lexical_search_codes_and_identifiers(self, db_session, smoke_claim_context):
        lexical = PostgresLexicalSearchService(session=db_session)
        scope = RetrievalScopeContext(
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            payer_id=smoke_claim_context["payer_id"],
        )

        # Search for CARC 50 / N115 denial terms
        results = lexical.search(query="N115 MED_NEC_01", scope=scope, top_k=5)
        assert len(results) > 0

    def test_sql_injection_and_punctuation_safety(self, db_session, smoke_claim_context):
        lexical = PostgresLexicalSearchService(session=db_session)
        scope = RetrievalScopeContext(
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            payer_id=smoke_claim_context["payer_id"],
        )

        malicious_query = "conservative'; DROP TABLE evidence_chunks; -- \" OR 1=1"
        lexical.search(query=malicious_query, scope=scope, top_k=5)
        # Must execute cleanly without exception and preserve table
        count = db_session.execute(select(func.count(EvidenceChunk.id))).scalar()
        assert count > 0


class TestReciprocalRankFusion:
    """Tests for deterministic RRF formula, channel deduplication, and tie-breaking."""

    def test_rrf_scoring_accuracy_and_fusion(self):
        engine = ReciprocalRankFusionEngine(k=60)
        cid1 = uuid.uuid4()
        cid2 = uuid.uuid4()
        cid3 = uuid.uuid4()

        sem_results = [(cid1, 0.9, 1), (cid2, 0.7, 2)]
        lex_results = [(cid2, 0.5, 1), (cid3, 0.3, 2)]

        fused = engine.fuse(sem_results, lex_results, limit=10)

        assert len(fused) == 3
        assert fused[0].chunk_id == cid2
        assert np.isclose(fused[0].fused_score, 1.0 / 62 + 1.0 / 61, atol=1e-4)

        assert fused[1].chunk_id == cid1
        assert np.isclose(fused[1].fused_score, 1.0 / 61, atol=1e-4)

        assert fused[2].chunk_id == cid3
        assert np.isclose(fused[2].fused_score, 1.0 / 62, atol=1e-4)

    def test_deterministic_tie_breaking(self):
        engine = ReciprocalRankFusionEngine(k=60)
        cid_a = uuid.UUID("10000000-0000-0000-0000-000000000000")
        cid_b = uuid.UUID("20000000-0000-0000-0000-000000000000")

        sem_results = [(cid_a, 0.8, 1), (cid_b, 0.8, 1)]
        fused = engine.fuse(sem_results, [], limit=10)

        assert len(fused) == 2
        assert fused[0].chunk_id == cid_a
        assert fused[1].chunk_id == cid_b


class TestSecurityAndEvidentiaryIntegrity:
    """Strict authorization and evidentiary boundaries: patient, tenant, payer, and role isolation."""

    def test_cross_patient_leakage_blocked(self, db_session, smoke_claim_context):
        service = HybridRetrievalService(session=db_session)
        fake_patient_id = uuid.uuid4()

        req = RetrievalRequest(
            query="knee pain conservative therapy",
            claim_id=smoke_claim_context["claim_id"],
            patient_id=fake_patient_id,
            limit=5,
        )

        with pytest.raises(ScopeValidationError, match="Scope contradiction"):
            service.retrieve(req)

    def test_clinical_supporting_evidence_strictly_same_patient(self, db_session, smoke_claim_context):
        service = HybridRetrievalService(session=db_session)
        req = RetrievalRequest(
            query="pain assessment plan",
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            allowed_roles=[EvidentiaryRole.CLINICAL_SUPPORTING],
            limit=5,
        )
        resp = service.retrieve(req)
        for item in resp.results:
            assert item.evidentiary_role == EvidentiaryRole.CLINICAL_SUPPORTING
            assert item.patient_id == smoke_claim_context["patient_id"]

    def test_payer_policy_never_patient_owned(self, db_session, smoke_claim_context):
        service = HybridRetrievalService(session=db_session)
        req = RetrievalRequest(
            query="coverage guidelines prior authorization",
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            allowed_roles=[EvidentiaryRole.PAYER_POLICY],
            limit=5,
        )
        resp = service.retrieve(req)
        for item in resp.results:
            assert item.evidentiary_role == EvidentiaryRole.PAYER_POLICY
            assert item.patient_id is None, "Policy chunk must NEVER be attributed to an individual patient"
            assert item.payer_id == smoke_claim_context["payer_id"]

    def test_denial_context_restricted_to_investigated_claim(self, db_session, smoke_claim_context):
        service = HybridRetrievalService(session=db_session)
        req = RetrievalRequest(
            query="denial reason medical necessity",
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            allowed_roles=[EvidentiaryRole.DENIAL_CONTEXT],
            limit=5,
        )
        resp = service.retrieve(req)
        for item in resp.results:
            assert item.evidentiary_role == EvidentiaryRole.DENIAL_CONTEXT
            assert item.claim_id == smoke_claim_context["claim_id"]
            assert item.patient_id == smoke_claim_context["patient_id"]

    def test_policy_effective_date_enforcement(self, db_session, smoke_claim_context):
        scope_filter = RetrievalScopeFilter(session=db_session)
        policy = db_session.execute(
            select(PayerPolicyVersion).where(PayerPolicyVersion.payer_id == smoke_claim_context["payer_id"]).limit(1)
        ).scalars().first()
        if policy:
            scope = RetrievalScopeContext(
                claim_id=smoke_claim_context["claim_id"],
                patient_id=smoke_claim_context["patient_id"],
                payer_id=smoke_claim_context["payer_id"],
                service_date=date(2000, 1, 1),  # Far in the past
            )
            mock_chunk = EvidenceChunk(
                id=uuid.uuid4(),
                dataset_build_id="synth_smoke_20261013_v1",
                evidentiary_role="PAYER_POLICY",
                patient_id=None,
                payer_id=smoke_claim_context["payer_id"],
                payer_policy_version_id=policy.id,
                source_resource_type="PayerPolicyVersion",
                source_resource_id=policy.id,
                chunk_index=0,
                content="Test policy",
                token_count=2,
                char_count=11,
                text_hash="abc",
                chunker_version="v1.0",
                is_active=True,
            )
            is_valid, reason = scope_filter.validate_chunk_scope(mock_chunk, scope)
            assert is_valid is False
            assert "is after service date" in reason

    def test_inactive_and_superseded_chunks_rejected(self, db_session, smoke_claim_context):
        scope_filter = RetrievalScopeFilter(session=db_session)
        scope = RetrievalScopeContext(
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
        )
        inactive_chunk = EvidenceChunk(
            id=uuid.uuid4(),
            evidentiary_role="CLINICAL_SUPPORTING",
            patient_id=smoke_claim_context["patient_id"],
            source_resource_type="ClinicalDocument",
            source_resource_id=uuid.uuid4(),
            chunk_index=0,
            content="Historical note",
            token_count=2,
            char_count=15,
            text_hash="abc",
            chunker_version="v1.0",
            is_active=False,
        )
        is_valid, reason = scope_filter.validate_chunk_scope(inactive_chunk, scope)
        assert is_valid is False
        assert "inactive or superseded" in reason


class TestEndToEndHybridRetrievalPipeline:
    """Full lifecycle testing on canonical smoke dataset."""

    def test_end_to_end_hybrid_query_stability(self, db_session, smoke_claim_context):
        service = HybridRetrievalService(session=db_session)
        req = RetrievalRequest(
            query="conservative therapy trials",
            claim_id=smoke_claim_context["claim_id"],
            patient_id=smoke_claim_context["patient_id"],
            channel=RetrievalChannel.HYBRID,
            limit=5,
        )

        resp1 = service.retrieve(req)
        resp2 = service.retrieve(req)

        assert resp1.total_candidates == resp2.total_candidates
        assert [r.chunk_id for r in resp1.results] == [r.chunk_id for r in resp2.results]
        assert [r.fused_score for r in resp1.results] == [r.fused_score for r in resp2.results]

    def test_indexing_does_not_mutate_canonical_sources_or_duplicate_chunks(self, db_session):
        count_before = db_session.execute(select(func.count(EvidenceChunk.id))).scalar()
        claims_before = db_session.execute(select(func.count(Claim.id))).scalar()

        service = HybridRetrievalService(session=db_session)
        _manifest = service.build_index("synth_smoke_20261013_v1", force=False)

        count_after = db_session.execute(select(func.count(EvidenceChunk.id))).scalar()
        claims_after = db_session.execute(select(func.count(Claim.id))).scalar()

        assert count_before == count_after, "Index building must never create or alter evidence chunks"
        assert claims_before == claims_after, "Index building must never modify canonical source records"
