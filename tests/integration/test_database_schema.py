import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, ProgrammingError

from backend.app.db.models import (
    Appeal,
    AppealDecision,
    AppealDraftVersion,
    AuditEvent,
    Authorization,
    Claim,
    ClaimDiagnosis,
    ClaimLine,
    ClinicalDocument,
    Condition,
    Coverage,
    DenialEvent,
    Encounter,
    EvidenceChunk,
    Export,
    Facility,
    Organization,
    Patient,
    Payer,
    PayerPlan,
    Practitioner,
    Remittance,
    RemittanceLine,
    User,
)
from backend.app.db.session import SessionLocal


@pytest.fixture
def db_session():
    """Provides a transactional database session rolled back after test."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def create_base_entities(db):
    """Helper to create foundational valid entities."""
    uid = uuid.uuid4().hex[:8]
    org = Organization(
        name=f"Test Health {uid}",
        type="HOSPITAL_SYSTEM",
        tax_id=f"TX-{uid}",
        npi=f"1{uid[:9]}",
    )
    db.add(org)
    db.flush()

    fac = Facility(
        organization_id=org.id,
        name=f"Main Clinic {uid}",
        pos_code="11",
        address={"city": "Metro", "state": "CA"},
    )
    db.add(fac)

    prac = Practitioner(
        organization_id=org.id,
        npi=f"2{uid[:9]}",
        first_name="Jane",
        last_name="Doe",
        specialty="Orthopedics",
        credentials="MD",
    )
    db.add(prac)

    pat = Patient(
        organization_id=org.id,
        dataset_build_id="test_build_v1",
        synthetic_mrn=f"MRN-{uid}",
        first_name="John",
        last_name="Smith",
        gender="male",
        birth_date=date(1980, 1, 1),
        split_group="train_dev",
        is_synthetic=True,
    )
    db.add(pat)

    payer = Payer(
        payer_identifier=f"PAYER_{uid}",
        name="Test Blue Payer",
        line_of_business="COMMERCIAL",
        timely_filing_days=90,
        appeal_filing_days=180,
    )
    db.add(payer)
    db.flush()

    plan = PayerPlan(
        payer_id=payer.id,
        plan_name="Gold Choice",
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

    user = User(
        email=f"user_{uid}@example.com",
        hashed_password="fake_hashed_password",
        full_name="Test Analyst",
        is_active=True,
    )
    db.add(user)
    db.flush()

    return {
        "org": org,
        "fac": fac,
        "prac": prac,
        "pat": pat,
        "payer": payer,
        "plan": plan,
        "cov": cov,
        "user": user,
    }


def test_encounter_temporal_coherence_constraint(db_session):
    """Encounter check constraint: end_time must be >= start_time."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)

    # Invalid encounter: discharge before admission
    invalid_enc = Encounter(
        patient_id=entities["pat"].id,
        facility_id=entities["fac"].id,
        practitioner_id=entities["prac"].id,
        encounter_class="ambulatory",
        status="finished",
        start_time=now,
        end_time=now - timedelta(hours=2),  # Invalid!
    )
    db_session.add(invalid_enc)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "ck_encounter_end_after_start" in str(exc_info.value)
    db_session.rollback()


def test_claim_negative_amount_constraint(db_session):
    """Claim check constraint: total_billed_amount cannot be negative."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)

    invalid_claim = Claim(
        claim_number=f"CLM-NEG-{uuid.uuid4().hex[:6]}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("-100.00"),  # Negative!
        currency="USD",
    )
    db_session.add(invalid_claim)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "ck_claim_total_billed_non_negative" in str(exc_info.value)
    db_session.rollback()


def test_claim_diagnosis_pointer_range_constraint(db_session):
    """Claim diagnosis pointer constraint: diagnosis_pointer must be between 1 and 12."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)

    claim = Claim(
        claim_number=f"CLM-PTR-{uuid.uuid4().hex[:6]}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1500.00"),
        currency="USD",
    )
    db_session.add(claim)
    db_session.flush()

    # Invalid pointer 0 (must be >= 1)
    invalid_diag = ClaimDiagnosis(
        claim_id=claim.id,
        patient_id=claim.patient_id,
        diagnosis_pointer=0,  # Invalid!
        diagnosis_code="M17.11",
        description="Right knee osteoarthritis",
    )
    db_session.add(invalid_diag)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "ck_claim_diag_pointer_range" in str(exc_info.value)
    db_session.rollback()


