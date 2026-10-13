"""Deterministic generator for synthetic claims, payer policies, authorizations,
remittances, and denial events covering all 12 authoritative denial categories."""

import random
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from backend.app.data_factory.config import DataFactoryProfile, derive_subseed
from backend.app.data_factory.generators.clinical import GeneratedClinicalResult
from backend.app.data_factory.generators.organizations import GeneratedOrganizationsResult
from backend.app.db.models import (
    Authorization,
    Claim,
    ClaimDiagnosis,
    ClaimLine,
    Coverage,
    DenialEvent,
    Encounter,
    Patient,
    PayerPolicyVersion,
    Remittance,
    RemittanceLine,
    ServiceCode,
)


def deterministic_uuid(rng: random.Random) -> UUID:
    """Generate a RFC 4122 compliant UUID deterministically from a seeded RNG."""
    return UUID(int=rng.getrandbits(128), version=4)


# Reference catalog of standard service codes (CPT / HCPCS)
STANDARD_SERVICE_CODES = [
    {
        "code": "27447",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Total knee arthroplasty, right",
        "category": "Surgery",
        "billed_amount": Decimal("3500.00"),
        "allowed_amount": Decimal("2800.00"),
    },
    {
        "code": "63047",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Laminectomy, facetectomy and foraminotomy, lumbar",
        "category": "Surgery",
        "billed_amount": Decimal("4200.00"),
        "allowed_amount": Decimal("3400.00"),
    },
    {
        "code": "92928",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Percutaneous transcatheter placement of intracoronary stent(s)",
        "category": "Cardiology",
        "billed_amount": Decimal("5100.00"),
        "allowed_amount": Decimal("4100.00"),
    },
    {
        "code": "95250",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Ambulatory continuous glucose monitoring of interstitial tissue fluid",
        "category": "Medicine",
        "billed_amount": Decimal("650.00"),
        "allowed_amount": Decimal("520.00"),
    },
    {
        "code": "45385",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Colonoscopy with lesion removal by snare technique",
        "category": "Endoscopy",
        "billed_amount": Decimal("1850.00"),
        "allowed_amount": Decimal("1450.00"),
    },
    {
        "code": "99214",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Office or other outpatient visit, 30-39 minutes, moderate complexity",
        "category": "Evaluation and Management",
        "billed_amount": Decimal("225.00"),
        "allowed_amount": Decimal("180.00"),
    },
    {
        "code": "99215",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Office or other outpatient visit, 40-54 minutes, high complexity",
        "category": "Evaluation and Management",
        "billed_amount": Decimal("340.00"),
        "allowed_amount": Decimal("270.00"),
    },
    {
        "code": "73562",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Radiologic examination, knee; 3 views",
        "category": "Radiology",
        "billed_amount": Decimal("260.00"),
        "allowed_amount": Decimal("195.00"),
    },
    {
        "code": "77003",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Fluoroscopic guidance for needle placement (incidental/bundled)",
        "category": "Radiology",
        "billed_amount": Decimal("480.00"),
        "allowed_amount": Decimal("360.00"),
    },
    {
        "code": "0488T",
        "system": "http://www.ama-assn.org/go/cpt",
        "display": "Experimental/investigational cartilage graft transplantation",
        "category": "Category III",
        "billed_amount": Decimal("2900.00"),
        "allowed_amount": Decimal("0.00"),
    },
    {
        "code": "J9999",
        "system": "https://www.cms.gov/hcpcs",
        "display": "Not otherwise classified antineoplastic drugs",
        "category": "HCPCS",
        "billed_amount": Decimal("450.00"),
        "allowed_amount": Decimal("360.00"),
    },
]

