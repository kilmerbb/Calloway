"""Tests for conversation summarization system."""
import pytest
from datetime import datetime, timezone, timedelta
from uuid import UUID, uuid4
from unittest.mock import patch, MagicMock

from app.models.schemas import (
    AgentConfig, Contact, Message, ConversationSummary,
    NormalizedEvent, IntentClassification, AssembledContext,
)
from app.services.summarization_service import (
    SUMMARIZATION_THRESHOLD,
    INCREMENTAL_BATCH,
    FULL_RESUMMARIZE_EVERY,
    TIME_BASED_MESSAGE_MIN,
    TIME_BASED_SPAN_DAYS,
    should_summarize,
    generate_or_update_summary,
    get_conversation_summary,
    _format_messages_for_prompt,
    _needs_full_resummarization,
)
from app.pipeline.assembler import (
    assemble_context,
    _load_history_with_summary,
    _estimate_summary_tokens,
    RECENT_MESSAGES_WITH_SUMMARY,
)

AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a22")
CONV_ID = UUID("c2eebc99-9c0b-4ef8-bb6d-6bb9bd380a33")

AGENT = AgentConfig(
    id=AGENT_ID, name="Jane Smith", email="jane@test.com",
    phone="+12155551000", twilio_number="+12155559999",
)

CONTACT = Contact(
    id=CONTACT_ID, agent_id=AGENT_ID, name="Mike Buyer",
    phone="+12155552000", role="lead", lifecycle_stage="active_buyer",
    consent_status="granted",
)


def _make_message(i: int, sender: str = "client") -> Message:
    return Message(
        id=uuid4(),
        agent_id=AGENT_ID,
        conversation_id=CONV_ID,
        sender_type=sender,
        body=f"Test message {i}",
        created_at=datetime(2026, 1, 1, 12, i % 60, tzinfo=timezone.utc),
    )


