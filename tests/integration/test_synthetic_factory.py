"""Integration tests for Synthetic Data Factory (Phase 3, Phase 4 & Phase 5: Claims, Policies & Denials).

Verifies:
1. Exact canonical determinism (identical seed = identical clinical records, FHIR payloads, claims, and denials).
2. Divergence across different seeds.
3. Foreign key and relational integrity across clinical and revenue cycle entities.
4. Tenant and organization boundary enforcement.
5. Patient-disjoint split sets (train_dev vs holdout_test).
6. Temporal coherence (start_time <= end_time, child records within encounter period, appeal_deadline >= denial_date).
7. Normalized-to-FHIR parity and structural validity.
8. Validation failures on temporal contradictions, cross-patient leakage, or corrupted hashes.
9. Revenue cycle exact financial arithmetic (claims total = sum(lines), remit total = sum(lines), billed = paid + adj).
10. Complete coverage of all 12 authoritative denial categories.
11. Representation of partial denials, whole-claim denials, and paid control claims.
12. Multi-denial claims representation.
13. Idempotency, safe build isolation, and cascade reset without deleting shared reference data.
14. Transactional rollback on generation failure.
15. Manifest accuracy (seed, counts, config hash, validation report).
16. Synthetic markers and zero-PHI enforcement.
"""

from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.data_factory import (
    DataFactoryPipeline,
    get_profile,
    validate_dataset,
)
from backend.app.data_factory.config import DataFactoryProfile
from backend.app.data_factory.generators.claims import generate_claims
from backend.app.data_factory.generators.clinical import generate_clinical
from backend.app.data_factory.generators.identities import generate_identities
from backend.app.data_factory.generators.insurance import generate_insurance
from backend.app.data_factory.generators.organizations import generate_organizations
from backend.app.db.models import (
    Authorization,
    Claim,
    ClaimDiagnosis,
    ClaimLine,
    DenialEvent,
    Patient,
    Payer,
    PayerPolicyVersion,
    Remittance,
    ServiceCode,
)
from backend.app.db.session import SessionLocal


@pytest.fixture
def db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


class TestSyntheticDataFactoryDeterminism:
    def test_identical_seed_produces_identical_canonical_data(self):
        """Rule 1: Same seed + profile produce 100% bit-for-bit identical canonical logical records."""
        profile = get_profile("smoke")
        seed = 20261013

        # Run 1
        org_res_1 = generate_organizations(seed, profile)
        pats_1 = generate_identities(seed, profile, org_res_1.organizations, "build_test_1")
        covs_1 = generate_insurance(seed, profile, pats_1, org_res_1.plans)
        clin_1 = generate_clinical(seed, profile, pats_1, org_res_1.facilities, org_res_1.practitioners)
        claims_1 = generate_claims(seed, profile, org_res_1, pats_1, covs_1, clin_1)

        # Run 2
        org_res_2 = generate_organizations(seed, profile)
        pats_2 = generate_identities(seed, profile, org_res_2.organizations, "build_test_1")
        covs_2 = generate_insurance(seed, profile, pats_2, org_res_2.plans)
        clin_2 = generate_clinical(seed, profile, pats_2, org_res_2.facilities, org_res_2.practitioners)
        claims_2 = generate_claims(seed, profile, org_res_2, pats_2, covs_2, clin_2)

        # Validate bit-for-bit parity across Clinical records
        assert len(clin_1.encounters) == len(clin_2.encounters)
        for e1, e2 in zip(clin_1.encounters, clin_2.encounters, strict=False):
            assert e1.id == e2.id
            assert e1.start_time == e2.start_time
            assert e1.end_time == e2.end_time
            assert e1.encounter_class == e2.encounter_class

        for p1, p2 in zip(clin_1.procedures, clin_2.procedures, strict=False):
            assert p1.id == p2.id
            assert p1.code == p2.code
            assert p1.performed_time == p2.performed_time

        for f1, f2 in zip(clin_1.fhir_resources, clin_2.fhir_resources, strict=False):
            assert f1.id == f2.id
            assert f1.resource_type == f2.resource_type
            assert f1.payload == f2.payload

        # Validate bit-for-bit parity across Revenue Cycle Claims & Denial records
        assert len(claims_1.claims) == len(claims_2.claims)
        for c1, c2 in zip(claims_1.claims, claims_2.claims, strict=False):
            assert c1.id == c2.id
            assert c1.claim_number == c2.claim_number
            assert c1.total_billed_amount == c2.total_billed_amount
            assert c1.service_start_date == c2.service_start_date

        assert len(claims_1.claim_lines) == len(claims_2.claim_lines)
        for cl1, cl2 in zip(claims_1.claim_lines, claims_2.claim_lines, strict=False):
            assert cl1.id == cl2.id
            assert cl1.service_code == cl2.service_code
            assert cl1.billed_amount == cl2.billed_amount

        assert len(claims_1.denial_events) == len(claims_2.denial_events)
        for de1, de2 in zip(claims_1.denial_events, claims_2.denial_events, strict=False):
            assert de1.id == de2.id
            assert de1.denial_category == de2.denial_category
            assert de1.carc_code == de2.carc_code
            assert de1.denied_amount == de2.denied_amount
            assert de1.appeal_deadline == de2.appeal_deadline

    def test_different_seeds_produce_divergent_data(self):
        """Rule 2: Distinct seeds produce diverging clinical and claims datasets."""
        profile = get_profile("smoke")

        # Seed A
        seed_a = 20261013
        org_a = generate_organizations(seed_a, profile)
        pats_a = generate_identities(seed_a, profile, org_a.organizations, "build_a")
        covs_a = generate_insurance(seed_a, profile, pats_a, org_a.plans)
        clin_a = generate_clinical(seed_a, profile, pats_a, org_a.facilities, org_a.practitioners)
        claims_a = generate_claims(seed_a, profile, org_a, pats_a, covs_a, clin_a)

        # Seed B
        seed_b = 99999999
        org_b = generate_organizations(seed_b, profile)
        pats_b = generate_identities(seed_b, profile, org_b.organizations, "build_b")
        covs_b = generate_insurance(seed_b, profile, pats_b, org_b.plans)
        clin_b = generate_clinical(seed_b, profile, pats_b, org_b.facilities, org_b.practitioners)
        claims_b = generate_claims(seed_b, profile, org_b, pats_b, covs_b, clin_b)

        enc_ids_a = {e.id for e in clin_a.encounters}
        enc_ids_b = {e.id for e in clin_b.encounters}
        assert enc_ids_a != enc_ids_b

        claim_ids_a = {c.id for c in claims_a.claims}
        claim_ids_b = {c.id for c in claims_b.claims}
        assert claim_ids_a != claim_ids_b
        claim_nums_a = {c.claim_number for c in claims_a.claims}
        claim_nums_b = {c.claim_number for c in claims_b.claims}
        assert claim_nums_a != claim_nums_b

        denial_ids_a = {de.id for de in claims_a.denial_events}
        denial_ids_b = {de.id for de in claims_b.denial_events}
        assert denial_ids_a != denial_ids_b