# Standard synthetic payer policies catalog
SYNTHETIC_POLICY_TEMPLATES = [
    {
        "policy_number": "POL-SYNTH-ORTHO-001",
        "title": "Clinical Coverage Policy: Elective Total Knee Arthroplasty (Synthetic Policy)",
        "version": "1.0",
        "governed_code": "27447",
        "denial_category": "MED_NEC_01",
        "requirements_spec": {
            "policy_id": "POL-SYNTH-ORTHO-001",
            "effective_date": "2024-01-01",
            "required_diagnoses": ["M17.11", "M17.12", "M17.0"],
            "criteria": [
                {
                    "rule_id": "CRIT-01",
                    "description": "Severe osteoarthritic changes (Kellgren-Lawrence Grade III or IV) confirmed by standing radiographs within 6 months.",
                    "evidence_type": "diagnostic_imaging",
                },
                {
                    "rule_id": "CRIT-02",
                    "description": "Documented failure of at least 3 consecutive months of conservative therapies (e.g., physical therapy, NSAIDs, intra-articular steroid injections).",
                    "evidence_type": "clinical_progress_note",
                },
                {
                    "rule_id": "CRIT-03",
                    "description": "Prior authorization obtained at least 5 business days prior to scheduled elective procedure.",
                    "evidence_type": "prior_authorization",
                },
            ],
        },
        "full_text": (
            "[SYNTHETIC PAYER POLICY - FOR TESTING PURPOSES ONLY - NOT ACTUAL PAYER POLICY]\n"
            "Policy Number: POL-SYNTH-ORTHO-001 | Version: 1.0 | Effective: 2024-01-01\n"
            "Subject: Clinical Coverage Criteria for Elective Total Knee Arthroplasty (CPT 27447)\n\n"
            "1. DESCRIPTION: Total knee arthroplasty (TKA) is a surgical reconstruction of the knee joint indicated for severe joint destruction.\n"
            "2. COVERAGE CRITERIA: Elective TKA is considered medically necessary only when ALL of the following conditions are met:\n"
            "   a. Radiographic evidence of severe joint degeneration (Kellgren-Lawrence Grade 3 or 4 joint space narrowing, osteophytes, subchondral sclerosis).\n"
            "   b. Documented medical failure of at least three (3) months of supervised conservative management including structured physical therapy and pharmacotherapy.\n"
            "   c. Valid prior authorization on file prior to surgical admission.\n"
            "3. EXCLUSIONS: Procedures performed without prior authorization or without documented radiographic and conservative therapy trials will be denied as not medically necessary."
        ),
    },
    {
        "policy_number": "POL-SYNTH-SPINE-002",
        "title": "Clinical Coverage Policy: Lumbar Spinal Decompression & Foraminotomy (Synthetic Policy)",
        "version": "1.0",
        "governed_code": "63047",
        "denial_category": "DOC_INCOMP_03",
        "requirements_spec": {
            "policy_id": "POL-SYNTH-SPINE-002",
            "effective_date": "2024-01-01",
            "required_diagnoses": ["M48.06", "M54.5"],
            "criteria": [
                {
                    "rule_id": "CRIT-01",
                    "description": "Correlating MRI or CT demonstrating moderate-to-severe lumbar central canal or neuroforaminal stenosis.",
                    "evidence_type": "diagnostic_imaging",
                },
                {
                    "rule_id": "CRIT-02",
                    "description": "Complete operative report detailing decompressed vertebral levels, facetectomy, and surgical technique submitted with claim.",
                    "evidence_type": "operative_report",
                },
                {
                    "rule_id": "CRIT-03",
                    "description": "Pre-service prior authorization issued by payer medical review team.",
                    "evidence_type": "prior_authorization",
                },
            ],
        },
        "full_text": (
            "[SYNTHETIC PAYER POLICY - FOR TESTING PURPOSES ONLY - NOT ACTUAL PAYER POLICY]\n"
            "Policy Number: POL-SYNTH-SPINE-002 | Version: 1.0 | Effective: 2024-01-01\n"
            "Subject: Lumbar Spinal Decompression (CPT 63047) Coverage and Documentation Standards\n\n"
            "1. COVERAGE GUIDELINES: Lumbar decompression is covered for neurogenic claudication or radicular symptoms refractory to conservative therapy.\n"
            "2. MANDATORY DOCUMENTATION: Claims must include the signed operative report clearly specifying anatomical margins and decompressed levels. Missing documentation will result in claim denial."
        ),
    },
    {
        "policy_number": "POL-SYNTH-CARDIO-003",
        "title": "Clinical Coverage Policy: Percutaneous Coronary Intervention (Synthetic Policy)",
        "version": "1.0",
        "governed_code": "92928",
        "denial_category": "CLIN_CONFLICT_12",
        "requirements_spec": {
            "policy_id": "POL-SYNTH-CARDIO-003",
            "effective_date": "2024-01-01",
            "required_diagnoses": ["I25.10"],
            "criteria": [
                {
                    "rule_id": "CRIT-01",
                    "description": "Diagnostic angiography demonstrating >= 70% luminal diameter stenosis in a major epicardial coronary artery.",
                    "evidence_type": "catheterization_report",
                },
                {
                    "rule_id": "CRIT-02",
                    "description": "Consistent clinical documentation confirming ischemic symptoms concordant with angiographic lesion location.",
                    "evidence_type": "clinical_notes",
                },
            ],
        },
        "full_text": (
            "[SYNTHETIC PAYER POLICY - FOR TESTING PURPOSES ONLY - NOT ACTUAL PAYER POLICY]\n"
            "Policy Number: POL-SYNTH-CARDIO-003 | Version: 1.0 | Effective: 2024-01-01\n"
            "Subject: Percutaneous Coronary Intervention (CPT 92928)\n\n"
            "1. COVERAGE CRITERIA: Covered for hemodynamically significant stenosis with documented concordant myocardial ischemia.\n"
            "2. CONFLICTING EVIDENCE: Conflicting anatomical findings or lesion descriptions across clinical notes and angiography reports will trigger denial for clinical discrepancy."
        ),
    },
    {
        "policy_number": "POL-SYNTH-ENDO-004",
        "title": "Clinical Coverage Policy: Continuous Glucose Monitoring (Synthetic Policy)",
        "version": "1.0",
        "governed_code": "95250",
        "denial_category": "CODE_MISMATCH_04",
        "requirements_spec": {
            "policy_id": "POL-SYNTH-ENDO-004",
            "effective_date": "2024-01-01",
            "required_diagnoses": ["E11.9", "E11.65"],
            "criteria": [
                {
                    "rule_id": "CRIT-01",
                    "description": "Confirmed diagnosis of diabetes mellitus requiring insulin therapy or severe glycemic volatility.",
                    "evidence_type": "clinical_diagnosis",
                },
            ],
        },
        "full_text": (
            "[SYNTHETIC PAYER POLICY - FOR TESTING PURPOSES ONLY - NOT ACTUAL PAYER POLICY]\n"
            "Policy Number: POL-SYNTH-ENDO-004 | Version: 1.0 | Effective: 2024-01-01\n"
            "Subject: Continuous Glucose Monitoring (CPT 95250)\n\n"
            "1. CODING REQUISITES: The primary billed diagnosis code must correlate with an eligible endocrine diagnosis. Mismatched diagnostic coding will be rejected under CARC 11."
        ),
    },
    {
        "policy_number": "POL-SYNTH-GASTRO-005",
        "title": "Clinical Coverage Policy: Colorectal Screening & Diagnostic Colonoscopy (Synthetic Policy)",
        "version": "1.0",
        "governed_code": "45385",
        "denial_category": "INSUF_INFO_11",
        "requirements_spec": {
            "policy_id": "POL-SYNTH-GASTRO-005",
            "effective_date": "2024-01-01",
            "required_diagnoses": ["K63.5", "Z12.11"],
            "criteria": [
                {
                    "rule_id": "CRIT-01",
                    "description": "Colonoscopy with polypectomy requires complete endoscopic visualization and pathology analysis.",
                    "evidence_type": "pathology_report",
                },
            ],
        },
        "full_text": (
            "[SYNTHETIC PAYER POLICY - FOR TESTING PURPOSES ONLY - NOT ACTUAL PAYER POLICY]\n"
            "Policy Number: POL-SYNTH-GASTRO-005 | Version: 1.0 | Effective: 2024-01-01\n"
            "Subject: Diagnostic & Therapeutic Colonoscopy (CPT 45385)\n\n"
            "1. ADJUDICATION RULES: If submitted documentation lacks complete pathology or visualization details, an Additional Documentation Request (ADR) will be initiated."
        ),
    },
    {
        "policy_number": "POL-SYNTH-ADMIN-006",
        "title": "Administrative Billing, Bundling, and Timely Filing Guidelines (Synthetic Policy)",
        "version": "1.0",
        "governed_code": "ALL",
        "denial_category": "DUP_BUNDLE_05",
        "requirements_spec": {
            "policy_id": "POL-SYNTH-ADMIN-006",
            "effective_date": "2024-01-01",
            "criteria": [
                {
                    "rule_id": "CRIT-01",
                    "description": "NCCI surgical bundling rules enforce that incidental guidance/fluoroscopy (e.g., CPT 77003) is bundled into primary surgical procedures unless distinct anatomical site modifier 59 is justified.",
                    "evidence_type": "billing_coding",
                },
                {
                    "rule_id": "CRIT-02",
                    "description": "Claims must be received within payer contractual timely filing window (e.g., 90 or 180 days from date of service).",
                    "evidence_type": "submission_timestamp",
                },
                {
                    "rule_id": "CRIT-03",
                    "description": "Investigational/experimental Category III codes (e.g. 0488T) are excluded from benefit plan coverage.",
                    "evidence_type": "benefit_exclusion",
                },
            ],
        },
        "full_text": (
            "[SYNTHETIC PAYER POLICY - FOR TESTING PURPOSES ONLY - NOT ACTUAL PAYER POLICY]\n"
            "Policy Number: POL-SYNTH-ADMIN-006 | Version: 1.0 | Effective: 2024-01-01\n"
            "Subject: Administrative Billing, NCCI Edits, and Benefit Exclusions\n\n"
            "1. NCCI BUNDLING: Services considered integral to the comprehensive surgical package will not be reimbursed separately.\n"
            "2. TIMELY FILING: Claims submitted past contractual filing limits will be denied without member liability.\n"
            "3. EXCLUSIONS: Experimental and investigational procedures without proven clinical efficacy are excluded benefits."
        ),
    },
]


