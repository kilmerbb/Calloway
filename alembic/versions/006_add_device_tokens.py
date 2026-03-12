"""006 add device_tokens table for FCM push notifications

Revision ID: 006_add_device_tokens
Revises: 005_add_transactions
Create Date: 2026-03-12

Stores FCM registration tokens per agent, supporting multiple devices.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "006_add_device_tokens"
down_revision = "005_add_transactions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "device_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fcm_token", sa.Text(), nullable=False),
        sa.Column("device_name", sa.Text(), nullable=True),
        sa.Column("platform", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index("idx_device_tokens_fcm", "device_tokens", ["fcm_token"], unique=True)
    op.create_index(
        "idx_device_tokens_agent_active", "device_tokens", ["agent_id"],
        postgresql_where=sa.text("is_active = true"),
    )

    op.execute("ALTER TABLE device_tokens ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_isolation ON device_tokens "
        "FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS agent_isolation ON device_tokens")
    op.drop_index("idx_device_tokens_agent_active")
    op.drop_index("idx_device_tokens_fcm")
    op.drop_table("device_tokens")
