"""003 add delivery tracking to messages

Revision ID: 003_delivery_tracking
Revises: 002_lead_source
Create Date: 2026-03-11

Adds provider_message_id, delivery_status, delivered_at, failure_reason,
and feedback_score columns to the messages table.
"""
from alembic import op
import sqlalchemy as sa

revision = "003_delivery_tracking"
down_revision = "002_lead_source"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("messages", sa.Column("provider_message_id", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("delivery_status", sa.Text(), server_default="pending", nullable=True))
    op.add_column("messages", sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("messages", sa.Column("failure_reason", sa.Text(), nullable=True))
    op.add_column("messages", sa.Column("feedback_score", sa.Integer(), nullable=True))

    op.create_index(
        "idx_messages_provider_id", "messages", ["provider_message_id"],
        postgresql_where=sa.text("provider_message_id IS NOT NULL"),
    )
    op.create_index(
        "idx_messages_delivery_status", "messages", ["agent_id", "delivery_status"],
        postgresql_where=sa.text("delivery_status IN ('failed', 'undelivered')"),
    )


def downgrade() -> None:
    op.drop_index("idx_messages_delivery_status")
    op.drop_index("idx_messages_provider_id")
    op.drop_column("messages", "feedback_score")
    op.drop_column("messages", "failure_reason")
    op.drop_column("messages", "delivered_at")
    op.drop_column("messages", "delivery_status")
    op.drop_column("messages", "provider_message_id")
