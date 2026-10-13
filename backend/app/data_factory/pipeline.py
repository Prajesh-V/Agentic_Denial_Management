"""Master pipeline orchestrator for synthetic dataset generation, transactional persistence, and validation."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.data_factory.config import (
    GENERATOR_VERSION,
    calculate_config_hash,
    get_profile,
)
from backend.app.data_factory.generators.identities import generate_identities
from backend.app.data_factory.generators.insurance import generate_insurance
from backend.app.data_factory.generators.organizations import generate_organizations
from backend.app.data_factory.validator import validate_dataset
from backend.app.db.models import (
    Coverage,
    DatasetBuild,
    Patient,
)
from backend.app.db.session import SessionLocal

logger = logging.getLogger(__name__)


class DataFactoryPipeline:
    """Master orchestrator for deterministic synthetic dataset generation and validation."""

    def __init__(self, session_factory=SessionLocal):
        self.session_factory = session_factory

    def generate(
        self,
        profile_name: str,
        seed: int = 20261013,
        build_id: str | None = None,
        session: Session | None = None,
        replace_existing: bool = False,
    ) -> DatasetBuild:
        """Executes the deterministic data factory pipeline."""
        profile = get_profile(profile_name)
        target_build_id = build_id or f"synth_{profile.name}_{seed}_v1"
        config_hash = calculate_config_hash(profile, seed)

        owns_session = session is None
        db: Session = self.session_factory() if owns_session else session

        try:
            # 1. Idempotency & build isolation check
            existing_build = db.execute(
                select(DatasetBuild).where(DatasetBuild.id == target_build_id)
            ).scalar_one_or_none()

            if existing_build:
                if replace_existing:
                    logger.info(f"Replacing existing dataset build '{target_build_id}'...")
                    self.reset(target_build_id, session=db)
                else:
                    raise ValueError(
                        f"Dataset build '{target_build_id}' already exists. "
                        "Specify replace_existing=True to rebuild or choose a distinct build_id."
                    )

            # 2. Subsystem domain generation
            logger.info(f"Generating organizations for seed={seed}, profile='{profile.name}'...")
            org_res = generate_organizations(seed, profile)

            logger.info(f"Generating identities for {profile.patient_count} patients...")
            patients = generate_identities(seed, profile, org_res.organizations, target_build_id)

            logger.info("Generating insurance coverages...")
            coverages = generate_insurance(seed, profile, patients, org_res.plans)

            # 3. Validation gate before commit
            logger.info("Validating generated dataset graph...")
            val_report = validate_dataset(profile, org_res, patients, coverages)

            if not val_report.passed:
                err_summary = "; ".join(val_report.errors[:5])
                raise RuntimeError(
                    f"Validation failed for dataset build '{target_build_id}': {err_summary}"
                )

            # 4. Transactional persistence in strict dependency order
            logger.info("Persisting entities to database in dependency order...")
            # Step 4a: Reference entities
            for ref_entity in (
                org_res.organizations
                + org_res.facilities
                + org_res.practitioners
                + org_res.users
                + org_res.memberships
                + org_res.user_roles
                + org_res.payers
                + org_res.plans
            ):
                db.merge(ref_entity)
            db.flush()

            # Step 4b: Patients (parent of coverages)
            for pat in patients:
                db.add(pat)
            db.flush()

            # Step 4c: Coverages (child of patients and plans)
            for cov in coverages:
                db.add(cov)
            db.flush()

            # Step 4d: Manifest
            dataset_build = DatasetBuild(
                id=target_build_id,
                generator_version=GENERATOR_VERSION,
                seed=seed,
                profile_name=profile.name,
                configuration_hash=config_hash,
                patient_count=len(patients),
                claim_count=0,
                validation_passed=True,
                validation_report=val_report.to_dict(),
            )
            db.add(dataset_build)

            db.commit()
            db.refresh(dataset_build)
            logger.info(f"Dataset build '{target_build_id}' committed successfully.")
            return dataset_build

        except Exception:
            db.rollback()
            raise
        finally:
            if owns_session:
                db.close()

    def reset(self, build_id: str, session: Session | None = None) -> dict[str, int]:
        """Safely rolls back and deletes all records associated with a dataset build."""
        owns_session = session is None
        db: Session = self.session_factory() if owns_session else session

        counts = {"coverages": 0, "patients": 0, "dataset_builds": 0}

        try:
            # 1. Fetch patient IDs for this build
            patient_ids_res = db.execute(
                select(Patient.id).where(Patient.dataset_build_id == build_id)
            ).scalars().all()
            patient_ids = list(patient_ids_res)

            # 2. Delete linked coverages
            if patient_ids:
                cov_del = db.execute(
                    delete(Coverage).where(Coverage.patient_id.in_(patient_ids))
                )
                counts["coverages"] = cov_del.rowcount or 0

            # 3. Delete patients
            pat_del = db.execute(
                delete(Patient).where(Patient.dataset_build_id == build_id)
            )
            counts["patients"] = pat_del.rowcount or 0

            # 4. Delete dataset build record
            build_del = db.execute(
                delete(DatasetBuild).where(DatasetBuild.id == build_id)
            )
            counts["dataset_builds"] = build_del.rowcount or 0

            db.commit()
            logger.info(f"Reset completed for build '{build_id}': {counts}")
            return counts

        except Exception:
            db.rollback()
            raise
        finally:
            if owns_session:
                db.close()
