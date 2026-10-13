"""add_evidence_chunks_fts_index

Revision ID: 9e01fee8d001
Revises: 8d90fee8c001
Create Date: 2026-10-13 22:45:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9e01fee8d001"
down_revision: str | None = "8d90fee8c001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create GIN expression index for PostgreSQL full-text search on chunk content
    op.create_index(
        "ix_evidence_chunks_content_fts",
        "evidence_chunks",
        [sa.text("to_tsvector('english', content)")],
        postgresql_using="gin",
    )


def downgrade() -> None:
    # Drop GIN expression index
    op.drop_index(
        "ix_evidence_chunks_content_fts",
        table_name="evidence_chunks",
        postgresql_using="gin",
    )
