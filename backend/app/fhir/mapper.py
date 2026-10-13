"""Deterministic mapper transforming normalized relational records into HL7 FHIR R4 representations."""

from datetime import UTC, datetime
from uuid import UUID

from pydantic import BaseModel

from backend.app.db.models import (
    ClinicalDocument,
    Condition,
    DiagnosticReport,
    Encounter,
    FhirResource,
    MedicationRequest,
    Observation,
    Patient,
    Procedure,
)
from backend.app.fhir.schemas import (
    Attachment,
    CodeableConcept,
    Coding,
    Content,
    DocumentContext,
    DosageInstruction,
    FHIRCondition,
    FHIRDiagnosticReport,
    FHIRDocumentReference,
    FHIREncounter,
    FHIRMedicationRequest,
    FHIRObservation,
    FHIRPatient,
    FHIRProcedure,
    HumanName,
    Identifier,
    Period,
    Quantity,
    Reference,
)


def _format_datetime(dt: datetime) -> str:
    """Format datetime as ISO 8601 UTC string."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.isoformat()


def map_patient_to_fhir(patient: Patient) -> FHIRPatient:
    return FHIRPatient(
        id=f"pat-{patient.id}",
        identifier=[
            Identifier(
                system="http://hospital.synthetic.local/mrn",
                value=patient.synthetic_mrn,
            )
        ],
        name=[
            HumanName(
                use="official",
                family=patient.last_name,
                given=[patient.first_name],
            )
        ],
        gender=patient.gender,
        birthDate=patient.birth_date.isoformat(),
    )


def map_encounter_to_fhir(encounter: Encounter, org_id: str | None = None) -> FHIREncounter:
    class_coding = Coding(
        system="http://terminology.hl7.org/CodeSystem/v3-ActCode",
        code=encounter.encounter_class,
        display="ambulatory" if encounter.encounter_class == "AMB" else ("inpatient" if encounter.encounter_class == "IMP" else "emergency"),
    )
    period = Period(
        start=_format_datetime(encounter.start_time),
        end=_format_datetime(encounter.end_time) if encounter.end_time else None,
    )
    service_provider = Reference(reference=f"Organization/org-{org_id}") if org_id else None

    return FHIREncounter(
        id=f"enc-{encounter.id}",
        status=encounter.status,
        class_=class_coding,
        subject=Reference(reference=f"Patient/pat-{encounter.patient_id}"),
        period=period,
        serviceProvider=service_provider,
    )


def map_condition_to_fhir(condition: Condition) -> FHIRCondition:
    return FHIRCondition(
        id=f"cond-{condition.id}",
        clinicalStatus=CodeableConcept(
            coding=[
                Coding(
                    system="http://terminology.hl7.org/CodeSystem/condition-clinical",
                    code=condition.clinical_status,
                )
            ]
        ),
        code=CodeableConcept(
            coding=[
                Coding(
                    system=condition.code_system,
                    code=condition.code,
                    display=condition.display,
                )
            ],
            text=condition.display,
        ),
        subject=Reference(reference=f"Patient/pat-{condition.patient_id}"),
        encounter=Reference(reference=f"Encounter/enc-{condition.encounter_id}"),
        onsetDateTime=_format_datetime(condition.onset_time),
        abatementDateTime=_format_datetime(condition.abatement_time) if condition.abatement_time else None,
    )


def map_procedure_to_fhir(procedure: Procedure) -> FHIRProcedure:
    return FHIRProcedure(
        id=f"proc-{procedure.id}",
        status=procedure.status,
        code=CodeableConcept(
            coding=[
                Coding(
                    system=procedure.code_system,
                    code=procedure.code,
                    display=procedure.display,
                )
            ],
            text=procedure.display,
        ),
        subject=Reference(reference=f"Patient/pat-{procedure.patient_id}"),
        encounter=Reference(reference=f"Encounter/enc-{procedure.encounter_id}"),
        performedDateTime=_format_datetime(procedure.performed_time),
    )


def map_observation_to_fhir(observation: Observation) -> FHIRObservation:
    qty = None
    if observation.value_numeric is not None:
        qty = Quantity(
            value=float(observation.value_numeric),
            unit=observation.value_unit,
        )

    return FHIRObservation(
        id=f"obs-{observation.id}",
        status="final",
        code=CodeableConcept(
            coding=[
                Coding(
                    system=observation.code_system,
                    code=observation.code,
                    display=observation.display,
                )
            ],
            text=observation.display,
        ),
        subject=Reference(reference=f"Patient/pat-{observation.patient_id}"),
        encounter=Reference(reference=f"Encounter/enc-{observation.encounter_id}"),
        effectiveDateTime=_format_datetime(observation.effective_time),
        valueQuantity=qty,
        valueString=observation.value_string,
    )


def map_medication_request_to_fhir(med_req: MedicationRequest) -> FHIRMedicationRequest:
    return FHIRMedicationRequest(
        id=f"med-{med_req.id}",
        status=med_req.status,
        intent="order",
        medicationCodeableConcept=CodeableConcept(
            coding=[
                Coding(
                    system=med_req.code_system,
                    code=med_req.code,
                    display=med_req.display,
                )
            ],
            text=med_req.display,
        ),
        subject=Reference(reference=f"Patient/pat-{med_req.patient_id}"),
        encounter=Reference(reference=f"Encounter/enc-{med_req.encounter_id}"),
        authoredOn=_format_datetime(med_req.authored_on),
        dosageInstruction=[DosageInstruction(text=med_req.dosage_instruction)],
    )


def map_diagnostic_report_to_fhir(diag: DiagnosticReport) -> FHIRDiagnosticReport:
    return FHIRDiagnosticReport(
        id=f"diag-{diag.id}",
        status=diag.status,
        code=CodeableConcept(
            coding=[
                Coding(
                    system="http://www.ama-assn.org/go/cpt",
                    code=diag.code,
                    display=diag.display,
                )
            ],
            text=diag.display,
        ),
        subject=Reference(reference=f"Patient/pat-{diag.patient_id}"),
        encounter=Reference(reference=f"Encounter/enc-{diag.encounter_id}"),
        effectiveDateTime=_format_datetime(diag.effective_time),
        conclusion=diag.conclusion,
    )


def map_clinical_document_to_fhir(doc: ClinicalDocument) -> FHIRDocumentReference:
    return FHIRDocumentReference(
        id=f"doc-{doc.id}",
        status="current",
        docStatus="final",
        type=CodeableConcept(
            coding=[
                Coding(
                    system="http://loinc.org",
                    code="11506-3" if doc.document_type == "PROGRESS_NOTE" else "11488-4",
                    display=doc.document_type,
                )
            ],
            text=doc.title,
        ),
        subject=Reference(reference=f"Patient/pat-{doc.patient_id}"),
        context=DocumentContext(encounter=[Reference(reference=f"Encounter/enc-{doc.encounter_id}")]),
        date=_format_datetime(doc.authored_at),
        description=doc.title,
        content=[
            Content(
                attachment=Attachment(
                    contentType="text/plain",
                    data=doc.body_text,
                    title=doc.title,
                )
            )
        ],
    )


def to_fhir_resource_model(
    resource_type: str,
    fhir_id: str,
    patient_id: UUID,
    encounter_id: UUID | None,
    pydantic_resource: BaseModel,
) -> FhirResource:
    """Builds a database FhirResource instance from a validated Pydantic model."""
    payload = pydantic_resource.model_dump(by_alias=True, exclude_none=True)
    return FhirResource(
        resource_type=resource_type,
        fhir_id=fhir_id,
        patient_id=patient_id,
        encounter_id=encounter_id,
        payload=payload,
        fhir_version="R4",
        validation_status="VALID",
    )
