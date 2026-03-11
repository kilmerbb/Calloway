"""Tests for transaction model and tools."""
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.schemas import Transaction
from app.tools.transactions import VALID_STATUSES, VALID_TRANSACTION_TYPES

AGENT_ID = uuid4()
LISTING_ID = uuid4()
CONTACT_ID = uuid4()


# ── Model Tests ──────────────────────────────────────────────

class TestTransactionModel:

    def test_create_with_defaults(self):
        txn = Transaction(agent_id=AGENT_ID, contact_id=CONTACT_ID)
        assert txn.id is None
        assert txn.agent_id == AGENT_ID
        assert txn.contact_id == CONTACT_ID
        assert txn.transaction_type == "purchase"
        assert txn.status == "pending_offer"
        assert txn.listing_id is None
        assert txn.offer_price is None
        assert txn.final_price is None
        assert txn.commission_pct is None
        assert txn.notes is None

    def test_create_with_all_fields(self):
        txn = Transaction(
            id=uuid4(),
            agent_id=AGENT_ID,
            contact_id=CONTACT_ID,
            listing_id=LISTING_ID,
            transaction_type="sale",
            status="under_contract",
            offer_price=475000,
            final_price=470000,
            offer_date=date(2026, 3, 1),
            contract_date=date(2026, 3, 3),
            inspection_date=date(2026, 3, 10),
            appraisal_date=date(2026, 3, 15),
            financing_deadline=date(2026, 3, 20),
            closing_date=date(2026, 4, 15),
            earnest_money=5000,
            commission_pct=Decimal("2.50"),
            notes="Seller motivated, quick close expected.",
            created_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            updated_at=datetime(2026, 3, 10, 8, 0, tzinfo=timezone.utc),
        )
        assert txn.transaction_type == "sale"
        assert txn.offer_price == 475000
        assert txn.final_price == 470000
        assert txn.commission_pct == Decimal("2.50")
        assert txn.earnest_money == 5000

    def test_missing_agent_id_raises(self):
        with pytest.raises(ValidationError):
            Transaction()

    def test_serialization_roundtrip(self):
        txn = Transaction(
            agent_id=AGENT_ID,
            contact_id=CONTACT_ID,
            listing_id=LISTING_ID,
            offer_price=500000,
            commission_pct=Decimal("3.00"),
        )
        json_str = txn.model_dump_json()
        restored = Transaction.model_validate_json(json_str)
        assert restored.agent_id == txn.agent_id
        assert restored.offer_price == 500000
        assert restored.commission_pct == Decimal("3.00")

    def test_date_fields_accept_date_objects(self):
        txn = Transaction(
            agent_id=AGENT_ID,
            contact_id=CONTACT_ID,
            offer_date=date(2026, 3, 1),
            closing_date=date(2026, 4, 15),
        )
        assert txn.offer_date == date(2026, 3, 1)
        assert txn.closing_date == date(2026, 4, 15)


# ── Status Validation Tests ──────────────────────────────────

class TestTransactionStatuses:

    def test_valid_statuses_list(self):
        expected = {
            "pending_offer", "under_contract", "contingency",
            "clear_to_close", "closed", "fell_through",
        }
        assert VALID_STATUSES == expected

    def test_all_statuses_accepted_by_model(self):
        for status in VALID_STATUSES:
            txn = Transaction(agent_id=AGENT_ID, contact_id=CONTACT_ID, status=status)
            assert txn.status == status

    def test_valid_transaction_types(self):
        assert VALID_TRANSACTION_TYPES == {"purchase", "sale", "lease"}

    def test_all_transaction_types_accepted(self):
        for ttype in VALID_TRANSACTION_TYPES:
            txn = Transaction(agent_id=AGENT_ID, contact_id=CONTACT_ID, transaction_type=ttype)
            assert txn.transaction_type == ttype


# ── Transaction Type Tests ───────────────────────────────────

class TestTransactionTypes:

    def test_purchase_default(self):
        txn = Transaction(agent_id=AGENT_ID, contact_id=CONTACT_ID)
        assert txn.transaction_type == "purchase"

    def test_sale_type(self):
        txn = Transaction(agent_id=AGENT_ID, contact_id=CONTACT_ID, transaction_type="sale")
        assert txn.transaction_type == "sale"

    def test_lease_type(self):
        txn = Transaction(agent_id=AGENT_ID, contact_id=CONTACT_ID, transaction_type="lease")
        assert txn.transaction_type == "lease"


# ── Financial Fields ─────────────────────────────────────────

class TestTransactionFinancials:

    def test_offer_and_final_price(self):
        txn = Transaction(
            agent_id=AGENT_ID, contact_id=CONTACT_ID,
            offer_price=500000, final_price=485000,
        )
        assert txn.offer_price == 500000
        assert txn.final_price == 485000

    def test_commission_percentage(self):
        txn = Transaction(
            agent_id=AGENT_ID, contact_id=CONTACT_ID,
            commission_pct=Decimal("3.00"),
        )
        assert txn.commission_pct == Decimal("3.00")

    def test_earnest_money(self):
        txn = Transaction(
            agent_id=AGENT_ID, contact_id=CONTACT_ID,
            earnest_money=10000,
        )
        assert txn.earnest_money == 10000
