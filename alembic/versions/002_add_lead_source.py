"""002 add lead_source to contacts

Revision ID: 002_lead_source
Revises: 001_baseline
Create Date: 2026-03-11

Adds lead_source tracking column to contacts table and indexes.
"""
from alembic import op
import sqlalchemy as sa

revision = "002_lead_source"
down_revision = "001_baseline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("contacts", sa.Column("lead_source", sa.Text(), nullable=True))
    op.create_index(
        "idx_contacts_agent_email", "contacts", ["agent_id", "email"],
        postgresql_where=sa.text("email IS NOT NULL"),
    )
    op.create_index(
        "idx_contacts_lead_source", "contacts", ["agent_id", "lead_source"],
        postgresql_where=sa.text("lead_source IS NOT NULL"),
    )

    # Backfill existing contacts
    op.execute("""
        UPDATE contacts c
        SET lead_source = COALESCE(
            (SELECT DISTINCT cv.channel FROM conversations cv
             WHERE cv.contact_id = c.id
             ORDER BY cv.created_at LIMIT 1),
            'manual'
        )
        WHERE c.lead_source IS NULL
    """)


def downgrade() -> None:
    op.drop_index("idx_contacts_lead_source")
    op.drop_index("idx_contacts_agent_email")
    op.drop_column("contacts", "lead_source")
