"""extend_evidence_chunks_corpus

Revision ID: 8d90fee8c001
Revises: 7c89fee8b001
Create Date: 2026-10-13 21:35:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8d90fee8c001"
down_revision: str | None = "7c89fee8b001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Alter patient_id to nullable=True
    op.alter_column(
        "evidence_chunks",
        "patient_id",
        existing_type=sa.UUID(),
        nullable=True,
    )

    # 2. Add new columns
    op.add_column("evidence_chunks", sa.Column("dataset_build_id", sa.String(length=100), nullable=True))
    op.add_column("evidence_chunks", sa.Column("evidentiary_role", sa.String(length=50), server_default="CLINICAL_SUPPORTING", nullable=False))
    op.add_column("evidence_chunks", sa.Column("payer_id", sa.UUID(), nullable=True))
    op.add_column("evidence_chunks", sa.Column("payer_policy_version_id", sa.UUID(), nullable=True))
    op.add_column("evidence_chunks", sa.Column("claim_id", sa.UUID(), nullable=True))
    op.add_column("evidence_chunks", sa.Column("denial_event_id", sa.UUID(), nullable=True))
    op.add_column("evidence_chunks", sa.Column("section_name", sa.String(length=100), nullable=True))
    op.add_column("evidence_chunks", sa.Column("source_text_offset", sa.Integer(), nullable=True))
    op.add_column("evidence_chunks", sa.Column("source_text_length", sa.Integer(), nullable=True))
    op.add_column(
        "evidence_chunks",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )

    # 3. Create indexes
    op.create_index(op.f("ix_evidence_chunks_dataset_build_id"), "evidence_chunks", ["dataset_build_id"], unique=False)
    op.create_index(op.f("ix_evidence_chunks_evidentiary_role"), "evidence_chunks", ["evidentiary_role"], unique=False)
    op.create_index(op.f("ix_evidence_chunks_payer_id"), "evidence_chunks", ["payer_id"], unique=False)
    op.create_index(op.f("ix_evidence_chunks_payer_policy_version_id"), "evidence_chunks", ["payer_policy_version_id"], unique=False)
    op.create_index(op.f("ix_evidence_chunks_claim_id"), "evidence_chunks", ["claim_id"], unique=False)
    op.create_index(op.f("ix_evidence_chunks_denial_event_id"), "evidence_chunks", ["denial_event_id"], unique=False)

    # 4. Foreign key constraints
    op.create_foreign_key(
        "fk_chunk_payer",
        "evidence_chunks",
        "payers",
        ["payer_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_chunk_payer_policy_version",
        "evidence_chunks",
        "payer_policy_versions",
        ["payer_policy_version_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_chunk_claim",
        "evidence_chunks",
        "claims",
        ["claim_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_chunk_denial_event",
        "evidence_chunks",
        "denial_events",
        ["denial_event_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_chunk_denial_claim",
        "evidence_chunks",
        "denial_events",
        ["denial_event_id", "claim_id"],
        ["id", "claim_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_chunk_claim_patient",
        "evidence_chunks",
        "claims",
        ["claim_id", "patient_id"],
        ["id", "patient_id"],
        ondelete="CASCADE",
    )

    # 5. Drop old check constraints and unique constraint
    op.drop_constraint("ck_chunk_source_consistency", "evidence_chunks", type_="check")
    op.drop_constraint("ck_chunk_single_canonical_source", "evidence_chunks", type_="check")
    op.drop_constraint("uq_evidence_chunk_patient_src_idx", "evidence_chunks", type_="unique")

    # 6. Add updated check constraints & unique constraints
    op.create_check_constraint(
        "ck_chunk_source_consistency",
        "evidence_chunks",
        """
        (source_resource_type = 'ClinicalDocument' AND clinical_document_id IS NOT NULL AND source_resource_id = clinical_document_id) OR
        (source_resource_type = 'DiagnosticReport' AND diagnostic_report_id IS NOT NULL AND source_resource_id = diagnostic_report_id) OR
        (source_resource_type = 'Observation' AND observation_id IS NOT NULL AND source_resource_id = observation_id) OR
        (source_resource_type = 'Condition' AND condition_id IS NOT NULL AND source_resource_id = condition_id) OR
        (source_resource_type = 'Procedure' AND procedure_id IS NOT NULL AND source_resource_id = procedure_id) OR
        (source_resource_type = 'MedicationRequest' AND medication_request_id IS NOT NULL AND source_resource_id = medication_request_id) OR
        (source_resource_type = 'FhirResource' AND fhir_resource_id IS NOT NULL AND source_resource_id = fhir_resource_id) OR
        (source_resource_type = 'Encounter' AND encounter_id IS NOT NULL AND source_resource_id = encounter_id) OR
        (source_resource_type = 'PayerPolicyVersion' AND payer_policy_version_id IS NOT NULL AND source_resource_id = payer_policy_version_id) OR
        (source_resource_type = 'DenialEvent' AND denial_event_id IS NOT NULL AND source_resource_id = denial_event_id)
        """,
    )

    op.create_check_constraint(
        "ck_chunk_single_canonical_source",
        "evidence_chunks",
        """
        (CASE WHEN clinical_document_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN diagnostic_report_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN observation_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN condition_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN procedure_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN medication_request_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN fhir_resource_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN (source_resource_type = 'Encounter' AND encounter_id IS NOT NULL) THEN 1 ELSE 0 END +
         CASE WHEN payer_policy_version_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN denial_event_id IS NOT NULL THEN 1 ELSE 0 END) = 1
        """,
    )

    op.create_check_constraint(
        "ck_chunk_scope_consistency",
        "evidence_chunks",
        """
        (
            (evidentiary_role = 'PAYER_POLICY' AND source_resource_type = 'PayerPolicyVersion' AND patient_id IS NULL AND payer_id IS NOT NULL AND payer_policy_version_id IS NOT NULL AND claim_id IS NULL AND denial_event_id IS NULL)
            OR
            (evidentiary_role = 'CLINICAL_SUPPORTING' AND patient_id IS NOT NULL AND payer_id IS NULL AND payer_policy_version_id IS NULL AND denial_event_id IS NULL)
            OR
            (evidentiary_role = 'DENIAL_CONTEXT' AND source_resource_type = 'DenialEvent' AND patient_id IS NOT NULL AND claim_id IS NOT NULL AND denial_event_id IS NOT NULL AND payer_policy_version_id IS NULL)
            OR
            (evidentiary_role = 'ADMINISTRATIVE' AND patient_id IS NOT NULL AND payer_id IS NULL AND payer_policy_version_id IS NULL)
        )
        """,
    )

    op.create_unique_constraint(
        "uq_evidence_chunk_source_version_idx",
        "evidence_chunks",
        ["source_resource_id", "chunker_version", "chunk_index"],
    )

    op.create_index(
        "ix_evidence_chunk_active_source",
        "evidence_chunks",
        ["source_resource_id", "chunk_index"],
        unique=True,
        postgresql_where=sa.text("is_active = TRUE"),
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_chunk_active_source", table_name="evidence_chunks")
    op.drop_constraint("uq_evidence_chunk_source_version_idx", "evidence_chunks", type_="unique")
    op.drop_constraint("ck_chunk_scope_consistency", "evidence_chunks", type_="check")
    op.drop_constraint("ck_chunk_single_canonical_source", "evidence_chunks", type_="check")
    op.drop_constraint("ck_chunk_source_consistency", "evidence_chunks", type_="check")

    op.create_unique_constraint(
        "uq_evidence_chunk_patient_src_idx",
        "evidence_chunks",
        ["patient_id", "source_resource_id", "chunk_index"],
    )

    op.create_check_constraint(
        "ck_chunk_single_canonical_source",
        "evidence_chunks",
        """
        (CASE WHEN clinical_document_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN diagnostic_report_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN observation_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN condition_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN procedure_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN medication_request_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN fhir_resource_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN (source_resource_type = 'Encounter' AND encounter_id IS NOT NULL) THEN 1 ELSE 0 END) = 1
        """,
    )

    op.create_check_constraint(
        "ck_chunk_source_consistency",
        "evidence_chunks",
        """
        (source_resource_type = 'ClinicalDocument' AND clinical_document_id IS NOT NULL AND source_resource_id = clinical_document_id) OR
        (source_resource_type = 'DiagnosticReport' AND diagnostic_report_id IS NOT NULL AND source_resource_id = diagnostic_report_id) OR
        (source_resource_type = 'Observation' AND observation_id IS NOT NULL AND source_resource_id = observation_id) OR
        (source_resource_type = 'Condition' AND condition_id IS NOT NULL AND source_resource_id = condition_id) OR
        (source_resource_type = 'Procedure' AND procedure_id IS NOT NULL AND source_resource_id = procedure_id) OR
        (source_resource_type = 'MedicationRequest' AND medication_request_id IS NOT NULL AND source_resource_id = medication_request_id) OR
        (source_resource_type = 'FhirResource' AND fhir_resource_id IS NOT NULL AND source_resource_id = fhir_resource_id) OR
        (source_resource_type = 'Encounter' AND encounter_id IS NOT NULL AND source_resource_id = encounter_id)
        """,
    )

    op.drop_constraint("fk_chunk_claim_patient", "evidence_chunks", type_="foreignkey")
    op.drop_constraint("fk_chunk_denial_claim", "evidence_chunks", type_="foreignkey")
    op.drop_constraint("fk_chunk_denial_event", "evidence_chunks", type_="foreignkey")
    op.drop_constraint("fk_chunk_claim", "evidence_chunks", type_="foreignkey")
    op.drop_constraint("fk_chunk_payer_policy_version", "evidence_chunks", type_="foreignkey")
    op.drop_constraint("fk_chunk_payer", "evidence_chunks", type_="foreignkey")

    op.drop_index(op.f("ix_evidence_chunks_denial_event_id"), table_name="evidence_chunks")
    op.drop_index(op.f("ix_evidence_chunks_claim_id"), table_name="evidence_chunks")
    op.drop_index(op.f("ix_evidence_chunks_payer_policy_version_id"), table_name="evidence_chunks")
    op.drop_index(op.f("ix_evidence_chunks_payer_id"), table_name="evidence_chunks")
    op.drop_index(op.f("ix_evidence_chunks_evidentiary_role"), table_name="evidence_chunks")
    op.drop_index(op.f("ix_evidence_chunks_dataset_build_id"), table_name="evidence_chunks")

    op.drop_column("evidence_chunks", "metadata")
    op.drop_column("evidence_chunks", "source_text_length")
    op.drop_column("evidence_chunks", "source_text_offset")
    op.drop_column("evidence_chunks", "section_name")
    op.drop_column("evidence_chunks", "denial_event_id")
    op.drop_column("evidence_chunks", "claim_id")
    op.drop_column("evidence_chunks", "payer_policy_version_id")
    op.drop_column("evidence_chunks", "payer_id")
    op.drop_column("evidence_chunks", "evidentiary_role")
    op.drop_column("evidence_chunks", "dataset_build_id")

    op.alter_column(
        "evidence_chunks",
        "patient_id",
        existing_type=sa.UUID(),
        nullable=False,
    )
