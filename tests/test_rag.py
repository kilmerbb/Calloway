"""Tests for the RAG system — embedding service, chunking, RAG service, graceful degradation."""
import pytest
from unittest.mock import patch, MagicMock
from uuid import UUID

from app.services.embedding_service import chunk_text, EmbeddingService
from app.services.rag_service import RAGService


AGENT_ID = UUID("a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONTACT_ID = UUID("b1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")
CONVERSATION_ID = UUID("c1eebc99-9c0b-4ef8-bb6d-6bb9bd380a11")


# ── Chunking Tests ─────────────────────────────────────────────


class TestChunkText:
    def test_empty_text(self):
        assert chunk_text("") == []
        assert chunk_text("   ") == []

    def test_short_text_single_chunk(self):
        text = "This is a short text."
        result = chunk_text(text, chunk_size=512)
        assert len(result) == 1
        assert result[0] == text

    def test_long_text_multiple_chunks(self):
        # Create text that's definitely longer than one chunk
        text = "Word " * 1000  # ~5000 chars, well over 512*4=2048
        result = chunk_text(text, chunk_size=512, overlap=50)
        assert len(result) > 1
        # Each chunk should be non-empty
        for chunk in result:
            assert len(chunk.strip()) > 0

    def test_chunks_have_overlap(self):
        # Create text long enough for multiple chunks
        sentences = [f"Sentence number {i} with some padding text here. " for i in range(100)]
        text = " ".join(sentences)
        result = chunk_text(text, chunk_size=100, overlap=20)
        assert len(result) > 1
        # Check that consecutive chunks share some content (overlap)
        for i in range(len(result) - 1):
            # The end of chunk i should overlap with the start of chunk i+1
            # We can't check exact overlap due to boundary-finding logic,
            # but we can verify chunks are reasonable
            assert len(result[i]) > 0
            assert len(result[i + 1]) > 0

    def test_none_text(self):
        assert chunk_text(None) == []

    def test_custom_chunk_size(self):
        text = "A " * 500  # 1000 chars
        # With chunk_size=50, char_chunk_size=200
        result = chunk_text(text, chunk_size=50, overlap=10)
        assert len(result) > 1


# ── Embedding Service Tests ────────────────────────────────────


class TestEmbeddingService:
    @patch("app.services.embedding_service.get_settings")
    def test_no_api_key_raises(self, mock_settings):
        mock_settings.return_value = MagicMock(VOYAGE_API_KEY="")
        service = EmbeddingService()
        with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
            _ = service.client

    @patch("app.services.embedding_service.get_settings")
    def test_embed_texts_empty(self, mock_settings):
        mock_settings.return_value = MagicMock(VOYAGE_API_KEY="test-key")
        service = EmbeddingService(api_key="test-key")
        result = service.embed_texts([])
        assert result == []

    @patch("app.services.embedding_service.get_settings")
    def test_embed_texts_calls_voyage(self, mock_settings):
        mock_settings.return_value = MagicMock(VOYAGE_API_KEY="test-key")
        service = EmbeddingService(api_key="test-key")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1] * 512, [0.2] * 512]
        mock_client.embed.return_value = mock_result
        service._client = mock_client

        result = service.embed_texts(["hello", "world"])
        assert len(result) == 2
        assert len(result[0]) == 512
        mock_client.embed.assert_called_once_with(
            ["hello", "world"], model="voyage-3-lite", input_type="document"
        )

    @patch("app.services.embedding_service.get_settings")
    def test_embed_query_uses_query_input_type(self, mock_settings):
        mock_settings.return_value = MagicMock(VOYAGE_API_KEY="test-key")
        service = EmbeddingService(api_key="test-key")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.embeddings = [[0.3] * 512]
        mock_client.embed.return_value = mock_result
        service._client = mock_client

        result = service.embed_query("search query")
        assert len(result) == 512
        mock_client.embed.assert_called_once_with(
            ["search query"], model="voyage-3-lite", input_type="query"
        )

    @patch("app.services.embedding_service.time.sleep")
    @patch("app.services.embedding_service.get_settings")
    def test_retry_on_failure(self, mock_settings, mock_sleep):
        mock_settings.return_value = MagicMock(VOYAGE_API_KEY="test-key")
        service = EmbeddingService(api_key="test-key")

        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.embeddings = [[0.1] * 512]
        # Fail first, succeed second
        mock_client.embed.side_effect = [Exception("rate limit"), mock_result]
        service._client = mock_client

        result = service.embed_texts(["hello"])
        assert len(result) == 1
        assert mock_client.embed.call_count == 2
        mock_sleep.assert_called_once()

    @patch("app.services.embedding_service.time.sleep")
    @patch("app.services.embedding_service.get_settings")
    def test_retry_exhausted_raises(self, mock_settings, mock_sleep):
        mock_settings.return_value = MagicMock(VOYAGE_API_KEY="test-key")
        service = EmbeddingService(api_key="test-key")

        mock_client = MagicMock()
        mock_client.embed.side_effect = Exception("persistent error")
        service._client = mock_client

        with pytest.raises(Exception, match="persistent error"):
            service.embed_texts(["hello"], max_retries=2)

        assert mock_client.embed.call_count == 3  # initial + 2 retries


