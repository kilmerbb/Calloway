"""004 add SMS and voice cost tracking

Revision ID: 004_cost_tracking
Revises: 003_delivery_tracking
Create Date: 2026-03-11

Adds sms_segments_sent, sms_segments_received, sms_cost_cents, and
voice_cost_cents columns to usage_metrics. Adds voice_daily_cap_minutes
to agents for per-agent voice minute caps.
"""
from alembic import op
import sqlalchemy as sa

revision = "004_cost_tracking"
down_revision = "003_delivery_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("usage_metrics", sa.Column("sms_segments_sent", sa.Integer(), server_default="0", nullable=False))
    op.add_column("usage_metrics", sa.Column("sms_segments_received", sa.Integer(), server_default="0", nullable=False))
    op.add_column("usage_metrics", sa.Column("sms_cost_cents", sa.Integer(), server_default="0", nullable=False))
    op.add_column("usage_metrics", sa.Column("voice_cost_cents", sa.Integer(), server_default="0", nullable=False))
    op.add_column("agents", sa.Column("voice_daily_cap_minutes", sa.Integer(), server_default="30", nullable=False))


def downgrade() -> None:
    op.drop_column("agents", "voice_daily_cap_minutes")
    op.drop_column("usage_metrics", "voice_cost_cents")
    op.drop_column("usage_metrics", "sms_cost_cents")
    op.drop_column("usage_metrics", "sms_segments_received")
    op.drop_column("usage_metrics", "sms_segments_sent")
