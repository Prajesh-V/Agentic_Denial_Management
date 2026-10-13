import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from backend.app.data_factory.config import DataFactoryProfile
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
) -> ValidationReport:
    """Performs rigorous integrity, relationship, partition, and zero-leakage validation on generated data."""
    report = ValidationReport(passed=True)

    # 1. Counts validation
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

    # Determine final status
    report.passed = len(report.errors) == 0
    return report
