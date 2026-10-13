"""remediation_integrity_and_security

Revision ID: 6089fee8b997
Revises: ffdeed8bfb8b
Create Date: 2026-10-13 18:56:57.010738

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '6089fee8b997'
down_revision: str | Sequence[str] | None = 'ffdeed8bfb8b'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    # 1. Unique constraints required for composite foreign keys
    op.create_unique_constraint('uq_clinical_doc_id_patient', 'clinical_documents', ['id', 'patient_id'])
    op.create_unique_constraint('uq_diag_report_id_patient', 'diagnostic_reports', ['id', 'patient_id'])
    op.create_unique_constraint('uq_observation_id_patient', 'observations', ['id', 'patient_id'])
    op.create_unique_constraint('uq_condition_id_patient', 'conditions', ['id', 'patient_id'])
    op.create_unique_constraint('uq_procedure_id_patient', 'procedures', ['id', 'patient_id'])
    op.create_unique_constraint('uq_med_req_id_patient', 'medication_requests', ['id', 'patient_id'])
    op.create_unique_constraint('uq_fhir_resource_id_patient', 'fhir_resources', ['id', 'patient_id'])
    op.create_unique_constraint('uq_facility_id_org', 'facilities', ['id', 'organization_id'])
    op.create_unique_constraint('uq_practitioner_id_org', 'practitioners', ['id', 'organization_id'])
    op.create_unique_constraint('uq_coverage_id_patient', 'coverage', ['id', 'patient_id'])
    op.create_unique_constraint('uq_claim_id_patient', 'claims', ['id', 'patient_id'])
    op.create_unique_constraint('uq_claim_line_id_claim', 'claim_lines', ['id', 'claim_id'])
    op.create_unique_constraint('uq_denial_id_claim', 'denial_events', ['id', 'claim_id'])
    op.create_unique_constraint('uq_appeal_draft_id_appeal', 'appeal_draft_versions', ['id', 'appeal_id'])

    # 2. Add columns
    op.add_column('claim_diagnoses', sa.Column('patient_id', sa.UUID(), nullable=False))
    op.create_index(op.f('ix_claim_diagnoses_patient_id'), 'claim_diagnoses', ['patient_id'], unique=False)
    op.add_column('evidence_chunks', sa.Column('medication_request_id', sa.UUID(), nullable=True))

    # 3. Claims composite foreign keys (coverage/patient, facility/org, practitioner/org)
    op.create_foreign_key('fk_claim_coverage_patient', 'claims', 'coverage', ['coverage_id', 'patient_id'], ['id', 'patient_id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_claim_facility_org', 'claims', 'facilities', ['facility_id', 'organization_id'], ['id', 'organization_id'], ondelete='RESTRICT')
    op.create_foreign_key('fk_claim_practitioner_org', 'claims', 'practitioners', ['rendering_practitioner_id', 'organization_id'], ['id', 'organization_id'], ondelete='RESTRICT')

    # 4. Claim Diagnoses composite foreign keys
    op.drop_constraint('claim_diagnoses_claim_id_fkey', 'claim_diagnoses', type_='foreignkey')
    op.drop_constraint('claim_diagnoses_condition_id_fkey', 'claim_diagnoses', type_='foreignkey')
    op.create_foreign_key('fk_claim_diag_claim_patient', 'claim_diagnoses', 'claims', ['claim_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_claim_diag_condition_patient', 'claim_diagnoses', 'conditions', ['condition_id', 'patient_id'], ['id', 'patient_id'], ondelete='SET NULL')

    # 5. Denial Events composite foreign key to Claim Lines
    op.create_foreign_key('fk_denial_claim_line_claim', 'denial_events', 'claim_lines', ['claim_line_id', 'claim_id'], ['id', 'claim_id'], ondelete='SET NULL')

    # 6. Appeals composite foreign key to Denial Events
    op.drop_constraint('appeals_denial_event_id_fkey', 'appeals', type_='foreignkey')
    op.create_foreign_key('fk_appeal_denial_claim', 'appeals', 'denial_events', ['denial_event_id', 'claim_id'], ['id', 'claim_id'], ondelete='RESTRICT')

    # 7. Investigation Runs composite foreign key to Denial Events
    op.drop_constraint('investigation_runs_denial_event_id_fkey', 'investigation_runs', type_='foreignkey')
    op.create_foreign_key('fk_investigation_denial_claim', 'investigation_runs', 'denial_events', ['denial_event_id', 'claim_id'], ['id', 'claim_id'], ondelete='RESTRICT')

    # 8. Appeal Decisions & Exports composite foreign keys to Appeal Draft Versions
    op.drop_constraint('appeal_decisions_draft_version_id_fkey', 'appeal_decisions', type_='foreignkey')
    op.create_foreign_key('fk_decision_draft_appeal', 'appeal_decisions', 'appeal_draft_versions', ['draft_version_id', 'appeal_id'], ['id', 'appeal_id'], ondelete='RESTRICT')
    op.drop_constraint('exports_draft_version_id_fkey', 'exports', type_='foreignkey')
    op.create_foreign_key('fk_export_draft_appeal', 'exports', 'appeal_draft_versions', ['draft_version_id', 'appeal_id'], ['id', 'appeal_id'], ondelete='RESTRICT')

    # 9. Evidence Chunks provenance & patient consistency
    op.drop_constraint('evidence_chunks_clinical_document_id_fkey', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('evidence_chunks_observation_id_fkey', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('evidence_chunks_encounter_id_fkey', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('evidence_chunks_procedure_id_fkey', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('evidence_chunks_diagnostic_report_id_fkey', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('evidence_chunks_condition_id_fkey', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('evidence_chunks_fhir_resource_id_fkey', 'evidence_chunks', type_='foreignkey')

    op.create_foreign_key('fk_chunk_clinical_doc_patient', 'evidence_chunks', 'clinical_documents', ['clinical_document_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_diag_report_patient', 'evidence_chunks', 'diagnostic_reports', ['diagnostic_report_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_observation_patient', 'evidence_chunks', 'observations', ['observation_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_condition_patient', 'evidence_chunks', 'conditions', ['condition_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_procedure_patient', 'evidence_chunks', 'procedures', ['procedure_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_med_req_patient', 'evidence_chunks', 'medication_requests', ['medication_request_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_fhir_resource_patient', 'evidence_chunks', 'fhir_resources', ['fhir_resource_id', 'patient_id'], ['id', 'patient_id'], ondelete='CASCADE')
    op.create_foreign_key('fk_chunk_encounter_patient', 'evidence_chunks', 'encounters', ['encounter_id', 'patient_id'], ['id', 'patient_id'], ondelete='SET NULL')

    op.create_check_constraint(
        'ck_chunk_source_consistency',
        'evidence_chunks',
        """
        (source_resource_type = 'ClinicalDocument' AND clinical_document_id IS NOT NULL AND source_resource_id = clinical_document_id) OR
        (source_resource_type = 'DiagnosticReport' AND diagnostic_report_id IS NOT NULL AND source_resource_id = diagnostic_report_id) OR
        (source_resource_type = 'Observation' AND observation_id IS NOT NULL AND source_resource_id = observation_id) OR
        (source_resource_type = 'Condition' AND condition_id IS NOT NULL AND source_resource_id = condition_id) OR
        (source_resource_type = 'Procedure' AND procedure_id IS NOT NULL AND source_resource_id = procedure_id) OR
        (source_resource_type = 'MedicationRequest' AND medication_request_id IS NOT NULL AND source_resource_id = medication_request_id) OR
        (source_resource_type = 'FhirResource' AND fhir_resource_id IS NOT NULL AND source_resource_id = fhir_resource_id) OR
        (source_resource_type = 'Encounter' AND encounter_id IS NOT NULL AND source_resource_id = encounter_id)
        """
    )
    op.create_check_constraint(
        'ck_chunk_single_canonical_source',
        'evidence_chunks',
        """
        (CASE WHEN clinical_document_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN diagnostic_report_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN observation_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN condition_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN procedure_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN medication_request_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN fhir_resource_id IS NOT NULL THEN 1 ELSE 0 END +
         CASE WHEN (source_resource_type = 'Encounter' AND encounter_id IS NOT NULL) THEN 1 ELSE 0 END) = 1
        """
    )

    # 10. Database Triggers: Immutability
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_prevent_update_delete_audit_events()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'audit_events is append-only and cannot be updated or deleted';
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_immutable_audit_events
    BEFORE UPDATE OR DELETE ON audit_events
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete_audit_events();
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION fn_prevent_update_delete_appeal_drafts()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'appeal_draft_versions are immutable snapshots and cannot be updated or deleted';
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_immutable_appeal_drafts
    BEFORE UPDATE OR DELETE ON appeal_draft_versions
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete_appeal_drafts();
    """)

    op.execute("""
    CREATE OR REPLACE FUNCTION fn_prevent_update_delete_exports()
    RETURNS TRIGGER AS $$
    BEGIN
        RAISE EXCEPTION 'exports records are immutable and cannot be updated or deleted';
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_immutable_exports
    BEFORE UPDATE OR DELETE ON exports
    FOR EACH ROW EXECUTE FUNCTION fn_prevent_update_delete_exports();
    """)

    # 11. Database Triggers: Business Integrity Guarantees
    # A. Enforce human approval before export
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_enforce_export_approval()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM appeal_decisions
            WHERE appeal_id = NEW.appeal_id
              AND draft_version_id = NEW.draft_version_id
              AND decision = 'APPROVE'
        ) THEN
            RAISE EXCEPTION 'Cannot export draft version without explicit authorized human approval';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_enforce_export_approval
    BEFORE INSERT ON exports
    FOR EACH ROW EXECUTE FUNCTION fn_enforce_export_approval();
    """)

    # B. Enforce claim-line authorization matching coverage and service code
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_enforce_claim_line_auth()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NEW.authorization_id IS NOT NULL THEN
            IF NOT EXISTS (
                SELECT 1 FROM authorizations auth
                JOIN claims c ON c.id = NEW.claim_id
                WHERE auth.id = NEW.authorization_id
                  AND auth.coverage_id = c.coverage_id
                  AND auth.service_code = NEW.service_code
            ) THEN
                RAISE EXCEPTION 'Claim line authorization does not match claim coverage or service code';
            END IF;
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_claim_line_auth_coverage
    BEFORE INSERT OR UPDATE ON claim_lines
    FOR EACH ROW EXECUTE FUNCTION fn_enforce_claim_line_auth();
    """)

    # C. Enforce remittance-line payer consistency with claim coverage
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_enforce_remittance_line_payer()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM remittances r
            JOIN claim_lines cl ON cl.id = NEW.claim_line_id
            JOIN claims c ON c.id = cl.claim_id
            JOIN coverage cov ON cov.id = c.coverage_id
            JOIN payer_plans pp ON pp.id = cov.payer_plan_id
            WHERE r.id = NEW.remittance_id
              AND pp.payer_id = r.payer_id
        ) THEN
            RAISE EXCEPTION 'Remittance payer does not match claim coverage payer';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_remittance_line_payer
    BEFORE INSERT OR UPDATE ON remittance_lines
    FOR EACH ROW EXECUTE FUNCTION fn_enforce_remittance_line_payer();
    """)

    # D. Enforce denial event remittance line consistency
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_enforce_denial_remittance()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM remittance_lines rl
            JOIN claim_lines cl ON cl.id = rl.claim_line_id
            WHERE rl.id = NEW.remittance_line_id
              AND cl.claim_id = NEW.claim_id
              AND (NEW.claim_line_id IS NULL OR cl.id = NEW.claim_line_id)
        ) THEN
            RAISE EXCEPTION 'Denial event remittance line does not match claim or claim line';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)
    op.execute("""
    CREATE TRIGGER trg_denial_event_remit
    BEFORE INSERT OR UPDATE ON denial_events
    FOR EACH ROW EXECUTE FUNCTION fn_enforce_denial_remittance();
    """)


def downgrade() -> None:
    """Downgrade schema."""
    # Drop triggers and trigger functions
    op.execute("DROP TRIGGER IF EXISTS trg_denial_event_remit ON denial_events;")
    op.execute("DROP FUNCTION IF EXISTS fn_enforce_denial_remittance();")

    op.execute("DROP TRIGGER IF EXISTS trg_remittance_line_payer ON remittance_lines;")
    op.execute("DROP FUNCTION IF EXISTS fn_enforce_remittance_line_payer();")

    op.execute("DROP TRIGGER IF EXISTS trg_claim_line_auth_coverage ON claim_lines;")
    op.execute("DROP FUNCTION IF EXISTS fn_enforce_claim_line_auth();")

    op.execute("DROP TRIGGER IF EXISTS trg_enforce_export_approval ON exports;")
    op.execute("DROP FUNCTION IF EXISTS fn_enforce_export_approval();")

    op.execute("DROP TRIGGER IF EXISTS trg_immutable_exports ON exports;")
    op.execute("DROP FUNCTION IF EXISTS fn_prevent_update_delete_exports();")

    op.execute("DROP TRIGGER IF EXISTS trg_immutable_appeal_drafts ON appeal_draft_versions;")
    op.execute("DROP FUNCTION IF EXISTS fn_prevent_update_delete_appeal_drafts();")

    op.execute("DROP TRIGGER IF EXISTS trg_immutable_audit_events ON audit_events;")
    op.execute("DROP FUNCTION IF EXISTS fn_prevent_update_delete_audit_events();")

    # Drop evidence chunk check constraints
    op.drop_constraint('ck_chunk_single_canonical_source', 'evidence_chunks', type_='check')
    op.drop_constraint('ck_chunk_source_consistency', 'evidence_chunks', type_='check')

    # Revert evidence chunk foreign keys
    op.drop_constraint('fk_chunk_encounter_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_fhir_resource_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_med_req_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_procedure_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_condition_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_observation_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_diag_report_patient', 'evidence_chunks', type_='foreignkey')
    op.drop_constraint('fk_chunk_clinical_doc_patient', 'evidence_chunks', type_='foreignkey')

    op.create_foreign_key('evidence_chunks_clinical_document_id_fkey', 'evidence_chunks', 'clinical_documents', ['clinical_document_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('evidence_chunks_observation_id_fkey', 'evidence_chunks', 'observations', ['observation_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('evidence_chunks_encounter_id_fkey', 'evidence_chunks', 'encounters', ['encounter_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('evidence_chunks_procedure_id_fkey', 'evidence_chunks', 'procedures', ['procedure_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('evidence_chunks_diagnostic_report_id_fkey', 'evidence_chunks', 'diagnostic_reports', ['diagnostic_report_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('evidence_chunks_condition_id_fkey', 'evidence_chunks', 'conditions', ['condition_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('evidence_chunks_fhir_resource_id_fkey', 'evidence_chunks', 'fhir_resources', ['fhir_resource_id'], ['id'], ondelete='SET NULL')

    op.drop_column('evidence_chunks', 'medication_request_id')

    # Revert Appeal Decisions and Exports
    op.drop_constraint('fk_export_draft_appeal', 'exports', type_='foreignkey')
    op.create_foreign_key('exports_draft_version_id_fkey', 'exports', 'appeal_draft_versions', ['draft_version_id'], ['id'], ondelete='RESTRICT')

    op.drop_constraint('fk_decision_draft_appeal', 'appeal_decisions', type_='foreignkey')
    op.create_foreign_key('appeal_decisions_draft_version_id_fkey', 'appeal_decisions', 'appeal_draft_versions', ['draft_version_id'], ['id'], ondelete='RESTRICT')

    # Revert Investigation Runs
    op.drop_constraint('fk_investigation_denial_claim', 'investigation_runs', type_='foreignkey')
    op.create_foreign_key('investigation_runs_denial_event_id_fkey', 'investigation_runs', 'denial_events', ['denial_event_id'], ['id'], ondelete='RESTRICT')

    # Revert Appeals
    op.drop_constraint('fk_appeal_denial_claim', 'appeals', type_='foreignkey')
    op.create_foreign_key('appeals_denial_event_id_fkey', 'appeals', 'denial_events', ['denial_event_id'], ['id'], ondelete='RESTRICT')

    # Revert Denial Events
    op.drop_constraint('fk_denial_claim_line_claim', 'denial_events', type_='foreignkey')

    # Revert Claim Diagnoses
    op.drop_constraint('fk_claim_diag_condition_patient', 'claim_diagnoses', type_='foreignkey')
    op.drop_constraint('fk_claim_diag_claim_patient', 'claim_diagnoses', type_='foreignkey')
    op.create_foreign_key('claim_diagnoses_condition_id_fkey', 'claim_diagnoses', 'conditions', ['condition_id'], ['id'], ondelete='SET NULL')
    op.create_foreign_key('claim_diagnoses_claim_id_fkey', 'claim_diagnoses', 'claims', ['claim_id'], ['id'], ondelete='CASCADE')
    op.drop_index(op.f('ix_claim_diagnoses_patient_id'), table_name='claim_diagnoses')
    op.drop_column('claim_diagnoses', 'patient_id')

    # Revert Claims composite FKs
    op.drop_constraint('fk_claim_practitioner_org', 'claims', type_='foreignkey')
    op.drop_constraint('fk_claim_facility_org', 'claims', type_='foreignkey')
    op.drop_constraint('fk_claim_coverage_patient', 'claims', type_='foreignkey')

    # Drop unique constraints
    op.drop_constraint('uq_appeal_draft_id_appeal', 'appeal_draft_versions', type_='unique')
    op.drop_constraint('uq_denial_id_claim', 'denial_events', type_='unique')
    op.drop_constraint('uq_claim_line_id_claim', 'claim_lines', type_='unique')
    op.drop_constraint('uq_claim_id_patient', 'claims', type_='unique')
    op.drop_constraint('uq_coverage_id_patient', 'coverage', type_='unique')
    op.drop_constraint('uq_practitioner_id_org', 'practitioners', type_='unique')
    op.drop_constraint('uq_facility_id_org', 'facilities', type_='unique')
    op.drop_constraint('uq_fhir_resource_id_patient', 'fhir_resources', type_='unique')
    op.drop_constraint('uq_med_req_id_patient', 'medication_requests', type_='unique')
    op.drop_constraint('uq_procedure_id_patient', 'procedures', type_='unique')
    op.drop_constraint('uq_condition_id_patient', 'conditions', type_='unique')
    op.drop_constraint('uq_observation_id_patient', 'observations', type_='unique')
    op.drop_constraint('uq_diag_report_id_patient', 'diagnostic_reports', type_='unique')
    op.drop_constraint('uq_clinical_doc_id_patient', 'clinical_documents', type_='unique')