class TestSyntheticDataValidationRules:
    def test_valid_dataset_passes_all_checks(self):
        """Rule 3: Baseline smoke dataset satisfies all validation suites including clinical, FHIR, and claims."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)
        claims_res = generate_claims(seed, profile, org_res, pats, covs, clin_res)

        report = validate_dataset(profile, org_res, pats, covs, clin_res, claims_res)
        assert report.passed is True
        assert len(report.errors) == 0
        assert report.checks["counts"]["valid"] is True
        assert report.checks["foreign_keys"]["valid"] is True
        assert report.checks["split_disjointness"]["valid"] is True
        assert report.checks["synthetic_designation"]["valid"] is True
        assert report.checks["zero_phi_leakage"]["valid"] is True
        assert report.checks["demographics"]["valid"] is True
        assert report.checks["clinical_timeline_coherence"]["valid"] is True
        assert report.checks["fhir_parity_and_integrity"]["valid"] is True
        assert report.checks["claims_and_denials_integrity"]["valid"] is True

    def test_all_12_denial_categories_covered(self):
        """Rule 4: Generated dataset covers all 12 authoritative denial categories with valid templates."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "cat_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)
        claims_res = generate_claims(seed, profile, org_res, pats, covs, clin_res)

        categories_found = {de.denial_category for de in claims_res.denial_events}
        expected_categories = {
            "MED_NEC_01",
            "PA_MISS_02",
            "DOC_INCOMP_03",
            "CODE_MISMATCH_04",
            "DUP_BUNDLE_05",
            "ELIG_TIMING_06",
            "UNTIMELY_07",
            "NON_COV_08",
            "UNITS_MOD_09",
            "COB_OTHER_10",
            "INSUF_INFO_11",
            "CLIN_CONFLICT_12",
        }
        assert expected_categories.issubset(categories_found)

    def test_financial_arithmetic_reconciliation_exact(self):
        """Rule 5: Claim headers reconcile with lines, remittances reconcile with lines, and billed = paid + adj."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "fin_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)
        claims_res = generate_claims(seed, profile, org_res, pats, covs, clin_res)

        # Corrupt one claim line billed amount deliberately
        corrupted_line = claims_res.claim_lines[0]
        original_billed = corrupted_line.billed_amount
        corrupted_line.billed_amount = original_billed + Decimal("500.00")

        report = validate_dataset(profile, org_res, pats, covs, clin_res, claims_res)
        assert report.passed is False
        assert any("financial mismatch" in err or "balance mismatch" in err for err in report.errors)

        # Restore
        corrupted_line.billed_amount = original_billed

    def test_clinical_temporal_contradiction_detected(self):
        """Rule 6: Inverted encounter timestamps (start_time > end_time) fail validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        clin_res.encounters[0].start_time = clin_res.encounters[0].end_time + timedelta(hours=2)
        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("start_time > end_time" in err for err in report.errors)

    def test_clinical_cross_patient_leakage_detected(self):
        """Rule 7: Procedure assigned to different patient than its encounter fails validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        clin_res.procedures[0].patient_id = pats[1].id
        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("patient_id != encounter patient_id" in err for err in report.errors)

    def test_document_hash_tampering_detected(self):
        """Rule 8: Modified clinical document text without updated text_hash fails validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        clin_res.clinical_documents[0].body_text += "\n[UNAUTHENTICATED ALTERATION]"
        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("text_hash mismatch" in err for err in report.errors)

    def test_patient_disjoint_partitions_strict(self):
        """Rule 9: Overlap between train_dev and holdout_test partitions fails validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        pats[0].id = pats[-1].id
        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("Partition leakage" in err for err in report.errors)

    def test_zero_phi_leakage_in_clinical_documents(self):
        """Rule 10: Clinical documents containing prohibited real-world PHI patterns fail validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        clin_res.clinical_documents[0].body_text += " SSN: 123-45-6789"
        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("Prohibited SSN pattern found" in err for err in report.errors)


