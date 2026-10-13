"""Master pipeline orchestrator for synthetic dataset generation, clinical timelines, FHIR mapping,
transactional persistence, and validation."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.app.data_factory.config import (
    GENERATOR_VERSION,
    calculate_config_hash,
    get_profile,
)
from backend.app.data_factory.generators.clinical import generate_clinical
from backend.app.data_factory.generators.identities import generate_identities
from backend.app.data_factory.generators.insurance import generate_insurance
from backend.app.data_factory.generators.organizations import generate_organizations
from backend.app.data_factory.validator import validate_dataset
from backend.app.db.models import (
    ClinicalDocument,
    Condition,
    Coverage,
    DatasetBuild,
    DiagnosticReport,
    Encounter,
    Facility,
    FhirResource,
    MedicationRequest,
    Observation,
    Organization,
    OrganizationMembership,
    Patient,
    Payer,
    PayerPlan,
    Practitioner,
    Procedure,
    User,
    UserRole,
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

            # 3. Resolve and reconcile shared reference entities (prevent duplicates/collisions)
            logger.info("Reconciling shared reference entities...")
            for org in org_res.organizations:
                existing_org = db.execute(
                    select(Organization).where((Organization.tax_id == org.tax_id) | (Organization.npi == org.npi))
                ).scalar_one_or_none()
                if existing_org:
                    old_id = org.id
                    org.id = existing_org.id
                    for f in org_res.facilities:
                        if f.organization_id == old_id:
                            f.organization_id = existing_org.id
                    for pr in org_res.practitioners:
                        if pr.organization_id == old_id:
                            pr.organization_id = existing_org.id
                    for pat in patients:
                        if pat.organization_id == old_id:
                            pat.organization_id = existing_org.id
                    for m in org_res.memberships:
                        if m.organization_id == old_id:
                            m.organization_id = existing_org.id
                else:
                    db.add(org)

            for fac in org_res.facilities:
                existing_fac = db.execute(
                    select(Facility).where(
                        (Facility.name == fac.name) & (Facility.organization_id == fac.organization_id)
                    )
                ).scalar_one_or_none()
                if existing_fac:
                    fac.id = existing_fac.id
                else:
                    db.add(fac)

            for prac in org_res.practitioners:
                existing_prac = db.execute(
                    select(Practitioner).where(Practitioner.npi == prac.npi)
                ).scalar_one_or_none()
                if existing_prac:
                    prac.id = existing_prac.id
                else:
                    db.add(prac)

            for user in org_res.users:
                existing_user = db.execute(
                    select(User).where(User.email == user.email)
                ).scalar_one_or_none()
                if existing_user:
                    old_uid = user.id
                    user.id = existing_user.id
                    for m in org_res.memberships:
                        if m.user_id == old_uid:
                            m.user_id = existing_user.id
                    for ur in org_res.user_roles:
                        if ur.user_id == old_uid:
                            ur.user_id = existing_user.id
                else:
                    db.add(user)

            for m in org_res.memberships:
                existing_m = db.execute(
                    select(OrganizationMembership).where(
                        (OrganizationMembership.user_id == m.user_id)
                        & (OrganizationMembership.organization_id == m.organization_id)
                    )
                ).scalar_one_or_none()
                if not existing_m:
                    db.add(m)

            for ur in org_res.user_roles:
                existing_ur = db.execute(
                    select(UserRole).where((UserRole.user_id == ur.user_id) & (UserRole.role_id == ur.role_id))
                ).scalar_one_or_none()
                if not existing_ur:
                    db.add(ur)

            for payer in org_res.payers:
                existing_payer = db.execute(
                    select(Payer).where(Payer.payer_identifier == payer.payer_identifier)
                ).scalar_one_or_none()
                if existing_payer:
                    old_pid = payer.id
                    payer.id = existing_payer.id
                    for pl in org_res.plans:
                        if pl.payer_id == old_pid:
                            pl.payer_id = existing_payer.id
                else:
                    db.add(payer)

            for plan in org_res.plans:
                existing_plan = db.execute(
                    select(PayerPlan).where(
                        (PayerPlan.payer_id == plan.payer_id) & (PayerPlan.plan_name == plan.plan_name)
                    )
                ).scalar_one_or_none()
                if existing_plan:
                    old_plan_id = plan.id
                    plan.id = existing_plan.id
                    for cov in coverages:
                        if cov.payer_plan_id == old_plan_id:
                            cov.payer_plan_id = existing_plan.id
                else:
                    db.add(plan)

            db.flush()

            # 4. Generate Clinical Timelines & FHIR resources
            logger.info("Generating clinical timelines and FHIR resources...")
            clinical_res = generate_clinical(
                master_seed=seed,
                profile=profile,
                patients=patients,
                facilities=org_res.facilities,
                practitioners=org_res.practitioners,
            )

            # 5. Validation gate before commit
            logger.info("Validating generated dataset graph...")
            val_report = validate_dataset(profile, org_res, patients, coverages, clinical_res)

            if not val_report.passed:
                err_summary = "; ".join(val_report.errors[:5])
                raise RuntimeError(
                    f"Validation failed for dataset build '{target_build_id}': {err_summary}"
                )

            # 6. Transactional persistence in strict dependency order
            logger.info("Persisting patients and coverages...")
            for pat in patients:
                db.add(pat)
            db.flush()

            for cov in coverages:
                db.add(cov)
            db.flush()

            logger.info("Persisting encounters...")
            for enc in clinical_res.encounters:
                db.add(enc)
            db.flush()

            logger.info("Persisting conditions, procedures, observations, meds, reports, and documents...")
            for cond in clinical_res.conditions:
                db.add(cond)
            for proc in clinical_res.procedures:
                db.add(proc)
            for obs in clinical_res.observations:
                db.add(obs)
            for med in clinical_res.medication_requests:
                db.add(med)
            for diag in clinical_res.diagnostic_reports:
                db.add(diag)
            for doc in clinical_res.clinical_documents:
                db.add(doc)
            db.flush()

            logger.info("Persisting FHIR resources...")
            for fhir_rec in clinical_res.fhir_resources:
                db.add(fhir_rec)
            db.flush()

            logger.info("Persisting dataset build manifest...")
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

        counts = {
            "fhir_resources": 0,
            "clinical_documents": 0,
            "diagnostic_reports": 0,
            "medication_requests": 0,
            "observations": 0,
            "procedures": 0,
            "conditions": 0,
            "encounters": 0,
            "coverages": 0,
            "patients": 0,
            "dataset_builds": 0,
        }

        try:
            # 1. Fetch patient IDs for this build
            patient_ids_res = db.execute(
                select(Patient.id).where(Patient.dataset_build_id == build_id)
            ).scalars().all()
            patient_ids = list(patient_ids_res)

            if patient_ids:
                # 2. Delete FHIR resources
                del_fhir = db.execute(
                    delete(FhirResource).where(FhirResource.patient_id.in_(patient_ids))
                )
                counts["fhir_resources"] = del_fhir.rowcount or 0

                # 3. Delete clinical records (child to parent)
                del_doc = db.execute(
                    delete(ClinicalDocument).where(ClinicalDocument.patient_id.in_(patient_ids))
                )
                counts["clinical_documents"] = del_doc.rowcount or 0

                del_diag = db.execute(
                    delete(DiagnosticReport).where(DiagnosticReport.patient_id.in_(patient_ids))
                )
                counts["diagnostic_reports"] = del_diag.rowcount or 0

                del_med = db.execute(
                    delete(MedicationRequest).where(MedicationRequest.patient_id.in_(patient_ids))
                )
                counts["medication_requests"] = del_med.rowcount or 0

                del_obs = db.execute(
                    delete(Observation).where(Observation.patient_id.in_(patient_ids))
                )
                counts["observations"] = del_obs.rowcount or 0

                del_proc = db.execute(
                    delete(Procedure).where(Procedure.patient_id.in_(patient_ids))
                )
                counts["procedures"] = del_proc.rowcount or 0

                del_cond = db.execute(
                    delete(Condition).where(Condition.patient_id.in_(patient_ids))
                )
                counts["conditions"] = del_cond.rowcount or 0

                del_enc = db.execute(
                    delete(Encounter).where(Encounter.patient_id.in_(patient_ids))
                )
                counts["encounters"] = del_enc.rowcount or 0

                # 4. Delete coverages
                cov_del = db.execute(
                    delete(Coverage).where(Coverage.patient_id.in_(patient_ids))
                )
                counts["coverages"] = cov_del.rowcount or 0

            # 5. Delete patients
            pat_del = db.execute(
                delete(Patient).where(Patient.dataset_build_id == build_id)
            )
            counts["patients"] = pat_del.rowcount or 0

            # 6. Delete dataset build record
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
