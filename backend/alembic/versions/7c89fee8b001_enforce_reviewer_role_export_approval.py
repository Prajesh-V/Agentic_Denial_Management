"""enforce_reviewer_role_export_approval

Revision ID: 7c89fee8b001
Revises: 6089fee8b997
Create Date: 2026-10-13 19:25:00.000000

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c89fee8b001"
down_revision: str | Sequence[str] | None = "6089fee8b997"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Seed authoritative system roles if not present
    op.execute("""
    INSERT INTO roles (id, description)
    VALUES
        ('analyst', 'Denial Analyst - Operational claim queue and investigation access'),
        ('reviewer', 'Reviewer / Senior Specialist - Supervisory and review authority to approve appeals'),
        ('manager', 'RCM Manager - Queue and departmental operational oversight'),
        ('auditor', 'Auditor / Compliance Officer - Read-only forensic and audit access'),
        ('data_admin', 'Data Administrator - Dataset generation and benchmark management')
    ON CONFLICT (id) DO NOTHING;
    """)

    # 2. Strengthen trigger function to verify active human reviewer with reviewer role
    op.execute("""
    CREATE OR REPLACE FUNCTION fn_enforce_export_approval()
    RETURNS TRIGGER AS $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1
            FROM appeal_decisions ad
            JOIN users u ON u.id = ad.reviewer_user_id
            JOIN user_roles ur ON ur.user_id = u.id
            WHERE ad.appeal_id = NEW.appeal_id
              AND ad.draft_version_id = NEW.draft_version_id
              AND ad.decision = 'APPROVE'
              AND u.is_active = TRUE
              AND lower(ur.role_id) IN ('reviewer', 'senior_specialist', 'manager', 'rcm_manager')
        ) THEN
            RAISE EXCEPTION 'Cannot export draft version without authorized human approval by an active reviewer';
        END IF;
        RETURN NEW;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    # Revert trigger function to prior version (existence of approval row without role check)
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

    # Clean up seeded roles if needed
    op.execute("""
    DELETE FROM roles WHERE id IN ('analyst', 'reviewer', 'manager', 'auditor', 'data_admin');
    """)