@dataclass
class GeneratedClaimsResult:
    service_codes: list[ServiceCode] = field(default_factory=list)
    policy_versions: list[PayerPolicyVersion] = field(default_factory=list)
    authorizations: list[Authorization] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    claim_diagnoses: list[ClaimDiagnosis] = field(default_factory=list)
    claim_lines: list[ClaimLine] = field(default_factory=list)
    remittances: list[Remittance] = field(default_factory=list)
    remittance_lines: list[RemittanceLine] = field(default_factory=list)
    denial_events: list[DenialEvent] = field(default_factory=list)


# The 12 authoritative denial scenarios
DENIAL_SCENARIO_TEMPLATES = [
    {
        "category": "MED_NEC_01",
        "name": "Medical necessity not established (conservative therapy duration unmet)",
        "carc_code": "50",
        "rarc_code": "N115",
        "policy_number": "POL-SYNTH-ORTHO-001",
        "service_code": "27447",
        "reason_text": "Claim denied under synthetic policy POL-SYNTH-ORTHO-001: Medical necessity criteria not established. Submitted clinical records do not document >= 3 months of failed conservative therapy prior to surgical intervention.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": False,
    },
    {
        "category": "PA_MISS_02",
        "name": "Prior authorization missing or invalid / expired",
        "carc_code": "197",
        "rarc_code": "N54",
        "policy_number": "POL-SYNTH-SPINE-002",
        "service_code": "63047",
        "reason_text": "Precertification/authorization absent or invalid on date of service under synthetic policy POL-SYNTH-SPINE-002.",
        "auth_state": "expired",
        "is_partial": False,
        "is_whole_claim": False,
    },
    {
        "category": "DOC_INCOMP_03",
        "name": "Missing or incomplete clinical documentation",
        "carc_code": "252",
        "rarc_code": "N29",
        "policy_number": "POL-SYNTH-SPINE-002",
        "service_code": "63047",
        "reason_text": "Required documentation to substantiate procedure is missing. Operative report detailing decompressed vertebral levels was not submitted.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": False,
    },
    {
        "category": "CODE_MISMATCH_04",
        "name": "Coding or documentation mismatch between diagnosis and procedure",
        "carc_code": "11",
        "rarc_code": "M64",
        "policy_number": "POL-SYNTH-ENDO-004",
        "service_code": "95250",
        "reason_text": "The primary diagnosis code is inconsistent with the procedure code billed. CPT 95250 requires documented endocrine/diabetes diagnosis pointer.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": False,
    },
    {
        "category": "DUP_BUNDLE_05",
        "name": "Duplicate or bundled service under NCCI guidelines",
        "carc_code": "97",
        "rarc_code": "M15",
        "policy_number": "POL-SYNTH-ADMIN-006",
        "service_code": "77003",
        "reason_text": "The benefit for service 77003 is included in the payment for primary procedure 63047 under NCCI bundling edits without distinct modifier.",
        "auth_state": "approved",
        "is_partial": True,  # Multi-line: line 1 paid, line 2 denied
        "is_whole_claim": False,
    },
    {
        "category": "ELIG_TIMING_06",
        "name": "Eligibility or coverage timing failure",
        "carc_code": "27",
        "rarc_code": "N30",
        "policy_number": "POL-SYNTH-ADMIN-006",
        "service_code": "99214",
        "reason_text": "Expenses incurred after coverage terminated. Patient insurance enrollment was inactive on the date of service.",
        "auth_state": "none",
        "is_partial": False,
        "is_whole_claim": True,
    },
    {
        "category": "UNTIMELY_07",
        "name": "Untimely filing past payer contractual window",
        "carc_code": "29",
        "rarc_code": "N382",
        "policy_number": "POL-SYNTH-ADMIN-006",
        "service_code": "99215",
        "reason_text": "The time limit for filing has expired. Claim was submitted past the contractual timely filing deadline from the date of service.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": True,
    },
    {
        "category": "NON_COV_08",
        "name": "Non-covered service or plan exclusion",
        "carc_code": "96",
        "rarc_code": "N425",
        "policy_number": "POL-SYNTH-ADMIN-006",
        "service_code": "0488T",
        "reason_text": "Non-covered charge. Service code 0488T is excluded from benefit plan coverage as experimental/investigational under policy POL-SYNTH-ADMIN-006.",
        "auth_state": "denied",
        "is_partial": False,
        "is_whole_claim": False,
    },
    {
        "category": "UNITS_MOD_09",
        "name": "Units or modifier inconsistency exceeding MUE daily allowance",
        "carc_code": "151",
        "rarc_code": "M51",
        "policy_number": "POL-SYNTH-ADMIN-006",
        "service_code": "J9999",
        "reason_text": "Payment adjusted because the number of units billed exceeds the maximum Medically Unlikely Edit (MUE) daily allowance.",
        "auth_state": "approved",
        "is_partial": True,  # 1 unit paid, remaining units adjusted/denied
        "is_whole_claim": False,
    },
    {
        "category": "COB_OTHER_10",
        "name": "Coordination of benefits required (primary EOB missing)",
        "carc_code": "22",
        "rarc_code": "N102",
        "policy_number": "POL-SYNTH-ADMIN-006",
        "service_code": "27447",
        "reason_text": "Payment adjusted because this care may be covered by another payer per Coordination of Benefits (COB) rules. Primary EOB required.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": True,
    },
    {
        "category": "INSUF_INFO_11",
        "name": "Insufficient information or Additional Documentation Request (ADR)",
        "carc_code": "16",
        "rarc_code": "N257",
        "policy_number": "POL-SYNTH-GASTRO-005",
        "service_code": "45385",
        "reason_text": "Claim lacks information needed for adjudication. Additional Documentation Request (ADR) issued for itemized endoscopic flowsheet.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": False,
    },
    {
        "category": "CLIN_CONFLICT_12",
        "name": "Conflicting clinical evidence in patient record",
        "carc_code": "272",
        "rarc_code": "N381",
        "policy_number": "POL-SYNTH-CARDIO-003",
        "service_code": "92928",
        "reason_text": "Coverage guidelines not met due to conflicting medical evidence in the patient record between attending progress notes and catheterization report.",
        "auth_state": "approved",
        "is_partial": False,
        "is_whole_claim": False,
    },
]


