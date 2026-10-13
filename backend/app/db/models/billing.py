import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.db.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class Payer(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payers"

    payer_identifier: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    line_of_business: Mapped[str] = mapped_column(String(50), nullable=False)  # COMMERCIAL, MEDICARE_ADVANTAGE, MANAGED_MEDICAID
    timely_filing_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    appeal_filing_days: Mapped[int] = mapped_column(Integer, default=180, nullable=False)

    # Relationships
    plans: Mapped[list["PayerPlan"]] = relationship("PayerPlan", back_populates="payer", cascade="all, delete-orphan")
    policy_versions: Mapped[list["PayerPolicyVersion"]] = relationship("PayerPolicyVersion", back_populates="payer", cascade="all, delete-orphan")


class PayerPlan(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payer_plans"

    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    plan_name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan_type: Mapped[str] = mapped_column(String(50), nullable=False)  # HMO, PPO, EPO, POS

    # Relationships
    payer: Mapped["Payer"] = relationship("Payer", back_populates="plans")


class Coverage(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "coverage"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("patients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    payer_plan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payer_plans.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    member_id: Mapped[str] = mapped_column(String(50), nullable=False)
    group_number: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        CheckConstraint("end_date IS NULL OR end_date >= start_date", name="ck_coverage_dates"),
        UniqueConstraint("id", "patient_id", name="uq_coverage_id_patient"),
    )

    # Relationships
    authorizations: Mapped[list["Authorization"]] = relationship("Authorization", back_populates="coverage", cascade="all, delete-orphan")


class ServiceCode(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "service_codes"

    code: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    system: Mapped[str] = mapped_column(String(50), nullable=False)  # CPT, HCPCS, ICD10_CM
    display: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(50), nullable=False)  # SURGICAL, E_AND_M, RADIOLOGY, LAB
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("system", "code", name="uq_service_code_system_code"),
    )


class Authorization(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "authorizations"

    coverage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coverage.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    auth_number: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    service_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_codes.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_code: Mapped[str] = mapped_column(String(20), nullable=False)
    requested_units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approved_units: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="APPROVED", nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        CheckConstraint("effective_end >= effective_start", name="ck_auth_dates"),
    )

    # Relationships
    coverage: Mapped["Coverage"] = relationship("Coverage", back_populates="authorizations")


class Claim(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claims"

    claim_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    coverage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coverage.id", ondelete="RESTRICT"),
        nullable=False,
    )
    rendering_practitioner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("practitioners.id", ondelete="RESTRICT"),
        nullable=False,
    )
    facility_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("facilities.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assigned_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(50), default="NEW", nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(20), default="NORMAL", nullable=False)
    service_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    service_end_date: Mapped[date] = mapped_column(Date, nullable=False)
    submission_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    total_billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "patient_id", name="uq_claim_id_patient"),
        ForeignKeyConstraint(
            ["patient_id", "organization_id"],
            ["patients.id", "patients.organization_id"],
            name="fk_claim_patient_org",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["coverage_id", "patient_id"],
            ["coverage.id", "coverage.patient_id"],
            name="fk_claim_coverage_patient",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["facility_id", "organization_id"],
            ["facilities.id", "facilities.organization_id"],
            name="fk_claim_facility_org",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["rendering_practitioner_id", "organization_id"],
            ["practitioners.id", "practitioners.organization_id"],
            name="fk_claim_practitioner_org",
            ondelete="RESTRICT",
        ),
        CheckConstraint("service_end_date >= service_start_date", name="ck_claim_service_dates"),
        CheckConstraint("total_billed_amount >= 0", name="ck_claim_total_billed_non_negative"),
    )

    # Relationships
    lines: Mapped[list["ClaimLine"]] = relationship("ClaimLine", back_populates="claim", cascade="all, delete-orphan")
    diagnoses: Mapped[list["ClaimDiagnosis"]] = relationship("ClaimDiagnosis", back_populates="claim", cascade="all, delete-orphan")
    denial_events: Mapped[list["DenialEvent"]] = relationship("DenialEvent", back_populates="claim", cascade="all, delete-orphan")


class ClaimDiagnosis(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_diagnoses"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    patient_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    diagnosis_pointer: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 to 12
    condition_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )
    diagnosis_code: Mapped[str] = mapped_column(String(20), nullable=False)
    code_system: Mapped[str] = mapped_column(String(50), default="ICD-10-CM", nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("claim_id", "diagnosis_pointer", name="uq_claim_diag_pointer"),
        CheckConstraint("diagnosis_pointer >= 1 AND diagnosis_pointer <= 12", name="ck_claim_diag_pointer_range"),
        ForeignKeyConstraint(
            ["claim_id", "patient_id"],
            ["claims.id", "claims.patient_id"],
            name="fk_claim_diag_claim_patient",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["condition_id", "patient_id"],
            ["conditions.id", "conditions.patient_id"],
            name="fk_claim_diag_condition_patient",
            ondelete="SET NULL",
        ),
    )

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="diagnoses")


class ClaimLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "claim_lines"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    line_number: Mapped[int] = mapped_column(Integer, nullable=False)
    service_code_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("service_codes.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_code: Mapped[str] = mapped_column(String(20), nullable=False)
    modifiers: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, nullable=False)
    units: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=Decimal("1.0"), nullable=False)
    billed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    diagnosis_pointers: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=lambda: [1], nullable=False)
    authorization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("authorizations.id", ondelete="SET NULL"),
        nullable=True,
    )
    service_date: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        UniqueConstraint("claim_id", "line_number", name="uq_claim_line_number"),
        UniqueConstraint("id", "claim_id", name="uq_claim_line_id_claim"),
        CheckConstraint("billed_amount >= 0", name="ck_claim_line_billed_non_negative"),
    )

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="lines")


class Remittance(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "remittances"

    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    check_or_eft_number: Mapped[str] = mapped_column(String(50), nullable=False)
    remittance_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    total_paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relationships
    lines: Mapped[list["RemittanceLine"]] = relationship("RemittanceLine", back_populates="remittance", cascade="all, delete-orphan")


class RemittanceLine(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "remittance_lines"

    remittance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remittances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    claim_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_lines.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    allowed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    adjustment_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    carc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    rarc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        CheckConstraint("allowed_amount >= 0 AND paid_amount >= 0", name="ck_remit_amounts_non_negative"),
    )

    # Relationships
    remittance: Mapped["Remittance"] = relationship("Remittance", back_populates="lines")


class DenialEvent(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "denial_events"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    claim_line_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claim_lines.id", ondelete="SET NULL"),
        nullable=True,
    )
    remittance_line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("remittance_lines.id", ondelete="RESTRICT"),
        nullable=False,
    )
    payer_policy_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payer_policy_versions.id", ondelete="SET NULL"),
        nullable=True,
    )
    denial_category: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    carc_code: Mapped[str] = mapped_column(String(20), nullable=False)
    rarc_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    denial_reason_text: Mapped[str] = mapped_column(Text, nullable=False)
    denied_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    denial_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    appeal_deadline: Mapped[date] = mapped_column(Date, nullable=False)
    is_appealable: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (
        UniqueConstraint("id", "claim_id", name="uq_denial_id_claim"),
        ForeignKeyConstraint(
            ["claim_line_id", "claim_id"],
            ["claim_lines.id", "claim_lines.claim_id"],
            name="fk_denial_claim_line_claim",
            ondelete="SET NULL",
        ),
        CheckConstraint("appeal_deadline >= denial_date", name="ck_denial_deadline_after_date"),
        CheckConstraint("denied_amount >= 0", name="ck_denied_amount_non_negative"),
    )

    # Relationships
    claim: Mapped["Claim"] = relationship("Claim", back_populates="denial_events")


class PayerPolicyVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "payer_policy_versions"

    payer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("payers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_number: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[str] = mapped_column(String(20), nullable=False)
    effective_start: Mapped[date] = mapped_column(Date, nullable=False)
    effective_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    requirements_spec: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    full_text: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        UniqueConstraint("payer_id", "policy_number", "version", name="uq_payer_policy_version"),
    )

    # Relationships
    payer: Mapped["Payer"] = relationship("Payer", back_populates="policy_versions")


class Appeal(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "appeals"

    claim_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    denial_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    appeal_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="DRAFTING", nullable=False, index=True)
    filing_deadline: Mapped[date] = mapped_column(Date, nullable=False)

    __table_args__ = (
        ForeignKeyConstraint(
            ["denial_event_id", "claim_id"],
            ["denial_events.id", "denial_events.claim_id"],
            name="fk_appeal_denial_claim",
            ondelete="RESTRICT",
        ),
    )

    # Relationships
    draft_versions: Mapped[list["AppealDraftVersion"]] = relationship("AppealDraftVersion", back_populates="appeal", cascade="all, delete-orphan")


class AppealDraftVersion(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "appeal_draft_versions"

    appeal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appeals.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    investigation_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("investigation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    author_type: Mapped[str] = mapped_column(String(20), default="AGENT", nullable=False)  # AGENT, HUMAN_ANALYST
    author_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    subject_line: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    citations: Mapped[list] = mapped_column(JSONB, default=list, nullable=False)
    grounding_status: Mapped[str] = mapped_column(String(30), default="VALIDATED", nullable=False)
    grounding_report: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("appeal_id", "version_number", name="uq_appeal_draft_version"),
        UniqueConstraint("id", "appeal_id", name="uq_appeal_draft_id_appeal"),
    )

    # Relationships
    appeal: Mapped["Appeal"] = relationship("Appeal", back_populates="draft_versions")


class AppealDecision(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "appeal_decisions"

    appeal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appeals.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appeal_draft_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    reviewer_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    decision: Mapped[str] = mapped_column(String(30), nullable=False)  # APPROVE, REQUEST_REVISION, REJECT
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_version_id", "appeal_id"],
            ["appeal_draft_versions.id", "appeal_draft_versions.appeal_id"],
            name="fk_decision_draft_appeal",
            ondelete="RESTRICT",
        ),
    )


class Export(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    __tablename__ = "exports"

    appeal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appeals.id", ondelete="RESTRICT"),
        nullable=False,
    )
    draft_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("appeal_draft_versions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    exported_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    export_format: Mapped[str] = mapped_column(String(20), nullable=False)  # PDF, MARKDOWN, JSON_BUNDLE
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    exported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    __table_args__ = (
        ForeignKeyConstraint(
            ["draft_version_id", "appeal_id"],
            ["appeal_draft_versions.id", "appeal_draft_versions.appeal_id"],
            name="fk_export_draft_appeal",
            ondelete="RESTRICT",
        ),
    )