def test_tenant_isolation_composite_foreign_key(db_session):
    """Claim tenant isolation: claim.organization_id must match patient.organization_id."""
    entities1 = create_base_entities(db_session)

    # Create a second distinct organization
    uid2 = uuid.uuid4().hex[:8]
    org2 = Organization(
        name=f"Foreign Network {uid2}",
        type="PROVIDER_GROUP",
        tax_id=f"TX-{uid2}",
        npi=f"3{uid2[:9]}",
    )
    db_session.add(org2)
    db_session.flush()

    now = datetime.now(UTC)

    # Attempt cross-tenant mismatch: patient belongs to org1, but claim is assigned to org2
    cross_tenant_claim = Claim(
        claim_number=f"CLM-CROSS-{uuid.uuid4().hex[:6]}",
        patient_id=entities1["pat"].id,  # Belongs to Org 1!
        organization_id=org2.id,         # Set to Org 2! Mismatch!
        coverage_id=entities1["cov"].id,
        rendering_practitioner_id=entities1["prac"].id,
        facility_id=entities1["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1000.00"),
        currency="USD",
    )
    db_session.add(cross_tenant_claim)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_claim_patient_org" in str(exc_info.value)
    db_session.rollback()


def test_patient_isolation_clinical_composite_foreign_key(db_session):
    """Clinical patient isolation: condition.patient_id must match encounter.patient_id."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)

    # Valid encounter for Patient 1
    enc = Encounter(
        patient_id=entities["pat"].id,
        facility_id=entities["fac"].id,
        practitioner_id=entities["prac"].id,
        encounter_class="ambulatory",
        status="finished",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    db_session.add(enc)

    # Create Patient 2
    uid_p2 = uuid.uuid4().hex[:8]
    pat2 = Patient(
        organization_id=entities["org"].id,
        dataset_build_id="test_build_v1",
        synthetic_mrn=f"MRN-{uid_p2}",
        first_name="Alice",
        last_name="Johnson",
        gender="female",
        birth_date=date(1992, 4, 15),
        split_group="train_dev",
        is_synthetic=True,
    )
    db_session.add(pat2)
    db_session.flush()

    # Attempt cross-patient condition mismatch:
    # encounter belongs to Patient 1, but condition claims Patient 2!
    cross_patient_cond = Condition(
        patient_id=pat2.id,      # Patient 2!
        encounter_id=enc.id,     # Encounter belongs to Patient 1!
        code_system="http://hl7.org/fhir/sid/icd-10-cm",
        code="I10",
        display="Essential hypertension",
        clinical_status="active",
        onset_time=now,
    )
    db_session.add(cross_patient_cond)

    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_condition_encounter_patient" in str(exc_info.value)
    db_session.rollback()


def test_evidence_chunk_canonical_provenance(db_session):
    """EvidenceChunk must establish canonical provenance to source clinical document."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)

    enc = Encounter(
        patient_id=entities["pat"].id,
        facility_id=entities["fac"].id,
        practitioner_id=entities["prac"].id,
        encounter_class="ambulatory",
        status="finished",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    db_session.add(enc)
    db_session.flush()

    doc = ClinicalDocument(
        patient_id=entities["pat"].id,
        encounter_id=enc.id,
        practitioner_id=entities["prac"].id,
        document_type="OPERATIVE_NOTE",
        title="Right Knee Arthroscopy",
        body_text="Patient underwent right knee arthroscopy with partial meniscectomy.",
        text_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        authored_at=now,
    )
    db_session.add(doc)
    db_session.flush()

    # Valid evidence chunk with explicit provenance to ClinicalDocument
    chunk = EvidenceChunk(
        patient_id=entities["pat"].id,
        source_resource_type="ClinicalDocument",
        source_resource_id=doc.id,
        clinical_document_id=doc.id,  # Explicit foreign key!
        encounter_id=enc.id,
        effective_date=date(2025, 5, 1),
        chunk_index=0,
        content="Patient underwent right knee arthroscopy with partial meniscectomy.",
        token_count=10,
        char_count=65,
        text_hash="hash123",
        chunker_version="v1.0",
        is_active=True,
    )
    db_session.add(chunk)
    db_session.flush()

    assert chunk.id is not None
    assert chunk.clinical_document_id == doc.id
    db_session.rollback()


# =========================================================================
# Phase 2.1 Remediation Negative and Invariant Tests
# =========================================================================

def test_evidence_chunk_negative_no_canonical_source(db_session):
    """Negative test: Evidence chunk with no canonical source must be rejected."""
    entities = create_base_entities(db_session)
    chunk = EvidenceChunk(
        patient_id=entities["pat"].id,
        source_resource_type="ClinicalDocument",
        source_resource_id=uuid.uuid4(),
        effective_date=date(2025, 5, 1),
        chunk_index=0,
        content="Orphan chunk without FK",
        token_count=5,
        char_count=24,
        text_hash="hash_orphan",
        chunker_version="v1.0",
        is_active=True,
    )
    db_session.add(chunk)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "ck_chunk_single_canonical_source" in str(exc_info.value) or "ck_chunk_source_consistency" in str(exc_info.value)
    db_session.rollback()


def test_evidence_chunk_negative_patient_mismatch(db_session):
    """Negative test: Evidence chunk patient differs from source patient."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid2 = uuid.uuid4().hex[:8]
    pat2 = Patient(
        organization_id=entities["org"].id,
        dataset_build_id="test_build_v1",
        synthetic_mrn=f"MRN-OTHER-{uid2}",
        first_name="Other",
        last_name=f"Pat-{uid2}",
        gender="female",
        birth_date=date(1992, 2, 2),
        split_group="train_dev",
        is_synthetic=True,
    )
    db_session.add(pat2)
    db_session.flush()

    enc = Encounter(
        patient_id=entities["pat"].id,
        facility_id=entities["fac"].id,
        practitioner_id=entities["prac"].id,
        encounter_class="ambulatory",
        status="finished",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    db_session.add(enc)
    db_session.flush()

    doc = ClinicalDocument(
        patient_id=entities["pat"].id,  # Owned by pat
        encounter_id=enc.id,
        practitioner_id=entities["prac"].id,
        document_type="OPERATIVE_NOTE",
        title="Note",
        body_text="Body text",
        text_hash="hash1",
        authored_at=now,
    )
    db_session.add(doc)
    db_session.flush()

    # Attempt to assign chunk to pat2 while referencing doc owned by pat
    mismatched_chunk = EvidenceChunk(
        patient_id=pat2.id,  # Mismatched!
        source_resource_type="ClinicalDocument",
        source_resource_id=doc.id,
        clinical_document_id=doc.id,
        effective_date=date(2025, 5, 1),
        chunk_index=0,
        content="Cross-patient chunk content",
        token_count=5,
        char_count=26,
        text_hash="hash_mismatch",
        chunker_version="v1.0",
        is_active=True,
    )
    db_session.add(mismatched_chunk)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_chunk_clinical_doc_patient" in str(exc_info.value)
    db_session.rollback()


def test_evidence_chunk_negative_contradictory_source_type(db_session):
    """Negative test: Declared source type contradicts populated reference."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    enc = Encounter(
        patient_id=entities["pat"].id,
        facility_id=entities["fac"].id,
        practitioner_id=entities["prac"].id,
        encounter_class="ambulatory",
        status="finished",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    db_session.add(enc)
    db_session.flush()

    doc = ClinicalDocument(
        patient_id=entities["pat"].id,
        encounter_id=enc.id,
        practitioner_id=entities["prac"].id,
        document_type="OPERATIVE_NOTE",
        title="Note",
        body_text="Body text",
        text_hash="hash_type",
        authored_at=now,
    )
    db_session.add(doc)
    db_session.flush()

    # source_resource_type declared as Observation, but clinical_document_id is populated
    chunk = EvidenceChunk(
        patient_id=entities["pat"].id,
        source_resource_type="Observation",  # Contradiction!
        source_resource_id=doc.id,
        clinical_document_id=doc.id,
        effective_date=date(2025, 5, 1),
        chunk_index=0,
        content="Contradictory chunk",
        token_count=5,
        char_count=19,
        text_hash="hash_contra",
        chunker_version="v1.0",
        is_active=True,
    )
    db_session.add(chunk)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "ck_chunk_source_consistency" in str(exc_info.value)
    db_session.rollback()


def test_evidence_chunk_negative_nonexistent_source(db_session):
    """Negative test: Chunk referencing nonexistent source ID."""
    entities = create_base_entities(db_session)
    random_id = uuid.uuid4()
    chunk = EvidenceChunk(
        patient_id=entities["pat"].id,
        source_resource_type="ClinicalDocument",
        source_resource_id=random_id,
        clinical_document_id=random_id,  # Nonexistent!
        effective_date=date(2025, 5, 1),
        chunk_index=0,
        content="Nonexistent ref",
        token_count=3,
        char_count=15,
        text_hash="hash_nonexist",
        chunker_version="v1.0",
        is_active=True,
    )
    db_session.add(chunk)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_chunk_clinical_doc_patient" in str(exc_info.value)
    db_session.rollback()


def test_claim_coverage_patient_mismatch(db_session):
    """Negative test: Claim coverage belonging to a different patient must be rejected."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid2 = uuid.uuid4().hex[:8]
    pat2 = Patient(
        organization_id=entities["org"].id,
        dataset_build_id="test_build_v1",
        synthetic_mrn=f"MRN-COV-{uid2}",
        first_name="Jane",
        last_name=f"Doe-{uid2}",
        gender="female",
        birth_date=date(1995, 3, 3),
        split_group="train_dev",
        is_synthetic=True,
    )
    db_session.add(pat2)
    db_session.flush()

    cov2 = Coverage(
        patient_id=pat2.id,
        payer_plan_id=entities["plan"].id,
        member_id=f"MEM2-{uid2}",
        group_number=f"GRP2-{uid2}",
        status="active",
        start_date=date(2025, 1, 1),
    )
    db_session.add(cov2)
    db_session.flush()

    # Claim for entities['pat'] with cov2 belonging to pat2
    invalid_claim = Claim(
        claim_number=f"CLM-COV-MIS-{uid2}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=cov2.id,  # Mismatched patient coverage!
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1200.00"),
        currency="USD",
    )
    db_session.add(invalid_claim)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_claim_coverage_patient" in str(exc_info.value)
    db_session.rollback()


def test_claim_facility_and_practitioner_org_mismatch(db_session):
    """Negative test: Claim facility/practitioner belonging to different organization."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid2 = uuid.uuid4().hex[:8]
    org2 = Organization(name=f"Other Hospital {uid2}", type="HOSPITAL_SYSTEM", tax_id=f"TX-ORG2-{uid2}", npi=f"4{uid2[:9]}")
    db_session.add(org2)
    db_session.flush()

    fac2 = Facility(organization_id=org2.id, name=f"Other Clinic {uid2}", pos_code="22")
    db_session.add(fac2)
    db_session.flush()

    # Claim with entities['org'] but fac2 from org2
    invalid_claim = Claim(
        claim_number=f"CLM-ORG-MIS-{uid2}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=fac2.id,  # Mismatched facility organization!
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1200.00"),
        currency="USD",
    )
    db_session.add(invalid_claim)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_claim_facility_org" in str(exc_info.value)
    db_session.rollback()


def test_claim_diagnosis_condition_patient_mismatch(db_session):
    """Negative test: Claim diagnosis condition belonging to a different patient."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid2 = uuid.uuid4().hex[:8]
    pat2 = Patient(
        organization_id=entities["org"].id,
        dataset_build_id="test_build_v1",
        synthetic_mrn=f"MRN-COND-{uid2}",
        first_name="Other",
        last_name=f"Pat-{uid2}",
        gender="male",
        birth_date=date(1991, 1, 1),
        split_group="train_dev",
        is_synthetic=True,
    )
    db_session.add(pat2)
    db_session.flush()

    enc2 = Encounter(
        patient_id=pat2.id,
        facility_id=entities["fac"].id,
        practitioner_id=entities["prac"].id,
        encounter_class="ambulatory",
        status="finished",
        start_time=now - timedelta(hours=1),
        end_time=now,
    )
    db_session.add(enc2)
    db_session.flush()

    cond2 = Condition(
        patient_id=pat2.id,
        encounter_id=enc2.id,
        code="E11.9",
        code_system="ICD-10-CM",
        display="Type 2 diabetes",
        clinical_status="active",
        onset_time=now,
    )
    db_session.add(cond2)
    db_session.flush()

    claim = Claim(
        claim_number=f"CLM-DIAG-PAT-{uid2}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1200.00"),
        currency="USD",
    )
    db_session.add(claim)
    db_session.flush()

    diag = ClaimDiagnosis(
        claim_id=claim.id,
        patient_id=claim.patient_id,
        condition_id=cond2.id,  # Owned by pat2!
        diagnosis_pointer=1,
        diagnosis_code="E11.9",
        description="Type 2 diabetes",
    )
    db_session.add(diag)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_claim_diag_condition_patient" in str(exc_info.value)
    db_session.rollback()


def test_claim_line_auth_coverage_and_service_code_mismatch(db_session):
    """Negative test: Claim line authorization coverage or service code mismatch rejected by trigger."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid2 = uuid.uuid4().hex[:8]
    pat2 = Patient(
        organization_id=entities["org"].id,
        dataset_build_id="test_build_v1",
        synthetic_mrn=f"MRN-AUTH-{uid2}",
        first_name="Jane",
        last_name=f"Auth-{uid2}",
        gender="female",
        birth_date=date(1985, 2, 2),
        split_group="train_dev",
        is_synthetic=True,
    )
    db_session.add(pat2)
    db_session.flush()

    cov2 = Coverage(
        patient_id=pat2.id,
        payer_plan_id=entities["plan"].id,
        member_id=f"MEM-AUTH-{uid2}",
        group_number=f"GRP-AUTH-{uid2}",
        status="active",
        start_date=date(2025, 1, 1),
    )
    db_session.add(cov2)
    db_session.flush()

    auth2 = Authorization(
        coverage_id=cov2.id,
        auth_number=f"AUTH-{uid2}",
        service_code="29881",
        requested_units=1,
        approved_units=1,
        status="APPROVED",
        effective_start=date(2025, 1, 1),
        effective_end=date(2025, 12, 31),
    )
    db_session.add(auth2)
    db_session.flush()

    claim = Claim(
        claim_number=f"CLM-AUTH-{uid2}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1500.00"),
        currency="USD",
    )
    db_session.add(claim)
    db_session.flush()

    # Attempt to assign auth2 (from cov2) to claim line on claim (with entities['cov'])
    line = ClaimLine(
        claim_id=claim.id,
        line_number=1,
        service_code="29881",
        billed_amount=Decimal("1500.00"),
        authorization_id=auth2.id,  # Mismatch!
        service_date=date(2025, 5, 1),
    )
    db_session.add(line)
    with pytest.raises((IntegrityError, ProgrammingError)) as exc_info:
        db_session.flush()
    assert "Claim line authorization" in str(exc_info.value)
    db_session.rollback()


