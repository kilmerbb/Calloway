"""007 add console_users and audit_log tables for per-user console auth

Revision ID: 007_console_users
Revises: 006_add_device_tokens
Create Date: 2026-03-14

Per-user authentication for the operator console with role-based access
control and an audit trail for all state-changing actions.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "007_console_users"
down_revision = "006_add_device_tokens"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── console_users ──────────────────────────────────────────
    op.create_table(
        "console_users",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False, server_default=sa.text("'viewer'")),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index("idx_console_users_email", "console_users", ["email"], unique=True)

    # ── audit_log ──────────────────────────────────────────────
    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("console_users.id"), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_entity", sa.Text(), nullable=True),
        sa.Column("target_id", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index("idx_audit_log_created", "audit_log", ["created_at"])
    op.create_index("idx_audit_log_user", "audit_log", ["user_id"])
    op.create_index("idx_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    op.drop_index("idx_audit_log_action")
    op.drop_index("idx_audit_log_user")
    op.drop_index("idx_audit_log_created")
    op.drop_table("audit_log")
    op.drop_index("idx_console_users_email")
    op.drop_table("console_users")