def _make_summary(count: int = 50, incremental_count: int = 0) -> ConversationSummary:
    return ConversationSummary(
        id=uuid4(),
        tenant_id=AGENT_ID,
        contact_id=CONTACT_ID,
        conversation_id=CONV_ID,
        summary_text="CLIENT: Mike Buyer | ROLE: buyer\nBUDGET: $400000-$500000 | PRE-APPROVED: yes\nREQUIREMENTS: 3BR/2BA, Fishtown\nMUST-HAVES: garage, yard\nDEALBREAKERS: no HOA over $300\nTIMELINE: within 3 months",
        messages_summarized_count=count,
        last_message_id=uuid4(),
        token_estimate=80,
        incremental_count=incremental_count,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


# ── Format messages ─────────────────────────────────────────────

class TestFormatMessages:
    def test_format_client_message(self):
        msgs = [_make_message(0, "client")]
        result = _format_messages_for_prompt(msgs)
        assert "Client:" in result
        assert "Test message 0" in result

    def test_format_ai_message(self):
        msgs = [_make_message(0, "ai")]
        result = _format_messages_for_prompt(msgs)
        assert "Assistant:" in result

    def test_format_agent_command(self):
        msgs = [_make_message(0, "agent_command")]
        result = _format_messages_for_prompt(msgs)
        assert "Agent:" in result

    def test_format_multiple_messages(self):
        msgs = [_make_message(i, "client" if i % 2 == 0 else "ai") for i in range(5)]
        result = _format_messages_for_prompt(msgs)
        lines = result.strip().split("\n")
        assert len(lines) == 5


# ── should_summarize ────────────────────────────────────────────

class TestShouldSummarize:
    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_below_threshold_returns_false(self, mock_summary, mock_count):
        mock_count.return_value = SUMMARIZATION_THRESHOLD - 1
        with patch("app.services.summarization_service.get_conversation_span_days", return_value=0):
            assert should_summarize(AGENT_ID, CONTACT_ID) is False
        mock_summary.assert_not_called()

    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_above_threshold_no_summary_returns_true(self, mock_summary, mock_count):
        mock_count.return_value = SUMMARIZATION_THRESHOLD + 10
        mock_summary.return_value = None
        assert should_summarize(AGENT_ID, CONTACT_ID) is True

    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_above_threshold_with_recent_summary_returns_false(self, mock_summary, mock_count):
        mock_count.return_value = SUMMARIZATION_THRESHOLD + 5
        mock_summary.return_value = _make_summary(count=SUMMARIZATION_THRESHOLD + 5 - INCREMENTAL_BATCH + 1)
        # Not enough new messages since last summary
        assert should_summarize(AGENT_ID, CONTACT_ID) is False

    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_enough_new_messages_returns_true(self, mock_summary, mock_count):
        mock_count.return_value = 100
        mock_summary.return_value = _make_summary(count=100 - INCREMENTAL_BATCH)
        assert should_summarize(AGENT_ID, CONTACT_ID) is True

    @patch("app.services.summarization_service.get_conversation_span_days")
    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_time_based_trigger_slow_burn(self, mock_summary, mock_count, mock_span):
        """25+ messages spanning 30+ days triggers summarization even under 50-msg threshold."""
        mock_count.return_value = TIME_BASED_MESSAGE_MIN  # exactly at minimum
        mock_span.return_value = TIME_BASED_SPAN_DAYS  # exactly at minimum span
        mock_summary.return_value = None  # no existing summary
        assert should_summarize(AGENT_ID, CONTACT_ID) is True

    @patch("app.services.summarization_service.get_conversation_span_days")
    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_time_based_trigger_not_enough_messages(self, mock_summary, mock_count, mock_span):
        """Under 25 messages even with long span does not trigger."""
        mock_count.return_value = TIME_BASED_MESSAGE_MIN - 1
        mock_span.return_value = TIME_BASED_SPAN_DAYS + 10
        assert should_summarize(AGENT_ID, CONTACT_ID) is False
        mock_summary.assert_not_called()

    @patch("app.services.summarization_service.get_conversation_span_days")
    @patch("app.services.summarization_service.get_message_count")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_time_based_trigger_not_enough_days(self, mock_summary, mock_count, mock_span):
        """25+ messages but short span does not trigger (under threshold too)."""
        mock_count.return_value = TIME_BASED_MESSAGE_MIN + 5
        mock_span.return_value = TIME_BASED_SPAN_DAYS - 1
        assert should_summarize(AGENT_ID, CONTACT_ID) is False
        mock_summary.assert_not_called()


# ── Drift mitigation: full re-summarization ────────────────────

class TestFullResummarization:
    def test_needs_full_resummarization_at_threshold(self):
        summary = _make_summary(incremental_count=FULL_RESUMMARIZE_EVERY)
        assert _needs_full_resummarization(summary) is True

    def test_needs_full_resummarization_above_threshold(self):
        summary = _make_summary(incremental_count=FULL_RESUMMARIZE_EVERY + 2)
        assert _needs_full_resummarization(summary) is True

    def test_no_full_resummarization_below_threshold(self):
        summary = _make_summary(incremental_count=FULL_RESUMMARIZE_EVERY - 1)
        assert _needs_full_resummarization(summary) is False

    def test_no_full_resummarization_at_zero(self):
        summary = _make_summary(incremental_count=0)
        assert _needs_full_resummarization(summary) is False

    @patch("app.services.summarization_service._save_summary")
    @patch("app.services.summarization_service.get_anthropic_client")
    @patch("app.services.summarization_service._load_messages_for_summary")
    @patch("app.services.summarization_service.get_db_connection")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_full_resummarize_triggered_after_5_cycles(
        self, mock_get_summary, mock_db, mock_load_msgs, mock_client, mock_save
    ):
        """After 5 incremental updates, a full re-summarization from all messages is triggered."""
        existing = _make_summary(count=200, incremental_count=FULL_RESUMMARIZE_EVERY)
        mock_get_summary.return_value = existing

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = {"id": CONV_ID}
        mock_db.return_value = mock_conn

        all_messages = [_make_message(i) for i in range(200)]
        mock_load_msgs.return_value = all_messages

        mock_ai = MagicMock()
        mock_ai.compose.return_value = "Full re-summarized content."
        mock_client.return_value = mock_ai

        refreshed = _make_summary(count=200, incremental_count=0)
        mock_save.return_value = refreshed

        result = generate_or_update_summary(AGENT_ID, CONTACT_ID)

        # Verify _save_summary was called with incremental_count=0 (reset)
        save_call = mock_save.call_args
        assert save_call.kwargs.get("incremental_count", save_call[1].get("incremental_count")) == 0
        assert result == refreshed

    @patch("app.services.summarization_service._save_summary")
    @patch("app.services.summarization_service.get_anthropic_client")
    @patch("app.services.summarization_service._load_messages_for_summary")
    @patch("app.services.summarization_service.get_db_connection")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_incremental_update_increments_count(
        self, mock_get_summary, mock_db, mock_load_msgs, mock_client, mock_save
    ):
        """Each incremental update should increment the incremental_count."""
        existing = _make_summary(count=50, incremental_count=2)
        mock_get_summary.return_value = existing

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = {"id": CONV_ID}
        mock_db.return_value = mock_conn

        new_messages = [_make_message(i) for i in range(30)]
        mock_load_msgs.return_value = new_messages

        mock_ai = MagicMock()
        mock_ai.compose.return_value = "Updated summary."
        mock_client.return_value = mock_ai

        updated = _make_summary(count=80, incremental_count=3)
        mock_save.return_value = updated

        result = generate_or_update_summary(AGENT_ID, CONTACT_ID)

        # Verify incremental_count was incremented
        save_call = mock_save.call_args
        assert save_call.kwargs.get("incremental_count", save_call[1].get("incremental_count")) == 3


# ── generate_or_update_summary ──────────────────────────────────

class TestGenerateOrUpdateSummary:
    @patch("app.services.summarization_service._save_summary")
    @patch("app.services.summarization_service.get_anthropic_client")
    @patch("app.services.summarization_service._load_messages_for_summary")
    @patch("app.services.summarization_service.get_db_connection")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_initial_summary_generated(
        self, mock_get_summary, mock_db, mock_load_msgs, mock_client, mock_save
    ):
        mock_get_summary.return_value = None
        # Mock DB to return conversation id
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = {"id": CONV_ID}
        mock_db.return_value = mock_conn

        messages = [_make_message(i) for i in range(60)]
        mock_load_msgs.return_value = messages

        mock_ai = MagicMock()
        mock_ai.compose.return_value = "Summary: Mike is an active buyer in Fishtown."
        mock_client.return_value = mock_ai

        saved = _make_summary(count=60)
        mock_save.return_value = saved

        result = generate_or_update_summary(AGENT_ID, CONTACT_ID)

        mock_ai.compose.assert_called_once()
        mock_save.assert_called_once()
        assert result == saved

    @patch("app.services.summarization_service._save_summary")
    @patch("app.services.summarization_service.get_anthropic_client")
    @patch("app.services.summarization_service._load_messages_for_summary")
    @patch("app.services.summarization_service.get_db_connection")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_incremental_update(
        self, mock_get_summary, mock_db, mock_load_msgs, mock_client, mock_save
    ):
        existing = _make_summary(count=50)
        mock_get_summary.return_value = existing

        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = {"id": CONV_ID}
        mock_db.return_value = mock_conn

        new_messages = [_make_message(i) for i in range(30)]
        mock_load_msgs.return_value = new_messages

        mock_ai = MagicMock()
        mock_ai.compose.return_value = "Updated summary with new info."
        mock_client.return_value = mock_ai

        updated = _make_summary(count=80)
        mock_save.return_value = updated

        result = generate_or_update_summary(AGENT_ID, CONTACT_ID)

        # Should use incremental prompt (contains existing summary)
        call_args = mock_ai.compose.call_args
        assert "existing summary" in call_args.kwargs.get("system_prompt", call_args[1].get("system_prompt", "")).lower() or \
               "existing summary" in str(call_args).lower()
        assert result == updated

    @patch("app.services.summarization_service.get_db_connection")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_no_conversation_returns_none(self, mock_get_summary, mock_db):
        mock_get_summary.return_value = None
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_db.return_value = mock_conn

        result = generate_or_update_summary(AGENT_ID, CONTACT_ID)
        assert result is None


# ── ConversationSummary model ──────────────────────────────────

class TestConversationSummaryModel:
    def test_incremental_count_defaults_to_zero(self):
        summary = ConversationSummary(
            tenant_id=AGENT_ID,
            contact_id=CONTACT_ID,
            conversation_id=CONV_ID,
            summary_text="test",
        )
        assert summary.incremental_count == 0

    def test_incremental_count_can_be_set(self):
        summary = _make_summary(incremental_count=3)
        assert summary.incremental_count == 3


# ── Assembler integration ───────────────────────────────────────

class TestAssemblerWithSummary:
    @patch("app.pipeline.assembler._load_conversation_history")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_loads_summary_and_fewer_messages(self, mock_summary, mock_history):
        """When a summary exists, load fewer recent messages."""
        summary = _make_summary()
        mock_summary.return_value = summary
        mock_history.return_value = [_make_message(i) for i in range(RECENT_MESSAGES_WITH_SUMMARY)]

        summary_text, messages = _load_history_with_summary(AGENT_ID, CONTACT_ID)

        assert summary_text == summary.summary_text
        mock_history.assert_called_once_with(AGENT_ID, CONTACT_ID, limit=RECENT_MESSAGES_WITH_SUMMARY)

    @patch("app.pipeline.assembler._load_conversation_history")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_no_summary_loads_default_messages(self, mock_summary, mock_history):
        """When no summary, load the default 20 messages."""
        mock_summary.return_value = None
        mock_history.return_value = [_make_message(i) for i in range(20)]

        summary_text, messages = _load_history_with_summary(AGENT_ID, CONTACT_ID)

        assert summary_text is None
        mock_history.assert_called_once_with(AGENT_ID, CONTACT_ID, limit=20)

    @patch("app.pipeline.assembler._load_conversation_history")
    @patch("app.services.summarization_service.get_conversation_summary")
    def test_summary_lookup_failure_falls_back(self, mock_summary, mock_history):
        """If summary lookup fails, fall back to standard behavior."""
        import psycopg
        mock_summary.side_effect = psycopg.Error("DB error")
        mock_history.return_value = [_make_message(i) for i in range(20)]

        summary_text, messages = _load_history_with_summary(AGENT_ID, CONTACT_ID)

        assert summary_text is None
        assert len(messages) == 20

    def test_estimate_summary_tokens_none(self):
        assert _estimate_summary_tokens(None) == 0

    def test_estimate_summary_tokens_nonempty(self):
        text = "This is a summary of about ten words for testing."
        tokens = _estimate_summary_tokens(text)
        assert tokens > 0

    @patch("app.pipeline.assembler._load_history_with_summary")
    @patch("app.pipeline.assembler.search_listings")
    def test_assemble_context_includes_summary(self, mock_listings, mock_history):
        """AssembledContext should carry the summary text."""
        mock_listings.return_value = []
        summary_text = "CLIENT: Mike Buyer | ROLE: buyer\nBUDGET: $400000-$500000"
        mock_history.return_value = (summary_text, [_make_message(0)])

        event = NormalizedEvent(
            sender_phone="+12155552000", channel="sms", body="Hi",
            timestamp=datetime.now(timezone.utc),
            provider_message_id="SM999", raw_payload={}, agent_id=AGENT_ID,
        )
        intent = IntentClassification(
            intent="personal", sender_type="known_client",
            confidence=0.9, needs_full_context=False,
        )

        ctx = assemble_context(event, CONTACT, intent, AGENT)

        assert ctx.conversation_summary == summary_text
        assert len(ctx.conversation_history) == 1


# ── Dispatcher hook ─────────────────────────────────────────────

class TestDispatcherSummarizationHook:
    @patch("app.services.summarization_service.generate_or_update_summary")
    @patch("app.services.summarization_service.should_summarize")
    def test_summarize_called_when_needed(self, mock_should, mock_generate):
        from app.pipeline.dispatcher import _maybe_summarize_conversation

        mock_should.return_value = True
        mock_generate.return_value = _make_summary()

        _maybe_summarize_conversation(AGENT_ID, CONTACT_ID)

        mock_should.assert_called_once_with(AGENT_ID, CONTACT_ID)
        mock_generate.assert_called_once_with(AGENT_ID, CONTACT_ID)

    @patch("app.services.summarization_service.should_summarize")
    def test_summarize_skipped_when_not_needed(self, mock_should):
        from app.pipeline.dispatcher import _maybe_summarize_conversation

        mock_should.return_value = False

        _maybe_summarize_conversation(AGENT_ID, CONTACT_ID)

        mock_should.assert_called_once()

    @patch("app.services.summarization_service.should_summarize")
    def test_summarize_failure_is_non_fatal(self, mock_should):
        from app.pipeline.dispatcher import _maybe_summarize_conversation

        mock_should.side_effect = Exception("Service down")

        # Should not raise
        _maybe_summarize_conversation(AGENT_ID, CONTACT_ID)