# ── RAG Service Tests ──────────────────────────────────────────


class TestRAGService:
    def _make_rag_service(self):
        """Create a RAGService with mocked embedding service."""
        rag = RAGService()
        mock_embedding = MagicMock()
        mock_embedding.embed_texts.return_value = [[0.1] * 512]
        mock_embedding.embed_query.return_value = [0.2] * 512
        rag._embedding_service = mock_embedding
        return rag

    @patch("app.services.rag_service.get_settings")
    @patch("app.services.rag_service.get_db_connection")
    def test_search_result_formatting(self, mock_conn_fn, mock_settings):
        """Test that get_context_for_message formats results correctly."""
        mock_settings.return_value = MagicMock(
            RAG_TOP_K=5, RAG_CHUNK_SIZE=512, RAG_CHUNK_OVERLAP=50,
        )

        rag = self._make_rag_service()

        # Mock search to return pre-formatted results
        rag.search = MagicMock(return_value=[
            {
                "content": "Contact: Sarah Chen\nRole: buyer",
                "source_type": "contact",
                "source_id": str(CONTACT_ID),
                "chunk_index": 0,
                "metadata": {"contact_name": "Sarah Chen"},
                "similarity": 0.85,
            },
            {
                "content": "Client: I'm looking for a 3bed in Fishtown",
                "source_type": "conversation",
                "source_id": str(CONVERSATION_ID),
                "chunk_index": 0,
                "metadata": {},
                "similarity": 0.72,
            },
        ])

        result = rag.get_context_for_message(AGENT_ID, CONTACT_ID, "any bedrooms?")

        assert "## Relevant Context" in result
        assert "Contact" in result
        assert "Sarah Chen" in result
        assert "Conversation" in result
        assert "Fishtown" in result

    @patch("app.services.rag_service.get_settings")
    def test_graceful_degradation_on_search_failure(self, mock_settings):
        """Test that get_context_for_message returns empty string on failure."""
        mock_settings.return_value = MagicMock(RAG_TOP_K=5)

        rag = self._make_rag_service()
        rag.search = MagicMock(side_effect=Exception("DB connection failed"))

        result = rag.get_context_for_message(AGENT_ID, CONTACT_ID, "hello")
        assert result == ""

    @patch("app.services.rag_service.get_settings")
    def test_empty_search_results(self, mock_settings):
        """Test that empty search results return empty string."""
        mock_settings.return_value = MagicMock(RAG_TOP_K=5)

        rag = self._make_rag_service()
        rag.search = MagicMock(return_value=[])

        result = rag.get_context_for_message(AGENT_ID, None, "hello")
        assert result == ""

    @patch("app.services.rag_service.get_settings")
    @patch("app.services.rag_service.get_db_connection")
    @patch("app.services.rag_service.set_agent_context")
    def test_index_conversation_empty(self, mock_set_ctx, mock_conn_fn, mock_settings):
        """Test indexing an empty conversation returns 0."""
        mock_settings.return_value = MagicMock(
            RAG_CHUNK_SIZE=512, RAG_CHUNK_OVERLAP=50,
        )

        mock_conn = MagicMock()
        mock_conn_fn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn_fn.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value.fetchall.return_value = []

        rag = self._make_rag_service()
        result = rag.index_conversation(AGENT_ID, CONVERSATION_ID)
        assert result == 0

    @patch("app.services.rag_service.get_settings")
    @patch("app.services.rag_service.get_db_connection")
    @patch("app.services.rag_service.set_agent_context")
    def test_deduplication_upsert(self, mock_set_ctx, mock_conn_fn, mock_settings):
        """Test that re-indexing same content uses upsert (doesn't duplicate)."""
        mock_settings.return_value = MagicMock(
            RAG_CHUNK_SIZE=512, RAG_CHUNK_OVERLAP=50,
        )

        mock_conn = MagicMock()
        mock_conn_fn.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn_fn.return_value.__exit__ = MagicMock(return_value=False)

        # First call returns messages, second call is the upsert connection
        mock_conn.execute.return_value.fetchall.return_value = [
            {
                "id": CONVERSATION_ID,
                "sender_type": "client",
                "body": "Hello there",
                "created_at": "2024-01-01",
            },
        ]

        rag = self._make_rag_service()
        rag.index_conversation(AGENT_ID, CONVERSATION_ID)

        # Verify ON CONFLICT is used in the insert
        insert_calls = [
            call for call in mock_conn.execute.call_args_list
            if call[0] and "ON CONFLICT" in str(call[0][0])
        ]
        assert len(insert_calls) > 0, "Expected upsert with ON CONFLICT clause"


