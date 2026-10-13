import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Encounter(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "encounters"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_class: Mapped[str] = mapped_column("class", String(20), nullable=False)  # inpatient, outpatient, emergency
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="finished")
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("end_time >= start_time", name="ck_encounter_end_after_start"),
        UniqueConstraint("id", "patient_id", name="uq_encounter_id_patient"),
    )

    # Relationships
    conditions: Mapped[list["Condition"]] = relationship("Condition", back_populates="encounter", cascade="all, delete-orphan")
    procedures: Mapped[list["Procedure"]] = relationship("Procedure", back_populates="encounter", cascade="all, delete-orphan")
    observations: Mapped[list["Observation"]] = relationship("Observation", back_populates="encounter", cascade="all, delete-orphan")
    medication_requests: Mapped[list["MedicationRequest"]] = relationship("MedicationRequest", back_populates="encounter", cascade="all, delete-orphan")
    diagnostic_reports: Mapped[list["DiagnosticReport"]] = relationship("DiagnosticReport", back_populates="encounter", cascade="all, delete-orphan")
    clinical_documents: Mapped[list["ClinicalDocument"]] = relationship("ClinicalDocument", back_populates="encounter", cascade="all, delete-orphan")


class Condition(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "conditions"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    code_system: Mapped[str] = mapped_column(String(50), nullable=False, default="http://hl7.org/fhir/sid/icd-10-cm")
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    clinical_status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    onset_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    abatement_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"],
            ["encounters.id", "encounters.patient_id"],
            name="fk_condition_encounter_patient",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="conditions")


class Procedure(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "procedures"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code_system: Mapped[str] = mapped_column(String(50), nullable=False, default="http://www.ama-assn.org/go/cpt")
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="completed")
    performed_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"],
            ["encounters.id", "encounters.patient_id"],
            name="fk_procedure_encounter_patient",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="procedures")


class Observation(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "observations"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    code_system: Mapped[str] = mapped_column(String(50), nullable=False, default="http://loinc.org")
    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    value_numeric: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    value_unit: Mapped[str | None] = mapped_column(String(50), nullable=True)
    value_string: Mapped[str | None] = mapped_column(Text, nullable=True)
    reference_range_low: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    reference_range_high: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    effective_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"],
            ["encounters.id", "encounters.patient_id"],
            name="fk_observation_encounter_patient",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="observations")


class MedicationRequest(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "medication_requests"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code_system: Mapped[str] = mapped_column(String(50), nullable=False, default="http://www.nlm.nih.gov/research/umls/rxnorm")
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    dosage_instruction: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    authored_on: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"],
            ["encounters.id", "encounters.patient_id"],
            name="fk_medication_encounter_patient",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="medication_requests")


class DiagnosticReport(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "diagnostic_reports"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(50), nullable=False)
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="final")
    conclusion: Mapped[str] = mapped_column(Text, nullable=False)
    effective_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"],
            ["encounters.id", "encounters.patient_id"],
            name="fk_diag_report_encounter_patient",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="diagnostic_reports")


class ClinicalDocument(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "clinical_documents"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    document_type: Mapped[str] = mapped_column(String(50), nullable=False)  # OPERATIVE_NOTE, PROGRESS_NOTE, DISCHARGE_SUMMARY
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    authored_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["encounter_id", "patient_id"],
            ["encounters.id", "encounters.patient_id"],
            name="fk_clinical_doc_encounter_patient",
            ondelete="CASCADE",
        ),
    )

    # Relationships
    encounter: Mapped["Encounter"] = relationship("Encounter", back_populates="clinical_documents")


class FhirResource(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "fhir_resources"

    resource_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    fhir_id: Mapped[str] = mapped_column(String(64), nullable=False)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    encounter_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("encounters.id", ondelete="SET NULL"),
        nullable=True,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    fhir_version: Mapped[str] = mapped_column(String(10), default="R4", nullable=False)
    validation_status: Mapped[str] = mapped_column(String(20), default="VALID", nullable=False)

    __table_args__ = (
        UniqueConstraint("resource_type", "fhir_id", name="uq_fhir_resource_type_id"),
    )
