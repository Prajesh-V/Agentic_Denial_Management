"""HL7 FHIR Release 4 (R4) package for Agentic Denial Management."""

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
from backend.app.fhir.schemas import (
    FHIRCondition,
    FHIRDiagnosticReport,
    FHIRDocumentReference,
    FHIREncounter,
    FHIRMedicationRequest,
    FHIRObservation,
    FHIRPatient,
    FHIRProcedure,
)

__all__ = [
    "FHIRCondition",
    "FHIRDiagnosticReport",
    "FHIRDocumentReference",
    "FHIREncounter",
    "FHIRMedicationRequest",
    "FHIRObservation",
    "FHIRPatient",
    "FHIRProcedure",
    "map_clinical_document_to_fhir",
    "map_condition_to_fhir",
    "map_diagnostic_report_to_fhir",
    "map_encounter_to_fhir",
    "map_medication_request_to_fhir",
    "map_observation_to_fhir",
    "map_patient_to_fhir",
    "map_procedure_to_fhir",
    "to_fhir_resource_model",
]