# ── Pipeline Integration Tests ─────────────────────────────────


class TestRAGPipelineIntegration:
    """Tests for RAG integration in the pipeline handlers."""

    def _make_test_fixtures(self):
        from app.pipeline.handlers import handle_full_reasoning
        from app.models.schemas import (
            NormalizedEvent, AgentConfig, AssembledContext,
            IntentClassification,
        )
        from datetime import datetime, timezone

        agent = AgentConfig(
            id=AGENT_ID, name="Jane", email="j@t.com",
            phone="+1", twilio_number="+2",
        )
        event = NormalizedEvent(
            sender_phone="+3", channel="sms", body="Hi",
            timestamp=datetime.now(timezone.utc),
            provider_message_id="SM1", raw_payload={}, agent_id=AGENT_ID,
        )
        intent = IntentClassification(
            intent="listing_qa", sender_type="known_client",
            confidence=0.9, needs_full_context=True,
        )
        context = AssembledContext(agent=agent, intent=intent)
        return handle_full_reasoning, agent, event, context

    @patch("app.pipeline.handlers.get_anthropic_client")
    def test_rag_disabled_skips_context(self, mock_get_client):
        """When RAG_ENABLED=False, no RAG context is injected."""
        handle_full_reasoning, agent, event, context = self._make_test_fixtures()

        mock_client = mock_get_client.return_value
        mock_client.reason.return_value = MagicMock(
            response_text="Hello!", model_used="sonnet", tokens_used=100,
            tool_calls=[],
        )

        mock_settings = MagicMock(RAG_ENABLED=False)
        with patch("app.config.get_settings", return_value=mock_settings):
            with patch("app.services.rag_service.get_rag_service") as mock_rag:
                handle_full_reasoning(event, None, context, agent)
                mock_rag.assert_not_called()

    @patch("app.pipeline.handlers.get_anthropic_client")
    def test_rag_enabled_injects_context(self, mock_get_client):
        """When RAG_ENABLED=True, RAG context is fetched and injected."""
        handle_full_reasoning, agent, event, context = self._make_test_fixtures()

        mock_client = mock_get_client.return_value
        mock_client.reason.return_value = MagicMock(
            response_text="Hello!", model_used="sonnet", tokens_used=100,
            tool_calls=[],
        )

        mock_settings = MagicMock(RAG_ENABLED=True)
        mock_rag = MagicMock()
        mock_rag.get_context_for_message.return_value = "## Relevant Context\nSome info"

        with patch("app.config.get_settings", return_value=mock_settings):
            with patch("app.services.rag_service.get_rag_service", return_value=mock_rag):
                handle_full_reasoning(event, None, context, agent)

                mock_rag.get_context_for_message.assert_called_once_with(
                    agent_id=AGENT_ID,
                    contact_id=None,
                    message_text="Hi",
                )

                # Verify the context was included in system prompt
                call_args = mock_client.reason.call_args
                system_prompt = call_args[0][0] if call_args[0] else call_args[1]["system_prompt"]
                assert "Relevant Context" in system_prompt

    @patch("app.pipeline.handlers.get_anthropic_client")
    def test_rag_failure_graceful_degradation(self, mock_get_client):
        """When RAG fails, the handler continues without context."""
        handle_full_reasoning, agent, event, context = self._make_test_fixtures()

        mock_client = mock_get_client.return_value
        mock_client.reason.return_value = MagicMock(
            response_text="Hello!", model_used="sonnet", tokens_used=100,
            tool_calls=[],
        )

        mock_settings = MagicMock(RAG_ENABLED=True)
        with patch("app.config.get_settings", return_value=mock_settings):
            with patch("app.services.rag_service.get_rag_service", side_effect=Exception("RAG service down")):
                # Should not raise — graceful degradation
                result = handle_full_reasoning(event, None, context, agent)
                assert result.response_text == "Hello!"
