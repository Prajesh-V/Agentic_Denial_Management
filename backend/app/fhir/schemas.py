"""Strongly typed Pydantic v2 schemas for HL7 FHIR Release 4 (R4) resource representations."""


from pydantic import BaseModel, ConfigDict, Field


class Coding(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    system: str | None = None
    code: str | None = None
    display: str | None = None


class CodeableConcept(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    coding: list[Coding] = Field(default_factory=list)
    text: str | None = None


class Identifier(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    system: str | None = None
    value: str


class HumanName(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    use: str | None = "official"
    family: str
    given: list[str] = Field(default_factory=list)


class Period(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    start: str
    end: str | None = None


class Reference(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    reference: str
    display: str | None = None


class Quantity(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    value: float
    unit: str | None = None
    system: str | None = "http://unitsofmeasure.org"
    code: str | None = None


class Attachment(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    contentType: str | None = "text/plain"
    data: str | None = None
    title: str | None = None


class Content(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    attachment: Attachment


class DosageInstruction(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    text: str


class FHIRPatient(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "Patient"
    id: str
    identifier: list[Identifier] = Field(default_factory=list)
    name: list[HumanName] = Field(default_factory=list)
    gender: str
    birthDate: str


class FHIREncounter(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "Encounter"
    id: str
    status: str
    class_: Coding = Field(alias="class")
    subject: Reference
    period: Period
    serviceProvider: Reference | None = None


class FHIRCondition(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "Condition"
    id: str
    clinicalStatus: CodeableConcept
    code: CodeableConcept
    subject: Reference
    encounter: Reference
    onsetDateTime: str
    abatementDateTime: str | None = None


class FHIRProcedure(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "Procedure"
    id: str
    status: str
    code: CodeableConcept
    subject: Reference
    encounter: Reference
    performedDateTime: str


class FHIRObservation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "Observation"
    id: str
    status: str = "final"
    code: CodeableConcept
    subject: Reference
    encounter: Reference
    effectiveDateTime: str
    valueQuantity: Quantity | None = None
    valueString: str | None = None


class FHIRMedicationRequest(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "MedicationRequest"
    id: str
    status: str = "active"
    intent: str = "order"
    medicationCodeableConcept: CodeableConcept
    subject: Reference
    encounter: Reference
    authoredOn: str
    dosageInstruction: list[DosageInstruction] = Field(default_factory=list)


class FHIRDiagnosticReport(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "DiagnosticReport"
    id: str
    status: str = "final"
    code: CodeableConcept
    subject: Reference
    encounter: Reference
    effectiveDateTime: str
    conclusion: str


class DocumentContext(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    encounter: list[Reference] = Field(default_factory=list)


class FHIRDocumentReference(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    resourceType: str = "DocumentReference"
    id: str
    status: str = "current"
    docStatus: str = "final"
    type: CodeableConcept
    subject: Reference
    context: DocumentContext
    date: str
    description: str
    content: list[Content] = Field(default_factory=list)
