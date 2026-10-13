import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy.exc import IntegrityError

from backend.app.db.models import (
    Claim,
    ClaimDiagnosis,
    ClinicalDocument,
    Condition,
    Coverage,
    Encounter,
    EvidenceChunk,
    Facility,
    Organization,
    Patient,
    Payer,
    PayerPlan,
    Practitioner,
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
    db.flush()

    return {
        "org": org,
        "fac": fac,
        "prac": prac,
        "pat": pat,
        "payer": payer,
        "plan": plan,
        "cov": cov,
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