def test_remittance_line_payer_mismatch(db_session):
    """Negative test: Remittance line payer mismatch rejected by trigger."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid = uuid.uuid4().hex[:8]

    # Create second payer
    payer2 = Payer(
        payer_identifier=f"PAYER2_{uid}",
        name=f"Other Payer {uid}",
        line_of_business="COMMERCIAL",
        timely_filing_days=90,
        appeal_filing_days=180,
    )
    db_session.add(payer2)
    db_session.flush()

    claim = Claim(
        claim_number=f"CLM-REMIT-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("1000.00"),
        currency="USD",
    )
    db_session.add(claim)
    db_session.flush()

    cl = ClaimLine(
        claim_id=claim.id,
        line_number=1,
        service_code="99213",
        billed_amount=Decimal("1000.00"),
        service_date=date(2025, 5, 1),
    )
    db_session.add(cl)
    db_session.flush()

    # Remittance issued by payer2 (not entities['payer'])
    remit = Remittance(
        payer_id=payer2.id,
        check_or_eft_number=f"EFT-{uid}",
        remittance_date=date(2025, 5, 15),
        total_paid_amount=Decimal("800.00"),
    )
    db_session.add(remit)
    db_session.flush()

    rl = RemittanceLine(
        remittance_id=remit.id,
        claim_line_id=cl.id,
        allowed_amount=Decimal("900.00"),
        paid_amount=Decimal("800.00"),
        adjustment_amount=Decimal("100.00"),
    )
    db_session.add(rl)
    with pytest.raises((IntegrityError, ProgrammingError)) as exc_info:
        db_session.flush()
    assert "Remittance payer does not match claim coverage payer" in str(exc_info.value)
    db_session.rollback()


def test_denial_event_claim_line_and_remittance_consistency(db_session):
    """Negative test: Denial event claim line / claim cross-mismatch rejected."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid = uuid.uuid4().hex[:8]

    claim1 = Claim(
        claim_number=f"CLM-DEN1-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("500.00"),
        currency="USD",
    )
    claim2 = Claim(
        claim_number=f"CLM-DEN2-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("500.00"),
        currency="USD",
    )
    db_session.add_all([claim1, claim2])
    db_session.flush()

    cl2 = ClaimLine(
        claim_id=claim2.id,
        line_number=1,
        service_code="99214",
        billed_amount=Decimal("500.00"),
        service_date=date(2025, 5, 1),
    )
    db_session.add(cl2)
    db_session.flush()

    remit = Remittance(
        payer_id=entities["payer"].id,
        check_or_eft_number=f"EFT-DEN-{uid}",
        remittance_date=date(2025, 5, 15),
        total_paid_amount=Decimal("0.00"),
    )
    db_session.add(remit)
    db_session.flush()

    rl2 = RemittanceLine(
        remittance_id=remit.id,
        claim_line_id=cl2.id,
        allowed_amount=Decimal("0.00"),
        paid_amount=Decimal("0.00"),
        adjustment_amount=Decimal("500.00"),
    )
    db_session.add(rl2)
    db_session.flush()

    # Attempt to link DenialEvent on claim1 with cl2 from claim2
    denial = DenialEvent(
        claim_id=claim1.id,  # claim1!
        claim_line_id=cl2.id,  # cl2 belongs to claim2!
        remittance_line_id=rl2.id,
        denial_category="PRIOR_AUTH",
        carc_code="197",
        denial_reason_text="Precertification absent",
        denied_amount=Decimal("500.00"),
        denial_date=date(2025, 5, 15),
        appeal_deadline=date(2025, 7, 15),
    )
    db_session.add(denial)
    with pytest.raises((IntegrityError, ProgrammingError)) as exc_info:
        db_session.flush()
    assert "fk_denial_claim_line_claim" in str(exc_info.value) or "Denial event remittance line" in str(exc_info.value)
    db_session.rollback()