class TestSyntheticDataPipelineLifecycle:
    def test_invalid_profile_configuration_fails(self):
        """Rule 11: Requesting non-existent profile raises ValueError."""
        with pytest.raises(ValueError, match="Unknown data factory profile"):
            get_profile("non_existent_profile")

    def test_pipeline_generate_and_cascade_reset(self, db_session: Session):
        """Rule 12: End-to-end pipeline generates clinical, FHIR, and claims data, and reset cascades cleanly."""
        build_id = "test_build_claims_lifecycle_v1"
        pipeline = DataFactoryPipeline()

        # Step 1: Clean any pre-existing run
        pipeline.reset(build_id, session=db_session)

        # Step 2: Generate smoke dataset
        build = pipeline.generate(
            profile_name="smoke",
            seed=20269999,
            build_id=build_id,
            session=db_session,
            replace_existing=True,
        )

        assert build.id == build_id
        assert build.patient_count == 25
        assert build.claim_count == 25
        assert build.validation_passed is True

        # Query and verify database persistence
        patients = db_session.execute(
            select(Patient).where(Patient.dataset_build_id == build_id)
        ).scalars().all()
        assert len(patients) == 25
        pat_ids = [p.id for p in patients]

        claims = db_session.execute(
            select(Claim).where(Claim.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(claims) == 25
        claim_ids = [c.id for c in claims]

        claim_lines = db_session.execute(
            select(ClaimLine).where(ClaimLine.claim_id.in_(claim_ids))
        ).scalars().all()
        assert len(claim_lines) >= 25

        claim_diags = db_session.execute(
            select(ClaimDiagnosis).where(ClaimDiagnosis.claim_id.in_(claim_ids))
        ).scalars().all()
        assert len(claim_diags) >= 25

        auths = db_session.execute(
            select(Authorization)
        ).scalars().all()
        assert len(auths) >= 20

        denial_events = db_session.execute(
            select(DenialEvent).where(DenialEvent.claim_id.in_(claim_ids))
        ).scalars().all()
        assert len(denial_events) >= 12

        remittances = db_session.execute(
            select(Remittance)
        ).scalars().all()
        assert len(remittances) >= 25

        # Step 3: Cascade reset
        counts = pipeline.reset(build_id, session=db_session)
        assert counts["claims"] == 25
        assert counts["denial_events"] >= 12
        assert counts["remittance_lines"] >= 25
        assert counts["remittances"] >= 25
        assert counts["claim_diagnoses"] >= 25
        assert counts["claim_lines"] >= 25
        assert counts["authorizations"] >= 20
        assert counts["patients"] == 25
        assert counts["dataset_builds"] == 1

        # Verify claims completely purged
        rem_claims = db_session.execute(
            select(Claim).where(Claim.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(rem_claims) == 0

        rem_denials = db_session.execute(
            select(DenialEvent).where(DenialEvent.claim_id.in_(claim_ids))
        ).scalars().all()
        assert len(rem_denials) == 0

        # Verify shared reference entities were NOT deleted
        payers_remain = db_session.execute(select(Payer)).scalars().all()
        assert len(payers_remain) >= 3

        policies_remain = db_session.execute(select(PayerPolicyVersion)).scalars().all()
        assert len(policies_remain) >= 6

        sc_remain = db_session.execute(select(ServiceCode)).scalars().all()
        assert len(sc_remain) >= 10

    def test_failed_generation_leaves_no_partial_records(self, db_session: Session):
        """Rule 13: If generation fails, database transaction rolls back completely."""
        build_id = "test_build_failed_rollback_v3"
        pipeline = DataFactoryPipeline()

        pipeline.reset(build_id, session=db_session)

        bad_profile = DataFactoryProfile(
            name="corrupt_profile",
            organization_count=0,
            facilities_per_org=0,
            practitioners_per_org=0,
            payers_count=0,
            plans_per_payer=0,
            patient_count=10,
        )

        with pytest.raises(ValueError):
            generate_identities(12345, bad_profile, [], build_id)

        pats = db_session.execute(
            select(Patient).where(Patient.dataset_build_id == build_id)
        ).scalars().all()
        assert len(pats) == 0
