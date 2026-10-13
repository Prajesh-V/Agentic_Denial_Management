"""Deterministic generator for synthetic clinical timelines: Encounters, Conditions, Procedures,
Observations, MedicationRequests, DiagnosticReports, ClinicalDocuments, and FHIR R4 resources."""

import hashlib
import random
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID

from backend.app.data_factory.config import DataFactoryProfile, derive_subseed
from backend.app.db.models import (
    ClinicalDocument,
    Condition,
    DiagnosticReport,
    Encounter,
    Facility,
    FhirResource,
    MedicationRequest,
    Observation,
    Patient,
    Practitioner,
    Procedure,
)
from backend.app.fhir.mapper import (
    map_clinical_document_to_fhir,
    map_condition_to_fhir,
    map_diagnostic_report_to_fhir,
    map_encounter_to_fhir,
    map_medication_request_to_fhir,
    map_observation_to_fhir,
    map_patient_to_fhir,
    map_procedure_to_fhir,
    to_fhir_resource_model,
)


def deterministic_uuid(rng: random.Random) -> UUID:
    return UUID(int=rng.getrandbits(128), version=4)


@dataclass
class GeneratedClinicalResult:
    encounters: list[Encounter] = field(default_factory=list)
    conditions: list[Condition] = field(default_factory=list)
    procedures: list[Procedure] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    medication_requests: list[MedicationRequest] = field(default_factory=list)
    diagnostic_reports: list[DiagnosticReport] = field(default_factory=list)
    clinical_documents: list[ClinicalDocument] = field(default_factory=list)
    fhir_resources: list[FhirResource] = field(default_factory=list)