def test_appeal_and_investigation_run_denial_claim_consistency(db_session):
    """Negative test: Appeal / InvestigationRun referencing denial on different claim rejected."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid = uuid.uuid4().hex[:8]

    claim1 = Claim(
        claim_number=f"CLM-APP1-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("500.00"),
        currency="USD",
    )
    claim2 = Claim(
        claim_number=f"CLM-APP2-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("500.00"),
        currency="USD",
    )
    db_session.add_all([claim1, claim2])
    db_session.flush()

    cl1 = ClaimLine(
        claim_id=claim1.id,
        line_number=1,
        service_code="99214",
        billed_amount=Decimal("500.00"),
        service_date=date(2025, 5, 1),
    )
    db_session.add(cl1)
    db_session.flush()

    remit = Remittance(
        payer_id=entities["payer"].id,
        check_or_eft_number=f"EFT-APP-{uid}",
        remittance_date=date(2025, 5, 15),
        total_paid_amount=Decimal("0.00"),
    )
    db_session.add(remit)
    db_session.flush()

    rl1 = RemittanceLine(
        remittance_id=remit.id,
        claim_line_id=cl1.id,
        allowed_amount=Decimal("0.00"),
        paid_amount=Decimal("0.00"),
        adjustment_amount=Decimal("500.00"),
    )
    db_session.add(rl1)
    db_session.flush()

    denial1 = DenialEvent(
        claim_id=claim1.id,
        claim_line_id=cl1.id,
        remittance_line_id=rl1.id,
        denial_category="PRIOR_AUTH",
        carc_code="197",
        denial_reason_text="Precertification absent",
        denied_amount=Decimal("500.00"),
        denial_date=date(2025, 5, 15),
        appeal_deadline=date(2025, 7, 15),
    )
    db_session.add(denial1)
    db_session.flush()

    # Attempt to create Appeal referencing denial1 (on claim1) but with claim2
    invalid_appeal = Appeal(
        claim_id=claim2.id,  # claim2!
        denial_event_id=denial1.id,  # denial1 belongs to claim1!
        appeal_level=1,
        status="DRAFTING",
        filing_deadline=date(2025, 7, 15),
    )
    db_session.add(invalid_appeal)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_appeal_denial_claim" in str(exc_info.value)
    db_session.rollback()


def test_appeal_decision_draft_appeal_consistency(db_session):
    """Negative test: Appeal decision referencing draft from another appeal rejected."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid = uuid.uuid4().hex[:8]

    claim = Claim(
        claim_number=f"CLM-DEC-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("500.00"),
        currency="USD",
    )
    db_session.add(claim)
    db_session.flush()

    remit = Remittance(payer_id=entities["payer"].id, check_or_eft_number=f"EFT-{uid}", remittance_date=date(2025, 5, 15), total_paid_amount=Decimal("0.00"))
    db_session.add(remit)
    db_session.flush()

    cl = ClaimLine(claim_id=claim.id, line_number=1, service_code="99214", billed_amount=Decimal("500.00"), service_date=date(2025, 5, 1))
    db_session.add(cl)
    db_session.flush()

    rl = RemittanceLine(remittance_id=remit.id, claim_line_id=cl.id, allowed_amount=Decimal("0.00"), paid_amount=Decimal("0.00"), adjustment_amount=Decimal("500.00"))
    db_session.add(rl)
    db_session.flush()

    denial = DenialEvent(claim_id=claim.id, claim_line_id=cl.id, remittance_line_id=rl.id, denial_category="MEDICAL_NECESSITY", carc_code="50", denial_reason_text="Not medically necessary", denied_amount=Decimal("500.00"), denial_date=date(2025, 5, 15), appeal_deadline=date(2025, 7, 15))
    db_session.add(denial)
    db_session.flush()

    appeal1 = Appeal(claim_id=claim.id, denial_event_id=denial.id, appeal_level=1, status="DRAFTING", filing_deadline=date(2025, 7, 15))
    appeal2 = Appeal(claim_id=claim.id, denial_event_id=denial.id, appeal_level=2, status="DRAFTING", filing_deadline=date(2025, 7, 15))
    db_session.add_all([appeal1, appeal2])
    db_session.flush()

    draft1 = AppealDraftVersion(
        appeal_id=appeal1.id,
        version_number=1,
        author_type="AGENT",
        subject_line="Appeal 1 Draft",
        body_text="Appeal body text 1",
        text_hash="hash_draft1",
    )
    db_session.add(draft1)
    db_session.flush()

    # Attempt to record decision on appeal2 referencing draft1 (which belongs to appeal1)
    invalid_decision = AppealDecision(
        appeal_id=appeal2.id,  # appeal2!
        draft_version_id=draft1.id,  # draft1 belongs to appeal1!
        reviewer_user_id=entities["user"].id,
        decision="APPROVE",
        rationale="Approved",
    )
    db_session.add(invalid_decision)
    with pytest.raises(IntegrityError) as exc_info:
        db_session.flush()
    assert "fk_decision_draft_appeal" in str(exc_info.value)
    db_session.rollback()


