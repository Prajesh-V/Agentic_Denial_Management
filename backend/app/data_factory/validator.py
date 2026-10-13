"""Rigorous validation for Synthetic Data Factory: counts, foreign keys, partition disjointness,
synthetic watermarks, zero-PHI regex scans, clinical temporal coherence, and normalized-to-FHIR parity."""

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from backend.app.data_factory.config import DataFactoryProfile
from backend.app.data_factory.generators.clinical import GeneratedClinicalResult
from backend.app.data_factory.generators.organizations import GeneratedOrganizationsResult
from backend.app.db.models import Coverage, Patient


@dataclass
class ValidationReport:
    passed: bool
    checks: dict[str, Any] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
CREDIT_CARD_PATTERN = re.compile(r"\b(?:\d{4}-){3}\d{4}\b")


def validate_dataset(
    profile: DataFactoryProfile,
    org_res: GeneratedOrganizationsResult,
    patients: list[Patient],
    coverages: list[Coverage],
    clinical_res: GeneratedClinicalResult | None = None,
) -> ValidationReport:
    """Performs rigorous integrity, relationship, partition, clinical timeline, and FHIR validation."""
    report = ValidationReport(passed=True)

    # 1. Base Counts validation
    expected_counts = {
        "organizations": profile.organization_count,
        "facilities": profile.organization_count * profile.facilities_per_org,
        "practitioners": profile.organization_count * profile.practitioners_per_org,
        "payers": profile.payers_count,
        "plans": profile.payers_count * profile.plans_per_payer,
        "patients": profile.patient_count,
        "coverages": profile.patient_count,
    }
    actual_counts = {
        "organizations": len(org_res.organizations),
        "facilities": len(org_res.facilities),
        "practitioners": len(org_res.practitioners),
        "payers": len(org_res.payers),
        "plans": len(org_res.plans),
        "patients": len(patients),
        "coverages": len(coverages),
    }

    if clinical_res:
        actual_counts["encounters"] = len(clinical_res.encounters)
        actual_counts["conditions"] = len(clinical_res.conditions)
        actual_counts["procedures"] = len(clinical_res.procedures)
        actual_counts["observations"] = len(clinical_res.observations)
        actual_counts["medication_requests"] = len(clinical_res.medication_requests)
        actual_counts["diagnostic_reports"] = len(clinical_res.diagnostic_reports)
        actual_counts["clinical_documents"] = len(clinical_res.clinical_documents)
        actual_counts["fhir_resources"] = len(clinical_res.fhir_resources)

    counts_valid = True
    for entity, exp in expected_counts.items():
        act = actual_counts.get(entity, 0)
        if act != exp:
            report.errors.append(f"Count mismatch for '{entity}': expected {exp}, got {act}")
            counts_valid = False

    report.checks["counts"] = {
        "valid": counts_valid,
        "expected": expected_counts,
        "actual": actual_counts,
    }

    # 2. Foreign Key & Reference Integrity
    org_ids = {o.id for o in org_res.organizations}
    payer_ids = {p.id for p in org_res.payers}
    plan_ids = {pl.id for pl in org_res.plans}
    patient_ids = {pat.id for pat in patients}

    fk_errors: list[str] = []
    for f in org_res.facilities:
        if f.organization_id not in org_ids:
            fk_errors.append(f"Facility '{f.id}' references invalid organization '{f.organization_id}'")

    for pr in org_res.practitioners:
        if pr.organization_id not in org_ids:
            fk_errors.append(f"Practitioner '{pr.id}' references invalid organization '{pr.organization_id}'")

    for pl in org_res.plans:
        if pl.payer_id not in payer_ids:
            fk_errors.append(f"Plan '{pl.id}' references invalid payer '{pl.payer_id}'")

    for pat in patients:
        if pat.organization_id not in org_ids:
            fk_errors.append(f"Patient '{pat.id}' references invalid organization '{pat.organization_id}'")

    for cov in coverages:
        if cov.patient_id not in patient_ids:
            fk_errors.append(f"Coverage '{cov.id}' references invalid patient '{cov.patient_id}'")
        if cov.payer_plan_id not in plan_ids:
            fk_errors.append(f"Coverage '{cov.id}' references invalid plan '{cov.payer_plan_id}'")

    if fk_errors:
        report.errors.extend(fk_errors)

    report.checks["foreign_keys"] = {
        "valid": len(fk_errors) == 0,
        "error_count": len(fk_errors),
    }

    # 3. Patient Partition Disjointness
    train_dev_ids = {p.id for p in patients if p.split_group == "train_dev"}
    holdout_test_ids = {p.id for p in patients if p.split_group == "holdout_test"}

    overlap = train_dev_ids.intersection(holdout_test_ids)
    disjoint = len(overlap) == 0
    if not disjoint:
        report.errors.append(f"Partition leakage: {len(overlap)} patient IDs exist in both train_dev and holdout_test!")

    split_valid = (len(train_dev_ids) + len(holdout_test_ids)) == len(patients)
    report.checks["split_disjointness"] = {
        "valid": disjoint and split_valid,
        "train_dev_count": len(train_dev_ids),
        "holdout_test_count": len(holdout_test_ids),
        "leakage_count": len(overlap),
    }

    # 4. Synthetic Designation & Formatting
    synth_errors: list[str] = []
    for pat in patients:
        if not pat.is_synthetic:
            synth_errors.append(f"Patient '{pat.id}' is not marked is_synthetic=True")
        if not pat.synthetic_mrn.startswith("MRN-SYNTH-"):
            synth_errors.append(f"Patient '{pat.id}' MRN '{pat.synthetic_mrn}' lacks MRN-SYNTH- prefix")

    for o in org_res.organizations:
        if not o.tax_id.startswith("TX-SYNTH-"):
            synth_errors.append(f"Organization '{o.id}' tax_id '{o.tax_id}' lacks TX-SYNTH- prefix")

    for cov in coverages:
        if not cov.member_id.startswith("MEM-SYNTH-"):
            synth_errors.append(f"Coverage '{cov.id}' member_id lacks MEM-SYNTH- prefix")

    if synth_errors:
        report.errors.extend(synth_errors)

    report.checks["synthetic_designation"] = {
        "valid": len(synth_errors) == 0,
        "violations": len(synth_errors),
    }

    # 5. Zero Real-World PHI Leakage Check
    phi_violations: list[str] = []
    for pat in patients:
        for s in [pat.first_name, pat.last_name, pat.synthetic_mrn]:
            if SSN_PATTERN.search(s):
                phi_violations.append(f"Prohibited SSN pattern found in patient field: {s}")
            if CREDIT_CARD_PATTERN.search(s):
                phi_violations.append(f"Prohibited credit card pattern found in patient field: {s}")

    if clinical_res:
        for doc in clinical_res.clinical_documents:
            if SSN_PATTERN.search(doc.body_text):
                phi_violations.append(f"Prohibited SSN pattern found in clinical document: {doc.id}")
            if CREDIT_CARD_PATTERN.search(doc.body_text):
                phi_violations.append(f"Prohibited credit card pattern found in clinical document: {doc.id}")

    if phi_violations:
        report.errors.extend(phi_violations)

    report.checks["zero_phi_leakage"] = {
        "valid": len(phi_violations) == 0,
        "violations": len(phi_violations),
    }

    # 6. Demographics & Chronological Plausibility
    today = date(2026, 10, 13)
    demo_errors: list[str] = []
    for pat in patients:
        age_years = (today - pat.birth_date).days // 365
        if age_years < 18 or age_years > 100:
            demo_errors.append(f"Patient '{pat.id}' has implausible age {age_years} (DOB {pat.birth_date})")
        if pat.gender not in {"male", "female", "other"}:
            demo_errors.append(f"Patient '{pat.id}' has invalid gender '{pat.gender}'")

    if demo_errors:
        report.errors.extend(demo_errors)

    report.checks["demographics"] = {
        "valid": len(demo_errors) == 0,
        "errors": len(demo_errors),
    }

    # 7. Clinical Timeline Temporal & Relationship Coherence
    if clinical_res:
        clinical_errors: list[str] = []
        enc_by_id = {enc.id: enc for enc in clinical_res.encounters}

        for enc in clinical_res.encounters:
            if enc.start_time > enc.end_time:
                clinical_errors.append(f"Encounter '{enc.id}' has start_time > end_time")
            if enc.patient_id not in patient_ids:
                clinical_errors.append(f"Encounter '{enc.id}' references nonexistent patient '{enc.patient_id}'")

        # Check conditions
        for cond in clinical_res.conditions:
            enc = enc_by_id.get(cond.encounter_id)
            if not enc:
                clinical_errors.append(f"Condition '{cond.id}' references nonexistent encounter '{cond.encounter_id}'")
            elif cond.patient_id != enc.patient_id:
                clinical_errors.append(f"Condition '{cond.id}' patient_id != encounter patient_id (composite violation)")

        # Check procedures
        for proc in clinical_res.procedures:
            enc = enc_by_id.get(proc.encounter_id)
            if not enc:
                clinical_errors.append(f"Procedure '{proc.id}' references nonexistent encounter '{proc.encounter_id}'")
            else:
                if proc.patient_id != enc.patient_id:
                    clinical_errors.append(f"Procedure '{proc.id}' patient_id != encounter patient_id")
                if not (enc.start_time <= proc.performed_time <= enc.end_time):
                    clinical_errors.append(f"Procedure '{proc.id}' performed_time outside encounter period")

        # Check observations
        for obs in clinical_res.observations:
            enc = enc_by_id.get(obs.encounter_id)
            if not enc:
                clinical_errors.append(f"Observation '{obs.id}' references nonexistent encounter '{obs.encounter_id}'")
            elif obs.patient_id != enc.patient_id:
                clinical_errors.append(f"Observation '{obs.id}' patient_id != encounter patient_id")

        # Check clinical documents text hash & encounter linkage
        for doc in clinical_res.clinical_documents:
            enc = enc_by_id.get(doc.encounter_id)
            if not enc:
                clinical_errors.append(f"Document '{doc.id}' references nonexistent encounter '{doc.encounter_id}'")
            elif doc.patient_id != enc.patient_id:
                clinical_errors.append(f"Document '{doc.id}' patient_id != encounter patient_id")

            expected_hash = hashlib.sha256(doc.body_text.encode("utf-8")).hexdigest()
            if doc.text_hash != expected_hash:
                clinical_errors.append(f"Document '{doc.id}' text_hash mismatch")

        if clinical_errors:
            report.errors.extend(clinical_errors)

        report.checks["clinical_timeline_coherence"] = {
            "valid": len(clinical_errors) == 0,
            "error_count": len(clinical_errors),
        }

        # 8. Normalized to FHIR Parity & Integrity
        fhir_errors: list[str] = []
        expected_fhir_count = (
            len(patients)
            + len(clinical_res.encounters)
            + len(clinical_res.conditions)
            + len(clinical_res.procedures)
            + len(clinical_res.observations)
            + len(clinical_res.medication_requests)
            + len(clinical_res.diagnostic_reports)
            + len(clinical_res.clinical_documents)
        )
        actual_fhir_count = len(clinical_res.fhir_resources)
        if actual_fhir_count != expected_fhir_count:
            fhir_errors.append(
                f"FHIR resource count mismatch: expected {expected_fhir_count}, got {actual_fhir_count}"
            )

        for fr in clinical_res.fhir_resources:
            if fr.fhir_version != "R4":
                fhir_errors.append(f"FHIR resource '{fr.id}' has invalid version '{fr.fhir_version}'")
            if fr.validation_status != "VALID":
                fhir_errors.append(f"FHIR resource '{fr.id}' has non-valid status '{fr.validation_status}'")
            if "resourceType" not in fr.payload:
                fhir_errors.append(f"FHIR resource '{fr.id}' payload missing resourceType")
            if fr.payload.get("resourceType") != fr.resource_type:
                fhir_errors.append(f"FHIR resource '{fr.id}' payload resourceType mismatch")

        if fhir_errors:
            report.errors.extend(fhir_errors)

        report.checks["fhir_parity_and_integrity"] = {
            "valid": len(fhir_errors) == 0,
            "expected_count": expected_fhir_count,
            "actual_count": actual_fhir_count,
            "error_count": len(fhir_errors),
        }

    # Final verdict
    report.passed = len(report.errors) == 0
    return report
