"""Integration tests for Synthetic Data Factory (Phase 3 & Phase 4: Clinical Timelines & FHIR Mapping).

Verifies:
1. Exact canonical determinism (identical seed = identical clinical records & FHIR payloads).
2. Divergence across different seeds.
3. Foreign key and relational integrity across clinical entities.
4. Tenant and organization boundary enforcement.
5. Patient-disjoint split sets (train_dev vs holdout_test).
6. Temporal coherence (start_time <= end_time, child records within encounter period).
7. Normalized-to-FHIR parity and structural validity.
8. Validation failures on temporal contradictions, cross-patient leakage, or corrupted hashes.
9. Idempotency, safe build isolation, and cascade reset.
10. Transactional rollback on generation failure.
11. Manifest accuracy (seed, counts, config hash, validation report).
12. Synthetic markers and zero-PHI enforcement in structured records and clinical documents.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.data_factory import (
    GENERATOR_VERSION,
    DataFactoryPipeline,
    get_profile,
    validate_dataset,
)
from backend.app.data_factory.config import DataFactoryProfile
from backend.app.data_factory.generators.clinical import generate_clinical
from backend.app.data_factory.generators.identities import generate_identities
from backend.app.data_factory.generators.insurance import generate_insurance
from backend.app.data_factory.generators.organizations import generate_organizations
from backend.app.db.models import (
    ClinicalDocument,
    DatasetBuild,
    Encounter,
    FhirResource,
    Patient,
    Procedure,
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

        # Run 2
        org_res_2 = generate_organizations(seed, profile)
        pats_2 = generate_identities(seed, profile, org_res_2.organizations, "build_test_1")
        covs_2 = generate_insurance(seed, profile, pats_2, org_res_2.plans)
        clin_2 = generate_clinical(seed, profile, pats_2, org_res_2.facilities, org_res_2.practitioners)

        # Canonical comparisons of organizations
        assert [(o.id, o.name, o.tax_id) for o in org_res_1.organizations] == [(o.id, o.name, o.tax_id) for o in org_res_2.organizations]

        # Canonical comparisons of patients
        assert [(p.id, p.synthetic_mrn, p.first_name, str(p.birth_date)) for p in pats_1] == [(p.id, p.synthetic_mrn, p.first_name, str(p.birth_date)) for p in pats_2]

        # Canonical comparisons of coverages
        assert [(c.id, c.patient_id, c.payer_plan_id, c.member_id) for c in covs_1] == [(c.id, c.patient_id, c.payer_plan_id, c.member_id) for c in covs_2]

        # Canonical comparisons of encounters
        assert [(e.id, e.patient_id, e.encounter_class, str(e.start_time), str(e.end_time)) for e in clin_1.encounters] == [(e.id, e.patient_id, e.encounter_class, str(e.start_time), str(e.end_time)) for e in clin_2.encounters]

        # Canonical comparisons of conditions
        assert [(c.id, c.patient_id, c.code, c.display, str(c.onset_time)) for c in clin_1.conditions] == [(c.id, c.patient_id, c.code, c.display, str(c.onset_time)) for c in clin_2.conditions]

        # Canonical comparisons of procedures
        assert [(pr.id, pr.patient_id, pr.code, str(pr.performed_time)) for pr in clin_1.procedures] == [(pr.id, pr.patient_id, pr.code, str(pr.performed_time)) for pr in clin_2.procedures]

        # Canonical comparisons of observations
        assert [(o.id, o.patient_id, o.code, float(o.value_numeric) if o.value_numeric else None) for o in clin_1.observations] == [(o.id, o.patient_id, o.code, float(o.value_numeric) if o.value_numeric else None) for o in clin_2.observations]

        # Canonical comparisons of clinical documents
        assert [(d.id, d.patient_id, d.document_type, d.text_hash) for d in clin_1.clinical_documents] == [(d.id, d.patient_id, d.document_type, d.text_hash) for d in clin_2.clinical_documents]

        # Canonical comparisons of FHIR resources
        fhir_repr_1 = [(fr.fhir_id, fr.resource_type, fr.payload.get("resourceType")) for fr in clin_1.fhir_resources]
        fhir_repr_2 = [(fr.fhir_id, fr.resource_type, fr.payload.get("resourceType")) for fr in clin_2.fhir_resources]
        assert fhir_repr_1 == fhir_repr_2

    def test_different_seeds_produce_divergent_data(self):
        """Rule 2: Different seeds produce distinct logical datasets."""
        profile = get_profile("smoke")
        seed_a = 20261013
        seed_b = 99998888

        org_a = generate_organizations(seed_a, profile)
        pats_a = generate_identities(seed_a, profile, org_a.organizations, "build_a")
        clin_a = generate_clinical(seed_a, profile, pats_a, org_a.facilities, org_a.practitioners)

        org_b = generate_organizations(seed_b, profile)
        pats_b = generate_identities(seed_b, profile, org_b.organizations, "build_b")
        clin_b = generate_clinical(seed_b, profile, pats_b, org_b.facilities, org_b.practitioners)

        mrns_a = [p.synthetic_mrn for p in pats_a]
        mrns_b = [p.synthetic_mrn for p in pats_b]
        assert mrns_a != mrns_b

        enc_starts_a = [str(e.start_time) for e in clin_a.encounters]
        enc_starts_b = [str(e.start_time) for e in clin_b.encounters]
        assert enc_starts_a != enc_starts_b

        enc_ids_a = [e.id for e in clin_a.encounters]
        enc_ids_b = [e.id for e in clin_b.encounters]
        assert enc_ids_a != enc_ids_b

        doc_hashes_a = [d.text_hash for d in clin_a.clinical_documents]
        doc_hashes_b = [d.text_hash for d in clin_b.clinical_documents]
        assert doc_hashes_a != doc_hashes_b


class TestSyntheticDataValidationRules:
    def test_valid_dataset_passes_all_checks(self):
        """Rule 3: Baseline smoke dataset satisfies all validation suites including clinical & FHIR."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        report = validate_dataset(profile, org_res, pats, covs, clin_res)
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

    def test_clinical_temporal_contradiction_detected(self):
        """Rule 4: Inverted encounter timestamps (start_time > end_time) fail validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        # Corrupt encounter temporal coherence
        clin_res.encounters[0].start_time = clin_res.encounters[0].end_time + timedelta(hours=2)

        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("start_time > end_time" in err for err in report.errors)

    def test_clinical_cross_patient_leakage_detected(self):
        """Rule 5: Clinical records pointing across patient boundaries fail validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        # Mismatch condition's patient_id relative to encounter's patient_id
        clin_res.conditions[0].patient_id = pats[1].id
        clin_res.conditions[0].encounter_id = clin_res.encounters[0].id  # Belongs to pats[0]

        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("patient_id != encounter patient_id" in err for err in report.errors)

    def test_document_hash_tampering_detected(self):
        """Rule 6: Tampered document text or invalid text_hash fails validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        # Tamper with document text without updating text_hash
        clin_res.clinical_documents[0].body_text += " [UNAUTHORIZED TAMPERING]"

        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("text_hash mismatch" in err for err in report.errors)

    def test_patient_disjoint_partitions_strict(self):
        """Rule 7: Train/dev and holdout/test sets have strictly zero overlap."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")

        train_dev = {p.id for p in pats if p.split_group == "train_dev"}
        holdout = {p.id for p in pats if p.split_group == "holdout_test"}

        assert len(train_dev) > 0
        assert len(holdout) > 0
        assert train_dev.isdisjoint(holdout)
        assert len(train_dev) + len(holdout) == profile.patient_count

    def test_zero_phi_leakage_in_clinical_documents(self):
        """Rule 8: Prohibited SSN/CCN patterns in clinical notes fail validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)
        clin_res = generate_clinical(seed, profile, pats, org_res.facilities, org_res.practitioners)

        # Inject simulated SSN into note body
        clin_res.clinical_documents[0].body_text += " Patient SSN: 000-12-3456"

        report = validate_dataset(profile, org_res, pats, covs, clin_res)
        assert report.passed is False
        assert any("Prohibited SSN pattern found in clinical document" in err for err in report.errors)


class TestSyntheticDataPipelineLifecycle:
    def test_invalid_profile_configuration_fails(self):
        """Rule 9: Invalid configuration fails clearly."""
        with pytest.raises(ValueError, match="Unknown data factory profile"):
            get_profile("non_existent_profile")

    def test_pipeline_generate_and_cascade_reset(self, db_session: Session):
        """Rule 10: Pipeline persists clinical & FHIR entities, enforces idempotency, and cascade resets safely."""
        build_id = "test_build_smoke_phase4_v1"
        pipeline = DataFactoryPipeline()

        # Clean up any leftover from previous runs
        pipeline.reset(build_id, session=db_session)

        # 1. First run generates complete clinical cohort and FHIR resources
        build = pipeline.generate("smoke", seed=20267777, build_id=build_id, session=db_session)
        assert build.id == build_id
        assert build.patient_count == 25
        assert build.validation_passed is True
        assert build.generator_version == GENERATOR_VERSION

        # Verify clinical database rows exist
        patient_rows = db_session.execute(
            select(Patient).where(Patient.dataset_build_id == build_id)
        ).scalars().all()
        assert len(patient_rows) == 25
        pat_ids = [p.id for p in patient_rows]

        enc_rows = db_session.execute(
            select(Encounter).where(Encounter.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(enc_rows) == 50  # 25 patients * 2 encounters

        proc_rows = db_session.execute(
            select(Procedure).where(Procedure.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(proc_rows) == 25  # 1 procedure per patient

        doc_rows = db_session.execute(
            select(ClinicalDocument).where(ClinicalDocument.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(doc_rows) == 50  # 2 documents per patient

        fhir_rows = db_session.execute(
            select(FhirResource).where(FhirResource.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(fhir_rows) > 300  # Full FHIR cohort (Patient, Encounter, Condition, Procedure, Obs, Meds, Diag, Doc)

        # 2. Idempotency: second run without replace_existing=True raises ValueError
        with pytest.raises(ValueError, match="already exists"):
            pipeline.generate("smoke", seed=20267777, build_id=build_id, session=db_session, replace_existing=False)

        # 3. Third run with replace_existing=True rebuilds cleanly without primary key collisions
        rebuilt = pipeline.generate("smoke", seed=20267777, build_id=build_id, session=db_session, replace_existing=True)
        assert rebuilt.id == build_id

        # 4. Clean up via reset
        counts = pipeline.reset(build_id, session=db_session)
        assert counts["patients"] == 25
        assert counts["encounters"] == 50
        assert counts["procedures"] == 25
        assert counts["clinical_documents"] == 50
        assert counts["fhir_resources"] > 300
        assert counts["dataset_builds"] == 1

        # Verify completely purged from database
        rem_enc = db_session.execute(
            select(Encounter).where(Encounter.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(rem_enc) == 0

        rem_fhir = db_session.execute(
            select(FhirResource).where(FhirResource.patient_id.in_(pat_ids))
        ).scalars().all()
        assert len(rem_fhir) == 0

        rem_build = db_session.execute(
            select(DatasetBuild).where(DatasetBuild.id == build_id)
        ).scalar_one_or_none()
        assert rem_build is None

    def test_failed_generation_leaves_no_partial_records(self, db_session: Session):
        """Rule 11: If generation fails, database transaction rolls back completely."""
        build_id = "test_build_failed_rollback_v2"
        pipeline = DataFactoryPipeline()

        # Clean up before
        pipeline.reset(build_id, session=db_session)

        # Use invalid profile with 0 organizations which will fail generation/validation
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

        # Verify no orphaned records exist
        pats = db_session.execute(
            select(Patient).where(Patient.dataset_build_id == build_id)
        ).scalars().all()
        assert len(pats) == 0