def generate_claims(
    master_seed: int,
    profile: DataFactoryProfile,
    org_res: GeneratedOrganizationsResult,
    patients: list[Patient],
    coverages: list[Coverage],
    clinical_res: GeneratedClinicalResult,
) -> GeneratedClaimsResult:
    """Deterministically generates service codes, payer policies, authorizations,
    claims, remittances, and denial events covering all 12 denial categories."""
    subseed = derive_subseed(master_seed, "claims")
    rng = random.Random(subseed)

    result = GeneratedClaimsResult()

    # 1. Service Codes reference catalog
    service_code_map: dict[str, ServiceCode] = {}
    for sc_info in STANDARD_SERVICE_CODES:
        sc = ServiceCode(
            id=deterministic_uuid(rng),
            code=sc_info["code"],
            system=sc_info["system"],
            display=sc_info["display"],
            category=sc_info["category"],
            is_active=True,
        )
        service_code_map[sc.code] = sc
        result.service_codes.append(sc)

    # 2. Synthetic Payer Policies for each Payer
    policy_map: dict[tuple[UUID, str], PayerPolicyVersion] = {}
    for payer in org_res.payers:
        for p_tmpl in SYNTHETIC_POLICY_TEMPLATES:
            pol_ver = PayerPolicyVersion(
                id=deterministic_uuid(rng),
                payer_id=payer.id,
                policy_number=p_tmpl["policy_number"],
                title=f"{payer.name} - {p_tmpl['title']}",
                version=p_tmpl["version"],
                effective_start=date(2024, 1, 1),
                effective_end=None,
                requirements_spec=p_tmpl["requirements_spec"],
                full_text=p_tmpl["full_text"],
            )
            policy_map[(payer.id, p_tmpl["policy_number"])] = pol_ver
            result.policy_versions.append(pol_ver)

    # Quick lookups for patients' related clinical data
    encounters_by_patient: dict[UUID, list[Encounter]] = {}
    for enc in clinical_res.encounters:
        encounters_by_patient.setdefault(enc.patient_id, []).append(enc)

    conditions_by_patient: dict[UUID, list] = {}
    for cond in clinical_res.conditions:
        conditions_by_patient.setdefault(cond.patient_id, []).append(cond)

    procedures_by_patient: dict[UUID, list] = {}
    for proc in clinical_res.procedures:
        procedures_by_patient.setdefault(proc.patient_id, []).append(proc)

    coverages_by_patient: dict[UUID, Coverage] = {cov.patient_id: cov for cov in coverages}

    # Plans and Payers lookups
    plan_by_id = {plan.id: plan for plan in org_res.plans}
    payer_by_id = {payer.id: payer for payer in org_res.payers}

    # Practitioners and facilities grouped by organization
    practitioners_by_org: dict[UUID, list] = {}
    for pr in org_res.practitioners:
        practitioners_by_org.setdefault(pr.organization_id, []).append(pr)

    facilities_by_org: dict[UUID, list] = {}
    for fac in org_res.facilities:
        facilities_by_org.setdefault(fac.organization_id, []).append(fac)

    # 3. Generate Claims for patients
    claim_counter = 1

    for p_idx, patient in enumerate(patients):
        cov = coverages_by_patient.get(patient.id)
        if not cov:
            continue

        plan = plan_by_id.get(cov.payer_plan_id)
        if not plan:
            continue
        payer = payer_by_id.get(plan.payer_id)
        if not payer:
            continue

        pat_encs = encounters_by_patient.get(patient.id, [])
        pat_conds = conditions_by_patient.get(patient.id, [])
        pat_procs = procedures_by_patient.get(patient.id, [])

        org_pracs = practitioners_by_org.get(patient.organization_id, [])
        org_facs = facilities_by_org.get(patient.organization_id, [])
        if not org_pracs or not org_facs or not pat_encs:
            continue

        rendering_prac = org_pracs[p_idx % len(org_pracs)]
        facility = org_facs[p_idx % len(org_facs)]

        # Select encounter for service dates
        encounter = pat_encs[1] if len(pat_encs) > 1 else pat_encs[0]
        service_start = encounter.start_time.date()
        service_end = encounter.end_time.date() if encounter.end_time else service_start

        # Check if this patient is assigned to one of the 12 denial categories
        is_denial_case = p_idx < len(DENIAL_SCENARIO_TEMPLATES)
        denial_template = DENIAL_SCENARIO_TEMPLATES[p_idx] if is_denial_case else None

        # Multi-denial demonstration scenario on Patient 11 (Claim 12):
        # Patient 11 exhibits CLIN_CONFLICT_12 on line 1 AND a secondary denial event on line 2!
        is_multi_denial_case = (denial_template is not None and denial_template["category"] == "CLIN_CONFLICT_12")

        # Determine submission date and filing timing
        if denial_template and denial_template["category"] == "UNTIMELY_07":
            # Intentional untimely filing: submission is > 210 days after service end
            submission_dt = datetime(service_end.year, service_end.month, service_end.day, 10, 0, tzinfo=UTC) + timedelta(days=215)
        else:
            # Normal prompt filing: 3-7 days after service end
            submission_dt = datetime(service_end.year, service_end.month, service_end.day, 10, 0, tzinfo=UTC) + timedelta(days=5)

        # Determine coverage timing
        if denial_template and denial_template["category"] == "ELIG_TIMING_06":
            # Intentional coverage timing failure: coverage terminated before service start
            cov.end_date = service_start - timedelta(days=15)
            cov.status = "terminated"

        claim_num = f"CLM-SYNTH-{claim_counter:04d}-{rng.randint(1000, 9999)}"
        claim_id = deterministic_uuid(rng)

        # Diagnoses setup
        primary_diag = pat_conds[0] if pat_conds else None
        secondary_diag = pat_conds[1] if len(pat_conds) > 1 else None

        claim_diagnoses: list[ClaimDiagnosis] = []
        if primary_diag:
            diag_code = primary_diag.code
            if denial_template and denial_template["category"] == "CODE_MISMATCH_04":
                diag_code = "I10"  # Essential hypertension instead of endocrine
                diag_desc = "Essential (primary) hypertension (Mismatched for CPT)"
            else:
                diag_desc = primary_diag.display or "Primary Condition"

            cd1 = ClaimDiagnosis(
                id=deterministic_uuid(rng),
                claim_id=claim_id,
                patient_id=patient.id,
                diagnosis_pointer=1,
                condition_id=primary_diag.id,
                diagnosis_code=diag_code,
                code_system="http://hl7.org/fhir/sid/icd-10-cm",
                description=diag_desc,
                is_primary=True,
            )
            claim_diagnoses.append(cd1)

        if secondary_diag:
            cd2 = ClaimDiagnosis(
                id=deterministic_uuid(rng),
                claim_id=claim_id,
                patient_id=patient.id,
                diagnosis_pointer=2,
                condition_id=secondary_diag.id,
                diagnosis_code=secondary_diag.code,
                code_system="http://hl7.org/fhir/sid/icd-10-cm",
                description=secondary_diag.display or "Secondary Condition",
                is_primary=False,
            )
            claim_diagnoses.append(cd2)

        # Lines and Prior Authorization setup
        claim_lines: list[ClaimLine] = []
        total_billed = Decimal("0.00")

        # Determine primary service code
        if denial_template:
            sc_code = denial_template["service_code"]
        elif pat_procs:
            sc_code = pat_procs[0].code
        else:
            sc_code = "99214"

        sc_obj = service_code_map.get(sc_code, service_code_map["99214"])

        # Prior Authorization
        auth: Authorization | None = None
        auth_state = denial_template["auth_state"] if denial_template else "approved"

        if auth_state != "none":
            auth_num = f"AUTH-SYNTH-{claim_counter:04d}-{p_idx + 1:04d}"
            if auth_state == "expired":
                auth_start = service_start - timedelta(days=60)
                auth_end = service_start - timedelta(days=5)  # Expired before service date
                status = "expired"
                app_units = 0
            elif auth_state == "denied":
                auth_start = service_start - timedelta(days=10)
                auth_end = service_start + timedelta(days=30)
                status = "denied"
                app_units = 0
            elif auth_state == "approved":
                auth_start = service_start - timedelta(days=14)
                auth_end = service_start + timedelta(days=60)
                status = "approved"
                app_units = 1
            else:
                auth_start = service_start - timedelta(days=5)
                auth_end = service_start + timedelta(days=30)
                status = "pending"
                app_units = 0

            auth = Authorization(
                id=deterministic_uuid(rng),
                coverage_id=cov.id,
                auth_number=auth_num,
                service_code_id=sc_obj.id,
                service_code=sc_obj.code,
                requested_units=1,
                approved_units=app_units,
                status=status,
                effective_start=auth_start,
                effective_end=auth_end,
            )
            result.authorizations.append(auth)

        # Line 1: Primary line
        line1_billed = Decimal("3500.00") if sc_code == "27447" else (
            Decimal("4200.00") if sc_code == "63047" else (
                Decimal("5100.00") if sc_code == "92928" else (
                    Decimal("1850.00") if sc_code == "45385" else Decimal("225.00")
                )
            )
        )
        if sc_code == "0488T":
            line1_billed = Decimal("2900.00")
        elif sc_code == "J9999":
            line1_billed = Decimal("450.00")

        line1_mods = ["RT"] if sc_code == "27447" else []

        cl1 = ClaimLine(
            id=deterministic_uuid(rng),
            claim_id=claim_id,
            line_number=1,
            service_code_id=sc_obj.id,
            service_code=sc_obj.code,
            modifiers=line1_mods,
            units=Decimal("1.00") if denial_template and denial_template["category"] != "UNITS_MOD_09" else Decimal("4.00"),
            billed_amount=line1_billed,
            diagnosis_pointers=[1],
            authorization_id=auth.id if (auth and auth.status == "approved") else None,
            service_date=service_start,
        )
        claim_lines.append(cl1)
        total_billed += line1_billed

        # Optional Line 2 for partial denial or multi-denial or multi-line scenario
        cl2: ClaimLine | None = None
        if denial_template and denial_template["category"] == "DUP_BUNDLE_05":
            # Multi-line bundling scenario: Line 1 (63047, paid), Line 2 (77003 fluoroscopy, bundled/denied)
            sc2_obj = service_code_map["77003"]
            line2_billed = Decimal("480.00")
            cl2 = ClaimLine(
                id=deterministic_uuid(rng),
                claim_id=claim_id,
                line_number=2,
                service_code_id=sc2_obj.id,
                service_code=sc2_obj.code,
                modifiers=[],  # Omitted modifier 59 triggers bundling edit
                units=Decimal("1.00"),
                billed_amount=line2_billed,
                diagnosis_pointers=[1],
                authorization_id=None,
                service_date=service_start,
            )
            claim_lines.append(cl2)
            total_billed += line2_billed
        elif is_multi_denial_case:
            # Multi-denial scenario: Line 2 also added and denied (e.g., secondary bundled service)
            sc2_obj = service_code_map["77003"]
            line2_billed = Decimal("480.00")
            cl2 = ClaimLine(
                id=deterministic_uuid(rng),
                claim_id=claim_id,
                line_number=2,
                service_code_id=sc2_obj.id,
                service_code=sc2_obj.code,
                modifiers=[],
                units=Decimal("1.00"),
                billed_amount=line2_billed,
                diagnosis_pointers=[1],
                authorization_id=None,
                service_date=service_start,
            )
            claim_lines.append(cl2)
            total_billed += line2_billed
        elif not is_denial_case and p_idx % 3 == 0:
            # Add secondary routine line for a paid claim (imaging 73562)
            sc2_obj = service_code_map["73562"]
            line2_billed = Decimal("260.00")
            cl2 = ClaimLine(
                id=deterministic_uuid(rng),
                claim_id=claim_id,
                line_number=2,
                service_code_id=sc2_obj.id,
                service_code=sc2_obj.code,
                modifiers=[],
                units=Decimal("1.00"),
                billed_amount=line2_billed,
                diagnosis_pointers=[1],
                authorization_id=None,
                service_date=service_start,
            )
            claim_lines.append(cl2)
            total_billed += line2_billed

        # Build Claim
        claim_status = "DENIED" if (denial_template and not denial_template["is_partial"]) else (
            "PARTIALLY_DENIED" if (denial_template and denial_template["is_partial"]) else "PAID"
        )
        claim = Claim(
            id=claim_id,
            claim_number=claim_num,
            patient_id=patient.id,
            organization_id=patient.organization_id,
            coverage_id=cov.id,
            rendering_practitioner_id=rendering_prac.id,
            facility_id=facility.id,
            assigned_user_id=None,
            status=claim_status,
            priority="NORMAL",
            service_start_date=service_start,
            service_end_date=service_end,
            submission_date=submission_dt,
            total_billed_amount=total_billed,
            currency="USD",
        )
        result.claims.append(claim)
        result.claim_diagnoses.extend(claim_diagnoses)
        result.claim_lines.extend(claim_lines)

        # 4. Remittance and RemittanceLines (835 adjudication)
        remittance_date = submission_dt.date() + timedelta(days=14)
        remit_id = deterministic_uuid(rng)
        remit_lines: list[RemittanceLine] = []
        total_paid = Decimal("0.00")

        # Adjudicate line 1
        if denial_template and not denial_template["is_partial"]:
            # Line 1 is fully denied
            remit_line1 = RemittanceLine(
                id=deterministic_uuid(rng),
                remittance_id=remit_id,
                claim_line_id=cl1.id,
                allowed_amount=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                adjustment_amount=line1_billed,
                carc_code=denial_template["carc_code"],
                rarc_code=denial_template["rarc_code"],
            )
            remit_lines.append(remit_line1)

            pol_key = (payer.id, denial_template["policy_number"])
            pol_version = policy_map.get(pol_key)
            appeal_deadline = remittance_date + timedelta(days=payer.appeal_filing_days)

            denial_ev1 = DenialEvent(
                id=deterministic_uuid(rng),
                claim_id=claim.id,
                claim_line_id=cl1.id,
                remittance_line_id=remit_line1.id,
                payer_policy_version_id=pol_version.id if pol_version else None,
                denial_category=denial_template["category"],
                carc_code=denial_template["carc_code"],
                rarc_code=denial_template["rarc_code"],
                denial_reason_text=denial_template["reason_text"],
                denied_amount=line1_billed,
                denial_date=remittance_date,
                appeal_deadline=appeal_deadline,
                is_appealable=True,
            )
            result.denial_events.append(denial_ev1)

            if is_multi_denial_case and cl2:
                # Secondary denial event on line 2 for multi-denial claim testing!
                remit_line2 = RemittanceLine(
                    id=deterministic_uuid(rng),
                    remittance_id=remit_id,
                    claim_line_id=cl2.id,
                    allowed_amount=Decimal("0.00"),
                    paid_amount=Decimal("0.00"),
                    adjustment_amount=cl2.billed_amount,
                    carc_code="97",
                    rarc_code="M15",
                )
                remit_lines.append(remit_line2)

                admin_pol = policy_map.get((payer.id, "POL-SYNTH-ADMIN-006"))
                denial_ev2 = DenialEvent(
                    id=deterministic_uuid(rng),
                    claim_id=claim.id,
                    claim_line_id=cl2.id,
                    remittance_line_id=remit_line2.id,
                    payer_policy_version_id=admin_pol.id if admin_pol else None,
                    denial_category="DUP_BUNDLE_05",
                    carc_code="97",
                    rarc_code="M15",
                    denial_reason_text="Secondary service 77003 denied as bundled into catheterization procedure.",
                    denied_amount=cl2.billed_amount,
                    denial_date=remittance_date,
                    appeal_deadline=appeal_deadline,
                    is_appealable=True,
                )
                result.denial_events.append(denial_ev2)

        elif denial_template and denial_template["category"] == "DUP_BUNDLE_05":
            # Partial denial: Line 1 is PAID, Line 2 is DENIED as bundled
            l1_allowed = Decimal("3400.00")
            l1_paid = Decimal("3400.00")
            l1_adj = line1_billed - l1_paid
            remit_line1 = RemittanceLine(
                id=deterministic_uuid(rng),
                remittance_id=remit_id,
                claim_line_id=cl1.id,
                allowed_amount=l1_allowed,
                paid_amount=l1_paid,
                adjustment_amount=l1_adj,
                carc_code=None,
                rarc_code=None,
            )
            remit_lines.append(remit_line1)
            total_paid += l1_paid

            assert cl2 is not None
            remit_line2 = RemittanceLine(
                id=deterministic_uuid(rng),
                remittance_id=remit_id,
                claim_line_id=cl2.id,
                allowed_amount=Decimal("0.00"),
                paid_amount=Decimal("0.00"),
                adjustment_amount=cl2.billed_amount,
                carc_code=denial_template["carc_code"],
                rarc_code=denial_template["rarc_code"],
            )
            remit_lines.append(remit_line2)

            pol_key = (payer.id, denial_template["policy_number"])
            pol_version = policy_map.get(pol_key)
            appeal_deadline = remittance_date + timedelta(days=payer.appeal_filing_days)

            denial_ev = DenialEvent(
                id=deterministic_uuid(rng),
                claim_id=claim.id,
                claim_line_id=cl2.id,
                remittance_line_id=remit_line2.id,
                payer_policy_version_id=pol_version.id if pol_version else None,
                denial_category=denial_template["category"],
                carc_code=denial_template["carc_code"],
                rarc_code=denial_template["rarc_code"],
                denial_reason_text=denial_template["reason_text"],
                denied_amount=cl2.billed_amount,
                denial_date=remittance_date,
                appeal_deadline=appeal_deadline,
                is_appealable=True,
            )
            result.denial_events.append(denial_ev)

        elif denial_template and denial_template["category"] == "UNITS_MOD_09":
            # Partial denial on units: 1 unit allowed/paid ($112.50), 3 units denied ($337.50)
            paid_part = Decimal("112.50")
            denied_part = line1_billed - paid_part
            remit_line1 = RemittanceLine(
                id=deterministic_uuid(rng),
                remittance_id=remit_id,
                claim_line_id=cl1.id,
                allowed_amount=paid_part,
                paid_amount=paid_part,
                adjustment_amount=denied_part,
                carc_code=denial_template["carc_code"],
                rarc_code=denial_template["rarc_code"],
            )
            remit_lines.append(remit_line1)
            total_paid += paid_part

            pol_key = (payer.id, denial_template["policy_number"])
            pol_version = policy_map.get(pol_key)
            appeal_deadline = remittance_date + timedelta(days=payer.appeal_filing_days)

            denial_ev = DenialEvent(
                id=deterministic_uuid(rng),
                claim_id=claim.id,
                claim_line_id=cl1.id,
                remittance_line_id=remit_line1.id,
                payer_policy_version_id=pol_version.id if pol_version else None,
                denial_category=denial_template["category"],
                carc_code=denial_template["carc_code"],
                rarc_code=denial_template["rarc_code"],
                denial_reason_text=denial_template["reason_text"],
                denied_amount=denied_part,
                denial_date=remittance_date,
                appeal_deadline=appeal_deadline,
                is_appealable=True,
            )
            result.denial_events.append(denial_ev)

        else:
            # Clean Paid Claim
            paid_amount = line1_billed * Decimal("0.80")
            adj_amount = line1_billed - paid_amount
            remit_line1 = RemittanceLine(
                id=deterministic_uuid(rng),
                remittance_id=remit_id,
                claim_line_id=cl1.id,
                allowed_amount=paid_amount,
                paid_amount=paid_amount,
                adjustment_amount=adj_amount,
                carc_code=None,
                rarc_code=None,
            )
            remit_lines.append(remit_line1)
            total_paid += paid_amount

            if cl2:
                cl2_paid = cl2.billed_amount * Decimal("0.80")
                cl2_adj = cl2.billed_amount - cl2_paid
                remit_line2 = RemittanceLine(
                    id=deterministic_uuid(rng),
                    remittance_id=remit_id,
                    claim_line_id=cl2.id,
                    allowed_amount=cl2_paid,
                    paid_amount=cl2_paid,
                    adjustment_amount=cl2_adj,
                    carc_code=None,
                    rarc_code=None,
                )
                remit_lines.append(remit_line2)
                total_paid += cl2_paid

        # Create Remittance record
        remittance = Remittance(
            id=remit_id,
            payer_id=payer.id,
            check_or_eft_number=f"EFT-SYNTH-{claim_counter:04d}-{p_idx + 1:04d}",
            remittance_date=remittance_date,
            total_paid_amount=total_paid,
        )
        result.remittances.append(remittance)
        result.remittance_lines.extend(remit_lines)

        claim_counter += 1

    return result