def test_export_human_approval_enforcement(db_session):
    """Enforce human approval before export: cannot export draft without authorized approval."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid = uuid.uuid4().hex[:8]

    claim = Claim(
        claim_number=f"CLM-EXP-{uid}",
        patient_id=entities["pat"].id,
        organization_id=entities["org"].id,
        coverage_id=entities["cov"].id,
        rendering_practitioner_id=entities["prac"].id,
        facility_id=entities["fac"].id,
        status="NEW",
        service_start_date=date(2025, 5, 1),
        service_end_date=date(2025, 5, 1),
        submission_date=now,
        total_billed_amount=Decimal("500.00"),
        currency="USD",
    )
    db_session.add(claim)
    db_session.flush()

    remit = Remittance(payer_id=entities["payer"].id, check_or_eft_number=f"EFT-{uid}", remittance_date=date(2025, 5, 15), total_paid_amount=Decimal("0.00"))
    db_session.add(remit)
    db_session.flush()

    cl = ClaimLine(claim_id=claim.id, line_number=1, service_code="99214", billed_amount=Decimal("500.00"), service_date=date(2025, 5, 1))
    db_session.add(cl)
    db_session.flush()

    rl = RemittanceLine(remittance_id=remit.id, claim_line_id=cl.id, allowed_amount=Decimal("0.00"), paid_amount=Decimal("0.00"), adjustment_amount=Decimal("500.00"))
    db_session.add(rl)
    db_session.flush()

    denial = DenialEvent(claim_id=claim.id, claim_line_id=cl.id, remittance_line_id=rl.id, denial_category="MEDICAL_NECESSITY", carc_code="50", denial_reason_text="Not medically necessary", denied_amount=Decimal("500.00"), denial_date=date(2025, 5, 15), appeal_deadline=date(2025, 7, 15))
    db_session.add(denial)
    db_session.flush()

    appeal = Appeal(claim_id=claim.id, denial_event_id=denial.id, appeal_level=1, status="DRAFTING", filing_deadline=date(2025, 7, 15))
    db_session.add(appeal)
    db_session.flush()

    draft = AppealDraftVersion(
        appeal_id=appeal.id,
        version_number=1,
        author_type="AGENT",
        subject_line="Draft for Export",
        body_text="Export body text",
        text_hash="hash_export_draft",
    )
    db_session.add(draft)
    db_session.flush()

    # 1. Negative test: export without approval must fail!
    unapproved_export = Export(
        appeal_id=appeal.id,
        draft_version_id=draft.id,
        exported_by_user_id=entities["user"].id,
        export_format="PDF",
        file_path="/exports/draft1.pdf",
        file_hash="hash_pdf",
    )
    db_session.add(unapproved_export)
    with pytest.raises((IntegrityError, ProgrammingError)) as exc_info:
        db_session.flush()
    assert "Cannot export draft version without explicit authorized human approval" in str(exc_info.value)
    db_session.rollback()

    # Re-fetch or recreate for positive test
    entities = create_base_entities(db_session)
    claim = Claim(claim_number=f"CLM-EXP-OK-{uid}", patient_id=entities["pat"].id, organization_id=entities["org"].id, coverage_id=entities["cov"].id, rendering_practitioner_id=entities["prac"].id, facility_id=entities["fac"].id, status="NEW", service_start_date=date(2025, 5, 1), service_end_date=date(2025, 5, 1), submission_date=now, total_billed_amount=Decimal("500.00"), currency="USD")
    db_session.add(claim)
    db_session.flush()
    cl = ClaimLine(claim_id=claim.id, line_number=1, service_code="99214", billed_amount=Decimal("500.00"), service_date=date(2025, 5, 1))
    db_session.add(cl)
    remit = Remittance(payer_id=entities["payer"].id, check_or_eft_number=f"EFT-OK-{uid}", remittance_date=date(2025, 5, 15), total_paid_amount=Decimal("0.00"))
    db_session.add(remit)
    db_session.flush()
    rl = RemittanceLine(remittance_id=remit.id, claim_line_id=cl.id, allowed_amount=Decimal("0.00"), paid_amount=Decimal("0.00"), adjustment_amount=Decimal("500.00"))
    db_session.add(rl)
    db_session.flush()
    denial = DenialEvent(claim_id=claim.id, claim_line_id=cl.id, remittance_line_id=rl.id, denial_category="MEDICAL_NECESSITY", carc_code="50", denial_reason_text="Not medically necessary", denied_amount=Decimal("500.00"), denial_date=date(2025, 5, 15), appeal_deadline=date(2025, 7, 15))
    db_session.add(denial)
    db_session.flush()
    appeal = Appeal(claim_id=claim.id, denial_event_id=denial.id, appeal_level=1, status="DRAFTING", filing_deadline=date(2025, 7, 15))
    db_session.add(appeal)
    db_session.flush()
    draft = AppealDraftVersion(appeal_id=appeal.id, version_number=1, author_type="AGENT", subject_line="Draft for Export", body_text="Export body text", text_hash="hash_export_draft_ok")
    db_session.add(draft)
    db_session.flush()

    # Add approval decision
    decision = AppealDecision(
        appeal_id=appeal.id,
        draft_version_id=draft.id,
        reviewer_user_id=entities["user"].id,
        decision="APPROVE",
        rationale="Analyst reviewed and approved draft",
    )
    db_session.add(decision)
    db_session.flush()

    # Now export succeeds!
    approved_export = Export(
        appeal_id=appeal.id,
        draft_version_id=draft.id,
        exported_by_user_id=entities["user"].id,
        export_format="PDF",
        file_path="/exports/draft1.pdf",
        file_hash="hash_pdf",
    )
    db_session.add(approved_export)
    db_session.flush()
    assert approved_export.id is not None
    db_session.rollback()


def test_immutable_records_triggers(db_session):
    """Immutable records: audit_events, appeal_draft_versions, exports cannot be updated or deleted."""
    entities = create_base_entities(db_session)
    now = datetime.now(UTC)
    uid = uuid.uuid4().hex[:8]

    # 1. Audit event immutability
    audit = AuditEvent(
        actor_type="USER",
        actor_user_id=entities["user"].id,
        organization_id=entities["org"].id,
        correlation_id=f"corr-{uid}",
        action="LOGIN",
        entity_type="user",
        entity_id=entities["user"].id,
    )
    db_session.add(audit)
    db_session.flush()

    # Attempt UPDATE on audit_events
    with pytest.raises((IntegrityError, ProgrammingError)) as exc_info:
        db_session.execute(
            text("UPDATE audit_events SET action = 'LOGOUT' WHERE id = :id"),
            {"id": audit.id},
        )
        db_session.flush()
    assert "audit_events is append-only" in str(exc_info.value)
    db_session.rollback()

    # 2. Appeal draft version immutability
    entities = create_base_entities(db_session)
    claim = Claim(claim_number=f"CLM-IMM-{uid}", patient_id=entities["pat"].id, organization_id=entities["org"].id, coverage_id=entities["cov"].id, rendering_practitioner_id=entities["prac"].id, facility_id=entities["fac"].id, status="NEW", service_start_date=date(2025, 5, 1), service_end_date=date(2025, 5, 1), submission_date=now, total_billed_amount=Decimal("500.00"), currency="USD")
    db_session.add(claim)
    db_session.flush()
    cl = ClaimLine(claim_id=claim.id, line_number=1, service_code="99214", billed_amount=Decimal("500.00"), service_date=date(2025, 5, 1))
    db_session.add(cl)
    remit = Remittance(payer_id=entities["payer"].id, check_or_eft_number=f"EFT-IMM-{uid}", remittance_date=date(2025, 5, 15), total_paid_amount=Decimal("0.00"))
    db_session.add(remit)
    db_session.flush()
    rl = RemittanceLine(remittance_id=remit.id, claim_line_id=cl.id, allowed_amount=Decimal("0.00"), paid_amount=Decimal("0.00"), adjustment_amount=Decimal("500.00"))
    db_session.add(rl)
    db_session.flush()
    denial = DenialEvent(claim_id=claim.id, claim_line_id=cl.id, remittance_line_id=rl.id, denial_category="MEDICAL_NECESSITY", carc_code="50", denial_reason_text="Not medically necessary", denied_amount=Decimal("500.00"), denial_date=date(2025, 5, 15), appeal_deadline=date(2025, 7, 15))
    db_session.add(denial)
    db_session.flush()
    appeal = Appeal(claim_id=claim.id, denial_event_id=denial.id, appeal_level=1, status="DRAFTING", filing_deadline=date(2025, 7, 15))
    db_session.add(appeal)
    db_session.flush()
    draft = AppealDraftVersion(appeal_id=appeal.id, version_number=1, author_type="AGENT", subject_line="Immutable Draft", body_text="Draft body", text_hash="hash_draft_imm")
    db_session.add(draft)
    db_session.flush()

    # Attempt UPDATE on appeal_draft_versions
    with pytest.raises((IntegrityError, ProgrammingError)) as exc_info:
        db_session.execute(
            text("UPDATE appeal_draft_versions SET body_text = 'Modified body' WHERE id = :id"),
            {"id": draft.id},
        )
        db_session.flush()
    assert "appeal_draft_versions are immutable snapshots" in str(exc_info.value)
    db_session.rollback()
