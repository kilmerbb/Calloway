"""005 add transactions table

Revision ID: 005_add_transactions
Revises: 004_cost_tracking
Create Date: 2026-03-11

Adds the transactions table for tracking offer-to-close lifecycle,
including deadlines, pricing, and commission tracking.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "005_add_transactions"
down_revision = "004_cost_tracking"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("agent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agents.id"), nullable=False),
        sa.Column("contact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("contacts.id"), nullable=False),
        sa.Column("listing_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("listings.id"), nullable=True),
        sa.Column("transaction_type", sa.Text(), nullable=False, server_default="purchase"),
        sa.Column("status", sa.Text(), nullable=False, server_default="pending_offer"),
        sa.Column("offer_price", sa.Integer(), nullable=True),
        sa.Column("final_price", sa.Integer(), nullable=True),
        sa.Column("offer_date", sa.Date(), nullable=True),
        sa.Column("contract_date", sa.Date(), nullable=True),
        sa.Column("closing_date", sa.Date(), nullable=True),
        sa.Column("inspection_date", sa.Date(), nullable=True),
        sa.Column("appraisal_date", sa.Date(), nullable=True),
        sa.Column("financing_deadline", sa.Date(), nullable=True),
        sa.Column("earnest_money", sa.Integer(), nullable=True),
        sa.Column("commission_pct", sa.Numeric(precision=4, scale=2), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    op.create_index("idx_transactions_agent_status", "transactions", ["agent_id", "status"])
    op.create_index("idx_transactions_contact", "transactions", ["contact_id"])
    op.create_index(
        "idx_transactions_closing", "transactions", ["closing_date"],
        postgresql_where=sa.text("status NOT IN ('closed', 'fell_through')"),
    )

    # Enable RLS
    op.execute("ALTER TABLE transactions ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY agent_isolation ON transactions "
        "FOR ALL USING (agent_id = current_setting('app.current_agent_id')::uuid)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS agent_isolation ON transactions")
    op.drop_index("idx_transactions_closing")
    op.drop_index("idx_transactions_contact")
    op.drop_index("idx_transactions_agent_status")
    op.drop_table("transactions")