CLINICAL_SCENARIOS = [
    {
        "name": "Orthopedic Knee Osteoarthritis & Total Knee Arthroplasty",
        "primary_icd": ("M17.11", "Unilateral primary osteoarthritis, right knee"),
        "secondary_icd": ("I10", "Essential hypertension"),
        "cpt_procedure": ("27447", "Total knee arthroplasty, right"),
        "imaging_cpt": ("73562", "Radiologic examination, knee; 3 views"),
        "imaging_conclusion": "Severe tricompartmental osteoarthritis of right knee with medial joint space obliteration and osteophyte formation.",
        "med_consult": ("314076", "Meloxicam 15 mg oral tablet", "15 mg oral daily with food"),
        "med_procedure": ("866417", "Cefazolin 1g IV injection", "1000 mg IV infusion 30 minutes prior to surgical incision"),
        "vitals_obs": [
            ("8867-4", "Heart rate", 74.0, "beats/minute", None, 60.0, 100.0),
            ("8480-6", "Systolic blood pressure", 128.0, "mm[Hg]", None, 90.0, 140.0),
            ("8462-4", "Diastolic blood pressure", 78.0, "mm[Hg]", None, 60.0, 90.0),
            ("39156-5", "Body mass index (BMI)", 28.6, "kg/m2", None, 18.5, 24.9),
        ],
        "consult_doc_title": "Orthopedic Pre-Operative Consultation Note",
        "consult_doc_template": (
            "PATIENT CLINICAL CONSULTATION NOTE (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Attending: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "CHIEF COMPLAINT: Chronic, severe right knee pain refractory to conservative therapy.\n"
            "HISTORY OF PRESENT ILLNESS: Patient is an adult with multi-year progressive right knee osteoarthritic pain. "
            "Conservative modalities including physical therapy, intra-articular steroid injections, and NSAIDs have provided minimal relief. "
            "Weight-bearing radiography demonstrates grade IV tricompartmental osteoarthritis with bone-on-bone contact.\n"
            "ASSESSMENT: Unilateral primary osteoarthritis, right knee (ICD-10: M17.11).\n"
            "PLAN: Proceed with elective right Total Knee Arthroplasty (CPT: 27447). Pre-operative clearance obtained."
        ),
        "proc_doc_title": "Operative Report: Right Total Knee Arthroplasty",
        "proc_doc_template": (
            "OPERATIVE REPORT (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Surgeon: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "PREOPERATIVE DIAGNOSIS: Severe primary osteoarthritis, right knee (M17.11).\n"
            "POSTOPERATIVE DIAGNOSIS: Severe primary osteoarthritis, right knee (M17.11).\n"
            "PROCEDURE PERFORMED: Right Total Knee Arthroplasty (CPT: 27447).\n"
            "ANESTHESIA: Spinal anesthesia with peripheral nerve block.\n"
            "DESCRIPTION: Standard anterior midline skin incision and medial parapatellar arthrotomy. "
            "Severe denudation of articular cartilage noted in the medial femoral condyle and tibial plateau. "
            "Appropriate femoral and tibial bone resections executed. Modular cemented prosthetic components placed. "
            "Joint stable throughout range of motion (0-125 degrees). Blood loss minimal. Patient transferred to PACU in stable condition."
        ),
    },
    {
        "name": "Spine Lumbar Stenosis & Decompression",
        "primary_icd": ("M48.06", "Spinal stenosis, lumbar region"),
        "secondary_icd": ("M54.5", "Low back pain, unspecified"),
        "cpt_procedure": ("63047", "Laminectomy, facetectomy and foraminotomy, single vertebral segment, lumbar"),
        "imaging_cpt": ("72148", "Magnetic resonance imaging, lumbar spine; without contrast"),
        "imaging_conclusion": "Severe central spinal canal stenosis and bilateral neuroforaminal narrowing at L4-L5 due to ligamentous hypertrophy.",
        "med_consult": ("25480", "Gabapentin 300 mg oral capsule", "300 mg oral three times daily"),
        "med_procedure": ("866417", "Cefazolin 1g IV injection", "1000 mg IV infusion pre-operatively"),
        "vitals_obs": [
            ("8867-4", "Heart rate", 68.0, "beats/minute", None, 60.0, 100.0),
            ("8480-6", "Systolic blood pressure", 132.0, "mm[Hg]", None, 90.0, 140.0),
            ("8462-4", "Diastolic blood pressure", 82.0, "mm[Hg]", None, 60.0, 90.0),
            ("72514-3", "Pain severity - 0-10 verbal numeric rating", 8.0, "{score}", None, 0.0, 10.0),
        ],
        "consult_doc_title": "Spine Surgery Evaluation Note",
        "consult_doc_template": (
            "SPINE SURGICAL CONSULTATION (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Attending: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "CHIEF COMPLAINT: Neurogenic claudication and progressive lower extremity radiculopathy.\n"
            "HISTORY: Symptoms persistent for > 6 months. Lumbar MRI confirms severe central canal stenosis at L4-L5. "
            "Physical therapy and epidural steroid injections failed to improve walking tolerance.\n"
            "ASSESSMENT: Lumbar spinal canal stenosis (ICD-10: M48.06).\n"
            "PLAN: Scheduled for lumbar laminectomy decompression (CPT: 63047)."
        ),
        "proc_doc_title": "Operative Report: Lumbar L4-L5 Laminectomy Decompression",
        "proc_doc_template": (
            "OPERATIVE REPORT (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Surgeon: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "PROCEDURE: Lumbar laminectomy, bilateral facetectomy and foraminotomy L4-L5 (CPT: 63047).\n"
            "INDICATION: Refractory lumbar neurogenic claudication and L4-L5 stenosis.\n"
            "OPERATIVE SUMMARY: Posterior midline incision centered over L4-L5. Spinous process and lamina excised. "
            "Hypertrophic ligamentum flavum resected, achieving thorough decompression of the thecal sac and traversing L5 nerve roots. "
            "Hemostasis confirmed. Layered closure without complications."
        ),
    },
    {
        "name": "Cardiovascular Coronary Artery Disease & Percutaneous Intervention",
        "primary_icd": ("I25.10", "Atherosclerotic heart disease of native coronary artery"),
        "secondary_icd": ("E78.5", "Hyperlipidemia, unspecified"),
        "cpt_procedure": ("93458", "Left heart catheterization with coronary angiography and stent placement"),
        "imaging_cpt": ("78452", "Myocardial perfusion imaging, tomographic (SPECT); multiple studies"),
        "imaging_conclusion": "Reversible perfusion defect in the anteroseptal myocardium consistent with critical left anterior descending ischemia.",
        "med_consult": ("617314", "Atorvastatin 80 mg oral tablet", "80 mg oral daily at bedtime"),
        "med_procedure": ("32968", "Clopidogrel 75 mg oral tablet", "300 mg oral loading dose followed by 75 mg daily"),
        "vitals_obs": [
            ("8867-4", "Heart rate", 82.0, "beats/minute", None, 60.0, 100.0),
            ("8480-6", "Systolic blood pressure", 144.0, "mm[Hg]", None, 90.0, 140.0),
            ("8462-4", "Diastolic blood pressure", 88.0, "mm[Hg]", None, 60.0, 90.0),
            ("2093-3", "Cholesterol, total in Serum", 235.0, "mg/dL", None, 125.0, 200.0),
        ],
        "consult_doc_title": "Cardiology Clinical Evaluation Note",
        "consult_doc_template": (
            "CARDIOLOGY CLINICAL NOTE (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Cardiologist: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "CHIEF COMPLAINT: Exertional angina pectoris and dyspnea on exertion.\n"
            "EVALUATION: Nuclear SPECT myocardial perfusion scan demonstrates significant reversible ischemia in the LAD territory. "
            "Resting ECG shows non-specific ST-T wave changes.\n"
            "ASSESSMENT: Native vessel coronary artery disease (ICD-10: I25.10).\n"
            "PLAN: Urgent diagnostic cardiac catheterization and ad-hoc percutaneous coronary intervention (CPT: 93458)."
        ),
        "proc_doc_title": "Cardiac Catheterization & Angioplasty Report",
        "proc_doc_template": (
            "CARDIAC CATHETERIZATION PROCEDURE REPORT (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Interventionalist: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "PROCEDURE PERFORMED: Left heart catheterization, selective coronary arteriography, and drug-eluting stent placement (CPT: 93458).\n"
            "FINDINGS: Right radial artery access. Left main normal. LAD exhibited a 90% discrete stenosis in the proximal third. "
            "Circumflex and RCA without critical obstructive disease.\n"
            "INTERVENTION: Successful deployment of a 3.5 x 18 mm everolimus-eluting stent to proximal LAD with 0% residual stenosis and TIMI 3 flow."
        ),
    },
    {
        "name": "Endocrine Type 2 Diabetes & Comprehensive Management",
        "primary_icd": ("E11.9", "Type 2 diabetes mellitus without complications"),
        "secondary_icd": ("E78.2", "Mixed hyperlipidemia"),
        "cpt_procedure": ("99214", "Office or other outpatient visit for the evaluation and management of an established patient"),
        "imaging_cpt": ("80053", "Comprehensive metabolic panel"),
        "imaging_conclusion": "Serum glucose elevated at 178 mg/dL; HbA1c 8.6%; estimated GFR > 60 mL/min/1.73m2 reflecting preserved renal clearance.",
        "med_consult": ("860975", "Metformin hydrochloride 1000 mg oral tablet", "1000 mg oral twice daily with meals"),
        "med_procedure": ("1544460", "Empagliflozin 10 mg oral tablet", "10 mg oral once daily in the morning"),
        "vitals_obs": [
            ("4548-4", "Hemoglobin A1c/Hemoglobin.total in Blood", 8.6, "%", None, 4.0, 5.6),
            ("2345-7", "Glucose in Serum/Plasma", 178.0, "mg/dL", None, 70.0, 99.0),
            ("2160-0", "Creatinine in Serum/Plasma", 1.05, "mg/dL", None, 0.7, 1.3),
            ("39156-5", "Body mass index (BMI)", 31.4, "kg/m2", None, 18.5, 24.9),
        ],
        "consult_doc_title": "Endocrinology Comprehensive Care Note",
        "consult_doc_template": (
            "ENDOCRINE CLINICAL EVALUATION (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Endocrinologist: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "CHIEF COMPLAINT: Suboptimal glycemic control with elevated home capillary glucose logs.\n"
            "CLINICAL SUMMARY: Patient presents for diabetes management. Recent HbA1c is 8.6%. "
            "No reported hypoglycemic episodes. Monofilament examination reveals intact sensory perception in bilateral lower extremities.\n"
            "ASSESSMENT: Type 2 diabetes mellitus, uncontrolled (ICD-10: E11.9).\n"
            "PLAN: Intensify medical regimen with SGLT2-inhibitor (empagliflozin). Continue metformin. Dietary consultation scheduled."
        ),
        "proc_doc_title": "Progress Note: Diabetic Treatment Follow-up",
        "proc_doc_template": (
            "PROGRESS NOTE (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Provider: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "SUBJECTIVE: Patient tolerating empagliflozin without adverse symptoms. Home glucose logs average 120-140 mg/dL.\n"
            "OBJECTIVE: Repeat POC HbA1c improved to 7.4%. Blood pressure well-controlled at 124/76 mmHg. Urine microalbumin negative.\n"
            "PLAN: Maintain current therapeutic doses. Follow-up in 3 months."
        ),
    },
    {
        "name": "Gastroenterology Colorectal Screening & Polypectomy",
        "primary_icd": ("K63.5", "Polyp of colon"),
        "secondary_icd": ("K21.9", "Gastro-esophageal reflux disease without esophagitis"),
        "cpt_procedure": ("45385", "Colonoscopy, flexible; with removal of tumor(s), polyp(s), or other lesion(s) by snare technique"),
        "imaging_cpt": ("88305", "Level IV - Surgical pathology, gross and microscopic examination"),
        "imaging_conclusion": "Tubular adenoma of transverse colon, complete resection margins verified, negative for high-grade dysplasia or malignancy.",
        "med_consult": ("312320", "Pantoprazole 40 mg oral tablet", "40 mg oral once daily before breakfast"),
        "med_procedure": ("866417", "Cefazolin 1g IV injection", "1000 mg IV infusion pre-procedure prophylaxis"),
        "vitals_obs": [
            ("8867-4", "Heart rate", 70.0, "beats/minute", None, 60.0, 100.0),
            ("8480-6", "Systolic blood pressure", 122.0, "mm[Hg]", None, 90.0, 140.0),
            ("8462-4", "Diastolic blood pressure", 76.0, "mm[Hg]", None, 60.0, 90.0),
            ("718-7", "Hemoglobin [Mass/volume] in Blood", 14.2, "g/dL", None, 13.0, 17.5),
        ],
        "consult_doc_title": "Gastroenterology Pre-Procedure Consultation",
        "consult_doc_template": (
            "GASTROENTEROLOGY EVALUATION (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Gastroenterologist: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "CHIEF COMPLAINT: Screening and diagnostic colonoscopy evaluation due to positive fecal occult blood screen.\n"
            "HISTORY: Patient reports intermittent gastroesophageal reflux well-controlled with PPI. No hematochezia or unexplained weight loss.\n"
            "ASSESSMENT: Screening for malignant neoplasm of colon / occult bleeding.\n"
            "PLAN: Scheduled for diagnostic and therapeutic flexible colonoscopy (CPT: 45385)."
        ),
        "proc_doc_title": "Endoscopy Report: Colonoscopy with Polypectomy",
        "proc_doc_template": (
            "COLONOSCOPY PROCEDURE REPORT (SYNTHETIC RECORD)\n"
            "Patient: {patient_name} | MRN: {mrn} | Date: {date}\n"
            "Endoscopist: Dr. {practitioner_name}, MD | Facility: {facility_name}\n\n"
            "PROCEDURE: Flexible colonoscopy to cecum with snare polypectomy (CPT: 45385).\n"
            "SEDATION: Moderate sedation administered with propofol.\n"
            "FINDINGS: Cecum reached and landmarks (ileocecal valve and appendiceal orifice) clearly documented. "
            "A 12 mm pedunculated polyp was identified in the mid-transverse colon. Completely excised using electrocautery snare and retrieved. "
            "Pathology submitted. Minimal bleeding, controlled with endoscopic clip. Residual mucosa normal."
        ),
    },
]


