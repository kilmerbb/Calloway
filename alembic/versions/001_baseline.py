"""001 baseline schema

Revision ID: 001_baseline
Revises:
Create Date: 2026-03-11

Baseline migration — marks the existing schema as the starting point.
All tables already exist from schema.sql; this is a no-op checkpoint.
"""
from alembic import op

revision = "001_baseline"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """No-op: schema already exists from initial schema.sql deployment."""
    pass


def downgrade() -> None:
    """Cannot downgrade past baseline."""
    raise RuntimeError("Cannot downgrade past baseline migration")
