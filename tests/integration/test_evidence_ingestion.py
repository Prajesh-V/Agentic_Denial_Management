import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.db.models.billing import (
    Claim,
    Coverage,
    Payer,
    PayerPlan,
    PayerPolicyVersion,
)
from backend.app.db.models.clinical import (
    ClinicalDocument,
    Encounter,
)
from backend.app.db.models.identity import (
    Facility,
    Organization,
    Patient,
    Practitioner,
)
from backend.app.db.models.investigation import EvidenceChunk
from backend.app.db.session import SessionLocal
from backend.app.ingestion.chunker import DeterministicEvidenceChunker
from backend.app.ingestion.normalizer import SafeTextNormalizer
from backend.app.ingestion.pipeline import EvidenceIngestionPipeline
from backend.app.ingestion.schemas import (
    CanonicalDocument,
    CanonicalSourceType,
    EvidentiaryRole,
)


@pytest.fixture
def db_session():
    """Provides a transactional database session rolled back after test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def create_base_test_entities(db):
    """Creates isolated entities for unit/integration tests."""
    uid = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Ingest Test Org {uid}",
        type="HOSPITAL_SYSTEM",
        tax_id=f"TX-{uid}",
        npi=f"1{uid[:9]}",
    )
    db.add(org)
    db.flush()

    fac = Facility(
        organization_id=org.id,
        name=f"Test Clinic {uid}",
        pos_code="11",
        address={"city": "Metro", "state": "CA"},
    )
    db.add(fac)

    prac = Practitioner(
        organization_id=org.id,
        npi=f"2{uid[:9]}",
        first_name="Doctor",
        last_name=f"Test-{uid}",
        specialty="Orthopedics",
        credentials="MD",
    )
    db.add(prac)

    pat = Patient(
        organization_id=org.id,
        dataset_build_id=f"test_ingest_{uid}",
        synthetic_mrn=f"MRN-INGEST-{uid}",
        first_name="Jane",
        last_name=f"Doe-{uid}",
        gender="female",
        birth_date=date(1985, 5, 20),
        split_group="train_dev",
        is_synthetic=True,
    )
    db.add(pat)
    db.flush()

    enc = Encounter(
        patient_id=pat.id,
        facility_id=fac.id,
        practitioner_id=prac.id,
        encounter_class="ambulatory",
        status="finished",
        start_time=datetime.now(UTC),
        end_time=datetime.now(UTC),
    )
    db.add(enc)

    payer = Payer(
        payer_identifier=f"PAYER_{uid}",
        name=f"Test Blue Payer {uid}",
        line_of_business="COMMERCIAL",
        timely_filing_days=90,
        appeal_filing_days=180,
    )
    db.add(payer)
    db.flush()

    plan = PayerPlan(
        payer_id=payer.id,
        plan_name=f"Standard PPO {uid}",
        plan_type="PPO",
    )
    db.add(plan)
    db.flush()

    cov = Coverage(
        patient_id=pat.id,
        payer_plan_id=plan.id,
        member_id=f"MEM-{uid}",
        group_number=f"GRP-{uid}",
        status="active",
        start_date=date(2025, 1, 1),
    )
    db.add(cov)
    db.flush()

    claim = Claim(
        claim_number=f"CLM-{uid}",
        patient_id=pat.id,
        organization_id=org.id,
        coverage_id=cov.id,
        rendering_practitioner_id=prac.id,
        facility_id=fac.id,
        status="DENIED",
        priority="NORMAL",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=datetime.now(UTC),
        total_billed_amount=Decimal("1500.00"),
        currency="USD",
    )
    db.add(claim)
    db.flush()

    return {
        "org": org,
        "fac": fac,
        "prac": prac,
        "pat": pat,
        "enc": enc,
        "payer": payer,
        "plan": plan,
        "cov": cov,
        "claim": claim,
        "build_id": pat.dataset_build_id,
    }


class TestEvidenceCorpusIngestion:
    """Test suite for Phase 6 Evidence Corpus Ingestion & Document Processing."""

    def test_ingest_all_supported_source_categories(self, db_session):
        """1. Ingestion of every supported source category."""
        pipeline = EvidenceIngestionPipeline(db_session)
        manifest = pipeline.ingest(
            dataset_build_id="synth_smoke_20261013_v1",
            dry_run=True,
        )
        assert manifest.validation_passed is True
        assert manifest.sources_discovered > 0
        assert manifest.chunks_generated > 0

        # Verify all 7 source types are discovered and processed
        expected_types = {
            "ClinicalDocument",
            "DiagnosticReport",
            "Observation",
            "Condition",
            "Procedure",
            "PayerPolicyVersion",
            "DenialEvent",
        }
        found_types = set(manifest.by_source_type.keys())
        assert expected_types.issubset(found_types), f"Missing source types: {expected_types - found_types}"

        # Verify all 3 evidentiary roles are represented
        expected_roles = {"CLINICAL_SUPPORTING", "PAYER_POLICY", "DENIAL_CONTEXT"}
        found_roles = set(manifest.by_evidentiary_role.keys())
        assert expected_roles.issubset(found_roles), f"Missing roles: {expected_roles - found_roles}"

    def test_deterministic_chunking_and_hashing(self):
        """2. Stable output for identical canonical source content and configuration."""
        raw_text = (
            "CHIEF COMPLAINT: Right knee severe osteoarthritic pain.\n\n"
            "HISTORY OF PRESENT ILLNESS: Patient reports pain refractory to physical therapy for 4 months.\n\n"
            "ASSESSMENT AND PLAN: Advanced medial joint space narrowing. Recommend surgical consultation."
        )
        norm_1, hash_1 = SafeTextNormalizer.normalize(raw_text)
        norm_2, hash_2 = SafeTextNormalizer.normalize(raw_text)
        assert norm_1 == norm_2
        assert hash_1 == hash_2

        doc_id = uuid.uuid4()
        pat_id = uuid.uuid4()
        doc = CanonicalDocument(
            source_id=doc_id,
            source_type=CanonicalSourceType.CLINICAL_DOCUMENT,
            evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
            patient_id=pat_id,
            raw_content=raw_text,
            normalized_content=norm_1,
            content_hash=hash_1,
            effective_date=date(2025, 3, 1),
        )

        chunker = DeterministicEvidenceChunker(chunk_size=300, chunk_overlap=50, version="v1.0")
        chunks_1 = chunker.chunk_document(doc)
        chunks_2 = chunker.chunk_document(doc)

        assert len(chunks_1) == len(chunks_2)
        for c1, c2 in zip(chunks_1, chunks_2, strict=True):
            assert c1.content == c2.content
            assert c1.text_hash == c2.text_hash
            assert c1.chunk_index == c2.chunk_index
            assert c1.token_count == c2.token_count
            assert c1.char_count == c2.char_count
            assert c1.source_text_offset == c2.source_text_offset

    def test_content_hash_sensitivity(self):
        """3. Different content hashes for changed content."""
        text_a = "Patient underwent right knee arthroscopy."
        text_b = "Patient underwent left knee arthroscopy."
        _, hash_a = SafeTextNormalizer.normalize(text_a)
        _, hash_b = SafeTextNormalizer.normalize(text_b)
        assert hash_a != hash_b

    def test_idempotent_repeat_ingestion(self, db_session):
        """4. Idempotent repeat ingestion without duplicate chunks."""
        e = create_base_test_entities(db_session)
        doc = ClinicalDocument(
            patient_id=e["pat"].id,
            encounter_id=e["enc"].id,
            practitioner_id=e["prac"].id,
            document_type="CONSULTATION",
            title="Idempotency Test Doc",
            body_text="CHIEF COMPLAINT: Test complaint.\n\nASSESSMENT: Patient stable.",
            authored_at=datetime.now(UTC),
            text_hash="hash_idemp_1",
        )
        db_session.add(doc)
        db_session.commit()

        pipeline = EvidenceIngestionPipeline(db_session)

        # First ingestion run
        m1 = pipeline.ingest(dataset_build_id=e["build_id"], source_types=["ClinicalDocument"])
        assert m1.chunks_persisted >= 1
        assert m1.chunks_skipped_duplicate == 0

        # Second ingestion run (identical configuration)
        m2 = pipeline.ingest(dataset_build_id=e["build_id"], source_types=["ClinicalDocument"])
        assert m2.chunks_persisted == 0
        assert m2.chunks_skipped_duplicate == m1.chunks_persisted

        # Cleanup
        pipeline.reset_build_chunks(e["build_id"])

    def test_versioning_and_supersession_on_reprocess(self, db_session):
        """5. Clear versioning behavior after chunker changes."""
        e = create_base_test_entities(db_session)
        doc = ClinicalDocument(
            patient_id=e["pat"].id,
            encounter_id=e["enc"].id,
            practitioner_id=e["prac"].id,
            document_type="CONSULTATION",
            title="Versioning Test Doc",
            body_text="CHIEF COMPLAINT: Multi-line clinical note.\nHISTORY: Chronic symptoms.\nPLAN: Conservative therapy.",
            authored_at=datetime.now(UTC),
            text_hash="hash_version_1",
        )
        db_session.add(doc)
        db_session.commit()

        pipeline = EvidenceIngestionPipeline(db_session)

        # Ingestion with v1.0
        m1 = pipeline.ingest(
            dataset_build_id=e["build_id"],
            source_types=["ClinicalDocument"],
            chunker_version="v1.0",
        )
        assert m1.chunks_persisted >= 1

        # Reprocess with v2.0
        m2 = pipeline.ingest(
            dataset_build_id=e["build_id"],
            source_types=["ClinicalDocument"],
            chunker_version="v2.0",
            reprocess=True,
        )
        assert m2.chunks_persisted >= 1
        assert m2.chunks_superseded >= 1

        # Check in DB that old chunks are is_active = False, new chunks are is_active = True
        v1_chunks = (
            db_session.query(EvidenceChunk)
            .filter_by(source_resource_id=doc.id, chunker_version="v1.0")
            .all()
        )
        v2_chunks = (
            db_session.query(EvidenceChunk)
            .filter_by(source_resource_id=doc.id, chunker_version="v2.0")
            .all()
        )

        assert all(not c.is_active for c in v1_chunks), "Old version chunks must be deactivated"
        assert all(c.is_active for c in v2_chunks), "New version chunks must be active"

        # Cleanup
        pipeline.reset_build_chunks(e["build_id"])

    def test_accurate_text_offsets_and_counts(self):
        """6. Accurate text offsets, character counts, and token counts."""
        raw_text = (
            "1. FIRST SECTION: Patient reports moderate discomfort.\n\n"
            "2. SECOND SECTION: Objective examination reveals normal range of motion.\n\n"
            "3. THIRD SECTION: Discharge instructions provided to patient."
        )
        norm_text, chash = SafeTextNormalizer.normalize(raw_text)
        doc = CanonicalDocument(
            source_id=uuid.uuid4(),
            source_type=CanonicalSourceType.CLINICAL_DOCUMENT,
            evidentiary_role=EvidentiaryRole.CLINICAL_SUPPORTING,
            patient_id=uuid.uuid4(),
            raw_content=raw_text,
            normalized_content=norm_text,
            content_hash=chash,
        )

        chunker = DeterministicEvidenceChunker(chunk_size=100, chunk_overlap=20, version="v1.0")
        chunks = chunker.chunk_document(doc)

        assert len(chunks) > 1
        for c in chunks:
            # Check length matches content length
            assert c.char_count == len(c.content)
            # Check token count matches estimate
            assert c.token_count == chunker.estimate_tokens(c.content)
            # Check hash matches content hash
            assert c.text_hash == chunker.compute_hash(c.content)
            # Check slice in source text
            slice_text = norm_text[c.source_text_offset : c.source_text_offset + c.source_text_length]
            assert c.content in slice_text or slice_text in c.content

    def test_patient_and_tenant_isolation(self, db_session):
        """7. Correct patient and tenant isolation."""
        e = create_base_test_entities(db_session)
        doc = ClinicalDocument(
            patient_id=e["pat"].id,
            encounter_id=e["enc"].id,
            practitioner_id=e["prac"].id,
            document_type="CONSULTATION",
            title="Isolation Note",
            body_text="Patient specific confidential progress note.",
            authored_at=datetime.now(UTC),
            text_hash="hash_iso_1",
        )
        db_session.add(doc)
        db_session.flush()

        # Other patient in different org
        other_pat = Patient(
            organization_id=e["org"].id,
            dataset_build_id="other_build",
            synthetic_mrn="MRN-OTHER-PAT",
            first_name="Other",
            last_name="Patient",
            gender="male",
            birth_date=date(1990, 1, 1),
            split_group="train_dev",
            is_synthetic=True,
        )
        db_session.add(other_pat)
        db_session.flush()

        # Attempt to insert chunk for other_pat referencing doc owned by e['pat']
        bad_chunk = EvidenceChunk(
            patient_id=other_pat.id,  # Mismatched!
            source_resource_type="ClinicalDocument",
            source_resource_id=doc.id,
            clinical_document_id=doc.id,
            content="Mismatched patient chunk",
            token_count=3,
            char_count=24,
            text_hash="hash_bad_pat",
            chunker_version="v1.0",
        )
        db_session.add(bad_chunk)
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()
        assert "fk_chunk_clinical_doc_patient" in str(exc_info.value)
        db_session.rollback()

    def test_payer_policy_scoping_and_zero_patient_linkage(self, db_session):
        """8. Correct payer-policy scope, version, and zero patient linkage."""
        e = create_base_test_entities(db_session)
        pol = PayerPolicyVersion(
            payer_id=e["payer"].id,
            policy_number="POL-TEST-001",
            title="Arthroscopy Coverage Criteria",
            version="1.0",
            effective_start=date(2024, 1, 1),
            effective_end=None,
            requirements_spec={"criteria": [{"rule_id": "CRIT-1", "description": "Failure of conservative therapy"}]},
            full_text="1. COVERAGE CRITERIA: Elective arthroscopy requires documentation of conservative therapy.",
        )
        db_session.add(pol)
        db_session.flush()

        # Valid PAYER_POLICY chunk: patient_id MUST be None
        valid_policy_chunk = EvidenceChunk(
            evidentiary_role="PAYER_POLICY",
            patient_id=None,  # Zero patient linkage!
            payer_id=e["payer"].id,
            payer_policy_version_id=pol.id,
            source_resource_type="PayerPolicyVersion",
            source_resource_id=pol.id,
            chunk_index=500,  # distinct index
            content="1. COVERAGE CRITERIA: Elective arthroscopy requires documentation.",
            token_count=8,
            char_count=65,
            text_hash="hash_pol_valid",
            chunker_version="v1.0",
        )
        db_session.add(valid_policy_chunk)
        db_session.flush()

        # Negative test: Policy chunk with falsely assigned patient_id MUST be rejected by ck_chunk_scope_consistency
        invalid_policy_chunk = EvidenceChunk(
            evidentiary_role="PAYER_POLICY",
            patient_id=e["pat"].id,  # VIOLATION: Policies cannot be patient-scoped!
            payer_id=e["payer"].id,
            payer_policy_version_id=pol.id,
            source_resource_type="PayerPolicyVersion",
            source_resource_id=pol.id,
            chunk_index=501,
            content="1. COVERAGE CRITERIA: Invalid patient assignment.",
            token_count=6,
            char_count=49,
            text_hash="hash_pol_invalid",
            chunker_version="v1.0",
        )
        db_session.add(invalid_policy_chunk)
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()
        assert "ck_chunk_scope_consistency" in str(exc_info.value)
        db_session.rollback()

    def test_rejection_of_orphan_chunks_without_provenance(self, db_session):
        """9. Rejection of chunks without valid canonical provenance."""
        e = create_base_test_entities(db_session)
        orphan_chunk = EvidenceChunk(
            patient_id=e["pat"].id,
            source_resource_type="ClinicalDocument",
            source_resource_id=uuid.uuid4(),  # Random orphan
            content="Orphan chunk with no FK",
            token_count=5,
            char_count=23,
            text_hash="hash_orphan_test",
            chunker_version="v1.0",
        )
        db_session.add(orphan_chunk)
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()
        assert "ck_chunk_single_canonical_source" in str(exc_info.value) or "ck_chunk_source_consistency" in str(exc_info.value)
        db_session.rollback()

    def test_prevention_of_contradictory_source_metadata(self, db_session):
        """10. Prevention of contradictory source metadata."""
        e = create_base_test_entities(db_session)
        doc = ClinicalDocument(
            patient_id=e["pat"].id,
            encounter_id=e["enc"].id,
            practitioner_id=e["prac"].id,
            document_type="CONSULTATION",
            title="Valid Note",
            body_text="Valid clinical note content.",
            authored_at=datetime.now(UTC),
            text_hash="hash_valid_1",
        )
        db_session.add(doc)
        db_session.flush()

        # Contradiction: source_resource_type is Observation, but clinical_document_id is populated
        contradictory_chunk = EvidenceChunk(
            patient_id=e["pat"].id,
            source_resource_type="Observation",  # Contradiction!
            source_resource_id=doc.id,
            clinical_document_id=doc.id,
            content="Contradictory chunk",
            token_count=2,
            char_count=19,
            text_hash="hash_contra_test",
            chunker_version="v1.0",
        )
        db_session.add(contradictory_chunk)
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()
        assert "ck_chunk_source_consistency" in str(exc_info.value)
        db_session.rollback()

    def test_empty_malformed_source_handling(self):
        """11. Empty, malformed, and whitespace-only source handling."""
        with pytest.raises(ValueError, match="None"):
            SafeTextNormalizer.normalize(None)

        with pytest.raises(ValueError, match="empty or whitespace-only"):
            SafeTextNormalizer.normalize("   \n\n\t  ")

    def test_distinction_between_clinical_evidence_and_denial_context(self, db_session):
        """12. Distinction between clinical evidence and denial context."""
        # Query the existing canonical denial context chunk
        denial_chunk = (
            db_session.query(EvidenceChunk)
            .filter_by(evidentiary_role="DENIAL_CONTEXT")
            .first()
        )
        assert denial_chunk is not None, "Smoke dataset must have at least one denial chunk"
        assert denial_chunk.evidentiary_role == "DENIAL_CONTEXT"
        assert denial_chunk.payer_policy_version_id is None
        assert denial_chunk.clinical_document_id is None
        assert denial_chunk.denial_event_id is not None
        assert denial_chunk.claim_id is not None
        assert denial_chunk.patient_id is not None

        # Negative test: Denial chunk falsely claiming CLINICAL_SUPPORTING role
        fake_clinical_chunk = EvidenceChunk(
            evidentiary_role="CLINICAL_SUPPORTING",  # Falsely claiming clinical role
            patient_id=denial_chunk.patient_id,
            claim_id=denial_chunk.claim_id,
            denial_event_id=denial_chunk.denial_event_id,
            source_resource_type="DenialEvent",
            source_resource_id=denial_chunk.source_resource_id,
            chunk_index=999,  # Distinct index
            content="Falsely claiming clinical role.",
            token_count=4,
            char_count=32,
            text_hash="hash_fake_clinical_test",
            chunker_version="v9.9",
        )
        db_session.add(fake_clinical_chunk)
        with pytest.raises(IntegrityError) as exc_info:
            db_session.flush()
        assert "ck_chunk_scope_consistency" in str(exc_info.value)
        db_session.rollback()

    def test_failed_ingestion_rollback(self, db_session):
        """13. Failed ingestion rollback and failure manifest."""
        pipeline = EvidenceIngestionPipeline(db_session)
        # Attempt ingestion for invalid / empty build on clinical documents
        manifest = pipeline.ingest(
            dataset_build_id="nonexistent_build_9999",
            source_types=["ClinicalDocument"],
            dry_run=False,
        )
        assert manifest.sources_processed == 0
        assert manifest.chunks_persisted == 0

    def test_safe_cleanup_preserves_canonical_sources(self, db_session):
        """14. Safe cleanup that never deletes canonical sources."""
        e = create_base_test_entities(db_session)
        doc = ClinicalDocument(
            patient_id=e["pat"].id,
            encounter_id=e["enc"].id,
            practitioner_id=e["prac"].id,
            document_type="CONSULTATION",
            title="Preservation Note",
            body_text="Important clinical data.",
            authored_at=datetime.now(UTC),
            text_hash="hash_preserv_1",
        )
        db_session.add(doc)
        db_session.commit()

        pipeline = EvidenceIngestionPipeline(db_session)
        pipeline.ingest(dataset_build_id=e["build_id"], source_types=["ClinicalDocument"])

        # Reset chunks for this build
        deleted_count = pipeline.reset_build_chunks(e["build_id"])
        assert deleted_count >= 1

        # Assert canonical patient, claim, and clinical document are STILL INTACT!
        pat_still_exists = db_session.query(Patient).filter_by(id=e["pat"].id).first()
        doc_still_exists = db_session.query(ClinicalDocument).filter_by(id=doc.id).first()
        claim_still_exists = db_session.query(Claim).filter_by(id=e["claim"].id).first()

        assert pat_still_exists is not None, "Canonical Patient must NOT be deleted by reset_build_chunks!"
        assert doc_still_exists is not None, "Canonical ClinicalDocument must NOT be deleted by reset_build_chunks!"
        assert claim_still_exists is not None, "Canonical Claim must NOT be deleted by reset_build_chunks!"