def generate_clinical(
    master_seed: int,
    profile: DataFactoryProfile,
    patients: list[Patient],
    facilities: list[Facility],
    practitioners: list[Practitioner],
) -> GeneratedClinicalResult:
    """Deterministically generates clinical timelines (Encounters, Conditions, Procedures, Observations,
    MedicationRequests, DiagnosticReports, ClinicalDocuments, and FHIRResources) for synthetic patients."""
    subseed = derive_subseed(master_seed, "clinical")
    rng = random.Random(subseed)

    result = GeneratedClinicalResult()

    # Index facilities and practitioners by organization_id
    fac_by_org = {}
    for f in facilities:
        fac_by_org.setdefault(f.organization_id, []).append(f)

    prac_by_org = {}
    for p in practitioners:
        prac_by_org.setdefault(p.organization_id, []).append(p)

    # 1. Generate FHIR Patient for each patient
    for patient in patients:
        fhir_pat = map_patient_to_fhir(patient)
        fhir_pat_row = to_fhir_resource_model(
            resource_type="Patient",
            fhir_id=fhir_pat.id,
            patient_id=patient.id,
            encounter_id=None,
            pydantic_resource=fhir_pat,
        )
        result.fhir_resources.append(fhir_pat_row)

    # 2. Generate encounters and connected clinical records per patient
    for p_idx, patient in enumerate(patients):
        scenario = CLINICAL_SCENARIOS[p_idx % len(CLINICAL_SCENARIOS)]

        org_facilities = fac_by_org.get(patient.organization_id, facilities)
        org_practitioners = prac_by_org.get(patient.organization_id, practitioners)

        facility = org_facilities[p_idx % len(org_facilities)]
        practitioner = org_practitioners[p_idx % len(org_practitioners)]

        # Patient demographics for notes
        pat_name = f"{patient.first_name} {patient.last_name}"
        prac_name = f"{practitioner.first_name} {practitioner.last_name}"
        fac_name = facility.name

        # Encounter 1: Ambulatory consultation in Spring 2025
        enc1_date = datetime(2025, 2, 1, 9, 0, tzinfo=UTC) + timedelta(days=rng.randint(1, 40), minutes=rng.randint(0, 180))
        enc1_end = enc1_date + timedelta(hours=1, minutes=15)
        enc1_id = deterministic_uuid(rng)

        enc1 = Encounter(
            id=enc1_id,
            patient_id=patient.id,
            facility_id=facility.id,
            practitioner_id=practitioner.id,
            encounter_class="AMB",
            status="finished",
            start_time=enc1_date,
            end_time=enc1_end,
        )
        result.encounters.append(enc1)

        # FHIR Encounter 1
        fhir_enc1 = map_encounter_to_fhir(enc1, org_id=str(patient.organization_id))
        result.fhir_resources.append(
            to_fhir_resource_model("Encounter", fhir_enc1.id, patient.id, enc1.id, fhir_enc1)
        )

        # Condition 1 (Primary)
        cond1_onset = enc1_date - timedelta(days=180 + rng.randint(0, 90))
        cond1 = Condition(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc1.id,
            code_system="http://hl7.org/fhir/sid/icd-10-cm",
            code=scenario["primary_icd"][0],
            display=scenario["primary_icd"][1],
            clinical_status="active",
            onset_time=cond1_onset,
        )
        result.conditions.append(cond1)
        fhir_cond1 = map_condition_to_fhir(cond1)
        result.fhir_resources.append(
            to_fhir_resource_model("Condition", fhir_cond1.id, patient.id, enc1.id, fhir_cond1)
        )

        # Condition 2 (Secondary comorbidity)
        cond2_onset = enc1_date - timedelta(days=365 + rng.randint(0, 180))
        cond2 = Condition(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc1.id,
            code_system="http://hl7.org/fhir/sid/icd-10-cm",
            code=scenario["secondary_icd"][0],
            display=scenario["secondary_icd"][1],
            clinical_status="active",
            onset_time=cond2_onset,
        )
        result.conditions.append(cond2)
        fhir_cond2 = map_condition_to_fhir(cond2)
        result.fhir_resources.append(
            to_fhir_resource_model("Condition", fhir_cond2.id, patient.id, enc1.id, fhir_cond2)
        )

        # Observations for Encounter 1
        for obs_tpl in scenario["vitals_obs"]:
            obs_id = deterministic_uuid(rng)
            obs_code, obs_disp, obs_val, obs_unit, obs_str, ref_low, ref_high = obs_tpl
            obs = Observation(
                id=obs_id,
                patient_id=patient.id,
                encounter_id=enc1.id,
                code_system="http://loinc.org",
                code=obs_code,
                display=obs_disp,
                value_numeric=obs_val,
                value_unit=obs_unit,
                value_string=obs_str,
                reference_range_low=ref_low,
                reference_range_high=ref_high,
                effective_time=enc1_date + timedelta(minutes=15),
            )
            result.observations.append(obs)
            fhir_obs = map_observation_to_fhir(obs)
            result.fhir_resources.append(
                to_fhir_resource_model("Observation", fhir_obs.id, patient.id, enc1.id, fhir_obs)
            )

        # MedicationRequest 1
        med_code, med_disp, med_dose = scenario["med_consult"]
        med1 = MedicationRequest(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc1.id,
            practitioner_id=practitioner.id,
            code_system="http://www.nlm.nih.gov/research/umls/rxnorm",
            code=med_code,
            display=med_disp,
            dosage_instruction=med_dose,
            status="active",
            authored_on=enc1_date + timedelta(minutes=45),
        )
        result.medication_requests.append(med1)
        fhir_med1 = map_medication_request_to_fhir(med1)
        result.fhir_resources.append(
            to_fhir_resource_model("MedicationRequest", fhir_med1.id, patient.id, enc1.id, fhir_med1)
        )

        # DiagnosticReport 1
        img_code, img_disp = scenario["imaging_cpt"]
        diag1 = DiagnosticReport(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc1.id,
            code=img_code,
            display=img_disp,
            status="final",
            conclusion=scenario["imaging_conclusion"],
            effective_time=enc1_date + timedelta(minutes=30),
        )
        result.diagnostic_reports.append(diag1)
        fhir_diag1 = map_diagnostic_report_to_fhir(diag1)
        result.fhir_resources.append(
            to_fhir_resource_model("DiagnosticReport", fhir_diag1.id, patient.id, enc1.id, fhir_diag1)
        )

        # ClinicalDocument 1
        doc1_body = scenario["consult_doc_template"].format(
            patient_name=pat_name,
            mrn=patient.synthetic_mrn,
            date=enc1_date.strftime("%Y-%m-%d"),
            practitioner_name=prac_name,
            facility_name=fac_name,
        )
        doc1 = ClinicalDocument(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc1.id,
            practitioner_id=practitioner.id,
            document_type="CONSULTATION",
            title=scenario["consult_doc_title"],
            body_text=doc1_body,
            text_hash=hashlib.sha256(doc1_body.encode("utf-8")).hexdigest(),
            authored_at=enc1_date + timedelta(minutes=60),
        )
        result.clinical_documents.append(doc1)
        fhir_doc1 = map_clinical_document_to_fhir(doc1)
        result.fhir_resources.append(
            to_fhir_resource_model("DocumentReference", fhir_doc1.id, patient.id, enc1.id, fhir_doc1)
        )

        # Encounter 2: Procedure / Inpatient / Surgical Visit in Summer/Fall 2025
        enc2_date = enc1_date + timedelta(days=rng.randint(45, 90), minutes=rng.randint(0, 120))
        enc2_end = enc2_date + timedelta(hours=6, minutes=30)
        enc2_id = deterministic_uuid(rng)

        enc2 = Encounter(
            id=enc2_id,
            patient_id=patient.id,
            facility_id=facility.id,
            practitioner_id=practitioner.id,
            encounter_class="IMP" if "Arthroplasty" in scenario["name"] or "Catheterization" in scenario["name"] else "AMB",
            status="finished",
            start_time=enc2_date,
            end_time=enc2_end,
        )
        result.encounters.append(enc2)
        fhir_enc2 = map_encounter_to_fhir(enc2, org_id=str(patient.organization_id))
        result.fhir_resources.append(
            to_fhir_resource_model("Encounter", fhir_enc2.id, patient.id, enc2.id, fhir_enc2)
        )

        # Procedure in Encounter 2
        proc_code, proc_disp = scenario["cpt_procedure"]
        proc_time = enc2_date + timedelta(hours=2)
        proc = Procedure(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc2.id,
            practitioner_id=practitioner.id,
            code_system="http://www.ama-assn.org/go/cpt",
            code=proc_code,
            display=proc_disp,
            status="completed",
            performed_time=proc_time,
        )
        result.procedures.append(proc)
        fhir_proc = map_procedure_to_fhir(proc)
        result.fhir_resources.append(
            to_fhir_resource_model("Procedure", fhir_proc.id, patient.id, enc2.id, fhir_proc)
        )

        # Medication in Encounter 2
        proc_med_code, proc_med_disp, proc_med_dose = scenario["med_procedure"]
        med2 = MedicationRequest(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc2.id,
            practitioner_id=practitioner.id,
            code_system="http://www.nlm.nih.gov/research/umls/rxnorm",
            code=proc_med_code,
            display=proc_med_disp,
            dosage_instruction=proc_med_dose,
            status="active",
            authored_on=enc2_date + timedelta(hours=1),
        )
        result.medication_requests.append(med2)
        fhir_med2 = map_medication_request_to_fhir(med2)
        result.fhir_resources.append(
            to_fhir_resource_model("MedicationRequest", fhir_med2.id, patient.id, enc2.id, fhir_med2)
        )

        # Post-procedure observation in Encounter 2
        obs_post = Observation(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc2.id,
            code_system="http://loinc.org",
            code="8867-4",
            display="Heart rate - recovery",
            value_numeric=76.0,
            value_unit="beats/minute",
            value_string="Regular rate post-procedure",
            reference_range_low=60.0,
            reference_range_high=100.0,
            effective_time=enc2_date + timedelta(hours=4),
        )
        result.observations.append(obs_post)
        fhir_obs_post = map_observation_to_fhir(obs_post)
        result.fhir_resources.append(
            to_fhir_resource_model("Observation", fhir_obs_post.id, patient.id, enc2.id, fhir_obs_post)
        )

        # Clinical Document 2 (Operative / Procedure Report)
        doc2_body = scenario["proc_doc_template"].format(
            patient_name=pat_name,
            mrn=patient.synthetic_mrn,
            date=enc2_date.strftime("%Y-%m-%d"),
            practitioner_name=prac_name,
            facility_name=fac_name,
        )
        doc2 = ClinicalDocument(
            id=deterministic_uuid(rng),
            patient_id=patient.id,
            encounter_id=enc2.id,
            practitioner_id=practitioner.id,
            document_type="OPERATIVE_NOTE" if "Operative" in scenario["proc_doc_title"] else "PROGRESS_NOTE",
            title=scenario["proc_doc_title"],
            body_text=doc2_body,
            text_hash=hashlib.sha256(doc2_body.encode("utf-8")).hexdigest(),
            authored_at=enc2_date + timedelta(hours=5),
        )
        result.clinical_documents.append(doc2)
        fhir_doc2 = map_clinical_document_to_fhir(doc2)
        result.fhir_resources.append(
            to_fhir_resource_model("DocumentReference", fhir_doc2.id, patient.id, enc2.id, fhir_doc2)
        )

    return result
