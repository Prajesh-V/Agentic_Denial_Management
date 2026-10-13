"""Rigorous validation for Synthetic Data Factory: counts, foreign keys, partition disjointness,
synthetic watermarks, zero-PHI regex scans, clinical temporal coherence, normalized-to-FHIR parity,
revenue cycle financial arithmetic, and 12-category denial scenario coverage."""

import hashlib
import re
from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any

from backend.app.data_factory.config import DataFactoryProfile
from backend.app.data_factory.generators.claims import GeneratedClaimsResult
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

AUTHORITATIVE_DENIAL_CATEGORIES = {
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


def validate_dataset(
    profile: DataFactoryProfile,
    org_res: GeneratedOrganizationsResult,
    patients: list[Patient],
    coverages: list[Coverage],
    clinical_res: GeneratedClinicalResult | None = None,
    claims_res: GeneratedClaimsResult | None = None,
) -> ValidationReport:
    """Performs rigorous integrity, relationship, partition, clinical timeline, FHIR,
    and revenue cycle claims & denial validation."""
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

    if claims_res:
        actual_counts["service_codes"] = len(claims_res.service_codes)
        actual_counts["policy_versions"] = len(claims_res.policy_versions)
        actual_counts["authorizations"] = len(claims_res.authorizations)
        actual_counts["claims"] = len(claims_res.claims)
        actual_counts["claim_diagnoses"] = len(claims_res.claim_diagnoses)
        actual_counts["claim_lines"] = len(claims_res.claim_lines)
        actual_counts["remittances"] = len(claims_res.remittances)
        actual_counts["remittance_lines"] = len(claims_res.remittance_lines)
        actual_counts["denial_events"] = len(claims_res.denial_events)

    count_errors: list[str] = []
    for k, exp in expected_counts.items():
        act = actual_counts.get(k, 0)
        if act != exp:
            count_errors.append(f"Count mismatch for '{k}': expected {exp}, got {act}")

    if count_errors:
        report.errors.extend(count_errors)

    report.checks["counts"] = {
        "valid": len(count_errors) == 0,
        "expected": expected_counts,
        "actual": actual_counts,
    }

    # 2. Foreign Key and Composite Tenant Invariants
    fk_errors: list[str] = []
    org_ids = {org.id for org in org_res.organizations}
    payer_ids = {payer.id for payer in org_res.payers}
    plan_ids = {plan.id for plan in org_res.plans}
    patient_ids = {p.id for p in patients}
    patient_org_map = {p.id: p.organization_id for p in patients}

    for fac in org_res.facilities:
        if fac.organization_id not in org_ids:
            fk_errors.append(f"Facility '{fac.id}' references nonexistent organization '{fac.organization_id}'")

    for prac in org_res.practitioners:
        if prac.organization_id not in org_ids:
            fk_errors.append(f"Practitioner '{prac.id}' references nonexistent organization '{prac.organization_id}'")

    for plan in org_res.plans:
        if plan.payer_id not in payer_ids:
            fk_errors.append(f"PayerPlan '{plan.id}' references nonexistent payer '{plan.payer_id}'")

    for pat in patients:
        if pat.organization_id not in org_ids:
            fk_errors.append(f"Patient '{pat.id}' references nonexistent organization '{pat.organization_id}'")

    for cov in coverages:
        if cov.patient_id not in patient_ids:
            fk_errors.append(f"Coverage '{cov.id}' references nonexistent patient '{cov.patient_id}'")
        if cov.payer_plan_id not in plan_ids:
            fk_errors.append(f"Coverage '{cov.id}' references nonexistent plan '{cov.payer_plan_id}'")

    if fk_errors:
        report.errors.extend(fk_errors)

    report.checks["foreign_keys"] = {
        "valid": len(fk_errors) == 0,
        "error_count": len(fk_errors),
    }

    # 3. Partition Disjointness
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

        for cond in clinical_res.conditions:
            enc = enc_by_id.get(cond.encounter_id)
            if not enc:
                clinical_errors.append(f"Condition '{cond.id}' references nonexistent encounter '{cond.encounter_id}'")
            elif cond.patient_id != enc.patient_id:
                clinical_errors.append(f"Condition '{cond.id}' patient_id != encounter patient_id (composite violation)")

        for proc in clinical_res.procedures:
            enc = enc_by_id.get(proc.encounter_id)
            if not enc:
                clinical_errors.append(f"Procedure '{proc.id}' references nonexistent encounter '{proc.encounter_id}'")
            else:
                if proc.patient_id != enc.patient_id:
                    clinical_errors.append(f"Procedure '{proc.id}' patient_id != encounter patient_id")
                if not (enc.start_time <= proc.performed_time <= enc.end_time):
                    clinical_errors.append(f"Procedure '{proc.id}' performed_time outside encounter period")

        for obs in clinical_res.observations:
            enc = enc_by_id.get(obs.encounter_id)
            if not enc:
                clinical_errors.append(f"Observation '{obs.id}' references nonexistent encounter '{obs.encounter_id}'")
            elif obs.patient_id != enc.patient_id:
                clinical_errors.append(f"Observation '{obs.id}' patient_id != encounter patient_id")

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

    # 9. Claims, Remittances, Authorizations & Denial Scenarios Validation
    if claims_res:
        claims_errors: list[str] = []
        coverage_by_id = {c.id: c for c in coverages}
        claim_by_id = {c.id: c for c in claims_res.claims}
        claim_lines_by_claim: dict[Any, list] = {}
        claim_line_by_id = {cl.id: cl for cl in claims_res.claim_lines}
        remit_lines_by_remit: dict[Any, list] = {}
        remit_line_by_id = {rl.id: rl for rl in claims_res.remittance_lines}
        auth_by_id = {a.id: a for a in claims_res.authorizations}

        for cl in claims_res.claim_lines:
            claim_lines_by_claim.setdefault(cl.claim_id, []).append(cl)

        for rl in claims_res.remittance_lines:
            remit_lines_by_remit.setdefault(rl.remittance_id, []).append(rl)

        # 9a. Claim Composite & Relationship Checks
        for claim in claims_res.claims:
            if claim.patient_id not in patient_ids:
                claims_errors.append(f"Claim '{claim.id}' references nonexistent patient '{claim.patient_id}'")
            elif claim.organization_id != patient_org_map.get(claim.patient_id):
                claims_errors.append(f"Claim '{claim.id}' organization mismatch with patient organization")

            cov = coverage_by_id.get(claim.coverage_id)
            if not cov:
                claims_errors.append(f"Claim '{claim.id}' references nonexistent coverage '{claim.coverage_id}'")
            elif cov.patient_id != claim.patient_id:
                claims_errors.append(f"Claim '{claim.id}' coverage patient does not match claim patient")

            if claim.service_end_date < claim.service_start_date:
                claims_errors.append(f"Claim '{claim.id}' service_end_date < service_start_date")

            c_lines = claim_lines_by_claim.get(claim.id, [])
            line_sum = sum(l.billed_amount for l in c_lines)
            if claim.total_billed_amount != line_sum:
                claims_errors.append(
                    f"Claim '{claim.claim_number}' financial mismatch: total_billed={claim.total_billed_amount} != sum(lines)={line_sum}"
                )

        # 9b. Claim Diagnoses Invariants
        for cd in claims_res.claim_diagnoses:
            claim = claim_by_id.get(cd.claim_id)
            if not claim:
                claims_errors.append(f"ClaimDiagnosis '{cd.id}' references nonexistent claim '{cd.claim_id}'")
            elif cd.patient_id != claim.patient_id:
                claims_errors.append(f"ClaimDiagnosis '{cd.id}' patient_id != claim patient_id")

            if not (1 <= cd.diagnosis_pointer <= 12):
                claims_errors.append(f"ClaimDiagnosis '{cd.id}' diagnosis_pointer '{cd.diagnosis_pointer}' out of bounds [1, 12]")

        # 9c. Claim Lines Invariants
        for line in claims_res.claim_lines:
            claim = claim_by_id.get(line.claim_id)
            if not claim:
                claims_errors.append(f"ClaimLine '{line.id}' references nonexistent claim '{line.claim_id}'")
            if line.billed_amount < Decimal("0.00"):
                claims_errors.append(f"ClaimLine '{line.id}' has negative billed_amount '{line.billed_amount}'")
            if line.authorization_id:
                auth = auth_by_id.get(line.authorization_id)
                if not auth:
                    claims_errors.append(f"ClaimLine '{line.id}' references nonexistent authorization '{line.authorization_id}'")

        # 9d. Remittance & Remittance Line Reconciliation
        for remit in claims_res.remittances:
            r_lines = remit_lines_by_remit.get(remit.id, [])
            paid_sum = sum(rl.paid_amount for rl in r_lines)
            if remit.total_paid_amount != paid_sum:
                claims_errors.append(
                    f"Remittance '{remit.check_or_eft_number}' financial mismatch: total_paid={remit.total_paid_amount} != sum(lines)={paid_sum}"
                )

        for rl in claims_res.remittance_lines:
            cline = claim_line_by_id.get(rl.claim_line_id)
            if not cline:
                claims_errors.append(f"RemittanceLine '{rl.id}' references nonexistent claim line '{rl.claim_line_id}'")
                continue

            if rl.allowed_amount < Decimal("0.00") or rl.paid_amount < Decimal("0.00"):
                claims_errors.append(f"RemittanceLine '{rl.id}' has negative allowed or paid amount")

            reconciled = rl.paid_amount + rl.adjustment_amount
            if cline.billed_amount != reconciled:
                claims_errors.append(
                    f"RemittanceLine '{rl.id}' balance mismatch: line billed {cline.billed_amount} != paid {rl.paid_amount} + adj {rl.adjustment_amount}"
                )

        # 9e. Denial Events & 12 Authoritative Categories Coverage
        categories_found = set()
        for de in claims_res.denial_events:
            categories_found.add(de.denial_category)
            claim = claim_by_id.get(de.claim_id)
            if not claim:
                claims_errors.append(f"DenialEvent '{de.id}' references nonexistent claim '{de.claim_id}'")
            if de.claim_line_id:
                cline = claim_line_by_id.get(de.claim_line_id)
                if not cline:
                    claims_errors.append(f"DenialEvent '{de.id}' references nonexistent claim line '{de.claim_line_id}'")
                elif cline.claim_id != de.claim_id:
                    claims_errors.append(f"DenialEvent '{de.id}' claim_line_id does not belong to claim_id")

            rl = remit_line_by_id.get(de.remittance_line_id)
            if not rl:
                claims_errors.append(f"DenialEvent '{de.id}' references nonexistent remittance line '{de.remittance_line_id}'")

            if de.appeal_deadline < de.denial_date:
                claims_errors.append(f"DenialEvent '{de.id}' appeal_deadline < denial_date")

            if claim and de.denial_date < claim.service_start_date:
                claims_errors.append(f"DenialEvent '{de.id}' denial_date < claim service_start_date")

            if de.denied_amount < Decimal("0.00"):
                claims_errors.append(f"DenialEvent '{de.id}' has negative denied_amount")

        missing_categories = AUTHORITATIVE_DENIAL_CATEGORIES - categories_found
        if missing_categories:
            claims_errors.append(f"Missing required denial categories in generated dataset: {sorted(missing_categories)}")

        partial_claims = [c for c in claims_res.claims if c.status == "PARTIALLY_DENIED"]
        whole_denied_claims = [c for c in claims_res.claims if c.status == "DENIED"]
        paid_claims = [c for c in claims_res.claims if c.status == "PAID"]

        if not partial_claims:
            claims_errors.append("Dataset lacks partially denied claims")
        if not whole_denied_claims:
            claims_errors.append("Dataset lacks whole-claim denied claims")
        if not paid_claims:
            claims_errors.append("Dataset lacks fully paid claims")

        if claims_errors:
            report.errors.extend(claims_errors)

        report.checks["claims_and_denials_integrity"] = {
            "valid": len(claims_errors) == 0,
            "categories_covered": len(categories_found),
            "all_12_categories_present": len(missing_categories) == 0,
            "partial_denial_count": len(partial_claims),
            "whole_claim_denial_count": len(whole_denied_claims),
            "fully_paid_claim_count": len(paid_claims),
            "error_count": len(claims_errors),
        }

    # Final verdict
    report.passed = len(report.errors) == 0
    return report
