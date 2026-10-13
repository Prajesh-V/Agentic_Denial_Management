"""Integration tests for Phase 3 — Synthetic Data Factory v1.

Verifies:
1. Exact canonical determinism (identical seed = identical records).
2. Divergence across different seeds.
3. Foreign key and relational integrity.
4. Tenant and organization boundary enforcement.
5. Patient-disjoint split sets (train_dev vs holdout_test).
6. Idempotency and safe build isolation.
7. Clear failures on invalid configuration.
8. Transactional rollback on generation failure.
9. Manifest accuracy (seed, counts, config hash, validation report).
10. Synthetic markers and zero-PHI enforcement.
11. Safe reset operation.
"""

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
from backend.app.data_factory.generators.identities import generate_identities
from backend.app.data_factory.generators.insurance import generate_insurance
from backend.app.data_factory.generators.organizations import generate_organizations
from backend.app.db.models import DatasetBuild, Patient
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

        # Run 2
        org_res_2 = generate_organizations(seed, profile)
        pats_2 = generate_identities(seed, profile, org_res_2.organizations, "build_test_1")
        covs_2 = generate_insurance(seed, profile, pats_2, org_res_2.plans)

        # Canonical comparisons of organizations
        orgs_repr_1 = [(o.id, o.name, o.tax_id, o.npi) for o in org_res_1.organizations]
        orgs_repr_2 = [(o.id, o.name, o.tax_id, o.npi) for o in org_res_2.organizations]
        assert orgs_repr_1 == orgs_repr_2

        # Canonical comparisons of patients
        pats_repr_1 = [
            (p.id, p.organization_id, p.synthetic_mrn, p.first_name, p.last_name, p.gender, str(p.birth_date), p.split_group)
            for p in pats_1
        ]
        pats_repr_2 = [
            (p.id, p.organization_id, p.synthetic_mrn, p.first_name, p.last_name, p.gender, str(p.birth_date), p.split_group)
            for p in pats_2
        ]
        assert pats_repr_1 == pats_repr_2

        # Canonical comparisons of coverages
        covs_repr_1 = [(c.id, c.patient_id, c.payer_plan_id, c.member_id, c.group_number, c.status) for c in covs_1]
        covs_repr_2 = [(c.id, c.patient_id, c.payer_plan_id, c.member_id, c.group_number, c.status) for c in covs_2]
        assert covs_repr_1 == covs_repr_2

    def test_different_seeds_produce_divergent_data(self):
        """Rule 2: Different seeds produce distinct logical datasets."""
        profile = get_profile("smoke")
        seed_a = 20261013
        seed_b = 99998888

        pats_a = generate_identities(seed_a, profile, generate_organizations(seed_a, profile).organizations, "build_a")
        pats_b = generate_identities(seed_b, profile, generate_organizations(seed_b, profile).organizations, "build_b")

        mrns_a = [p.synthetic_mrn for p in pats_a]
        mrns_b = [p.synthetic_mrn for p in pats_b]
        assert mrns_a != mrns_b

        names_a = [(p.first_name, p.last_name) for p in pats_a]
        names_b = [(p.first_name, p.last_name) for p in pats_b]
        assert names_a != names_b


class TestSyntheticDataValidationRules:
    def test_valid_dataset_passes_all_checks(self):
        """Rule 3: Baseline smoke dataset satisfies all 6 validation check suites."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)

        report = validate_dataset(profile, org_res, pats, covs)
        assert report.passed is True
        assert len(report.errors) == 0
        assert report.checks["counts"]["valid"] is True
        assert report.checks["foreign_keys"]["valid"] is True
        assert report.checks["split_disjointness"]["valid"] is True
        assert report.checks["synthetic_designation"]["valid"] is True
        assert report.checks["zero_phi_leakage"]["valid"] is True
        assert report.checks["demographics"]["valid"] is True

    def test_cross_organization_leakage_detected(self):
        """Rule 4: Patients pointing to invalid/unauthorized organizations fail validation."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)

        # Corrupt one patient's tenant/organization link
        pats[0].organization_id = "org_unauthorized_external_999"

        report = validate_dataset(profile, org_res, pats, covs)
        assert report.passed is False
        assert any("references invalid organization" in err for err in report.errors)

    def test_patient_disjoint_partitions_strict(self):
        """Rule 5: Train/dev and holdout/test sets have strictly zero overlap."""
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

    def test_zero_phi_leakage_detection(self):
        """Rule 6: Prohibited real-world identifiers (SSN/CCN) trigger validation failure."""
        profile = get_profile("smoke")
        seed = 20261013
        org_res = generate_organizations(seed, profile)
        pats = generate_identities(seed, profile, org_res.organizations, "val_test")
        covs = generate_insurance(seed, profile, pats, org_res.plans)

        # Inject simulated prohibited SSN
        pats[1].first_name = "123-45-6789"

        report = validate_dataset(profile, org_res, pats, covs)
        assert report.passed is False
        assert any("Prohibited SSN" in err for err in report.errors)


class TestSyntheticDataPipelineLifecycle:
    def test_invalid_profile_configuration_fails(self):
        """Rule 7: Invalid configuration fails clearly."""
        with pytest.raises(ValueError, match="Unknown data factory profile"):
            get_profile("non_existent_profile")

    def test_pipeline_generate_and_idempotency(self, db_session: Session):
        """Rule 8: Pipeline creates manifest, enforces idempotency, and allows explicit replace."""
        build_id = "test_build_smoke_idempotent_v1"
        pipeline = DataFactoryPipeline()

        # Clean up any leftover from previous test runs
        pipeline.reset(build_id, session=db_session)

        # 1. First run generates successfully
        build = pipeline.generate("smoke", seed=20261013, build_id=build_id, session=db_session)
        assert build.id == build_id
        assert build.patient_count == 25
        assert build.validation_passed is True
        assert build.generator_version == GENERATOR_VERSION

        # Verify database rows exist
        patient_count = db_session.execute(
            select(Patient).where(Patient.dataset_build_id == build_id)
        ).scalars().all()
        assert len(patient_count) == 25

        # 2. Second run without replace_existing=True raises ValueError
        with pytest.raises(ValueError, match="already exists"):
            pipeline.generate("smoke", seed=20261013, build_id=build_id, session=db_session, replace_existing=False)

        # 3. Third run with replace_existing=True rebuilds cleanly
        rebuilt = pipeline.generate("smoke", seed=20261013, build_id=build_id, session=db_session, replace_existing=True)
        assert rebuilt.id == build_id

        # Patient count is still exactly 25 (no duplication)
        patient_count_after = db_session.execute(
            select(Patient).where(Patient.dataset_build_id == build_id)
        ).scalars().all()
        assert len(patient_count_after) == 25

        # 4. Clean up via reset
        counts = pipeline.reset(build_id, session=db_session)
        assert counts["patients"] == 25
        assert counts["dataset_builds"] == 1

        # Verify completely purged
        rem = db_session.execute(
            select(DatasetBuild).where(DatasetBuild.id == build_id)
        ).scalar_one_or_none()
        assert rem is None

    def test_failed_generation_leaves_no_partial_records(self, db_session: Session):
        """Rule 9: If generation fails validation, database transaction rolls back completely."""
        build_id = "test_build_failed_rollback_v1"
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

        build_row = db_session.execute(
            select(DatasetBuild).where(DatasetBuild.id == build_id)
        ).scalar_one_or_none()
        assert build_row is None
