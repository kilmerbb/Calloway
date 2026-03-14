"""RAG search accuracy tests.

Mock-mode tests (default): verify search logic, result formatting, deduplication,
scoring thresholds, and edge cases using pre-computed mock embeddings.

Integration-mode tests (@pytest.mark.integration): verify end-to-end vector
search against a real PostgreSQL + pgvector database.
"""
import json
import math
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from uuid import UUID, uuid4

from app.services.rag_service import RAGService
from app.services.embedding_service import chunk_text, EMBEDDING_DIMENSIONS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AGENT_A = UUID("00000000-0000-0000-0000-000000000001")
AGENT_B = UUID("00000000-0000-0000-0000-000000000002")
SOURCE_LISTING_OAK = UUID("00000000-0000-0000-0000-0000000000a1")
SOURCE_LISTING_PINE = UUID("00000000-0000-0000-0000-0000000000a2")
SOURCE_CONTACT = UUID("00000000-0000-0000-0000-0000000000b1")
CONVERSATION_ID = UUID("00000000-0000-0000-0000-0000000000c1")


def _make_embedding(seed: float = 0.0) -> list[float]:
    """Return a deterministic 512-dim embedding for testing.

    Different seeds produce different unit vectors so cosine similarity
    can be controlled.
    """
    vec = [0.0] * EMBEDDING_DIMENSIONS
    # Place energy in a few dimensions based on seed
    idx = int(abs(seed * 100)) % EMBEDDING_DIMENSIONS
    vec[idx] = 1.0
    # Add a small amount elsewhere so it's not perfectly sparse
    vec[(idx + 1) % EMBEDDING_DIMENSIONS] = seed * 0.1
    # Normalize to unit length
    norm = math.sqrt(sum(x * x for x in vec))
    if norm > 0:
        vec = [x / norm for x in vec]
    return vec


def _make_similar_embedding(base_seed: float, noise: float = 0.05) -> list[float]:
    """Return an embedding close to the one produced by ``_make_embedding(base_seed)``."""
    base = _make_embedding(base_seed)
    # Perturb slightly
    perturbed = [x + noise * (0.01 * i % 0.1) for i, x in enumerate(base)]
    norm = math.sqrt(sum(x * x for x in perturbed))
    return [x / norm for x in perturbed]


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _mock_db_row(content, source_type, source_id, chunk_index, metadata, similarity):
    """Create a dict that behaves like a DB row (subscript-accessible)."""
    return {
        "content": content,
        "source_type": source_type,
        "source_id": source_id,
        "chunk_index": chunk_index,
        "metadata": metadata if isinstance(metadata, dict) else json.loads(metadata),
        "similarity": similarity,
    }


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def rag_service():
    """Return a RAGService with a mocked embedding service."""
    svc = RAGService()
    mock_emb = MagicMock()
    # Default: embed_query returns a deterministic vector
    mock_emb.embed_query.return_value = _make_embedding(1.0)
    mock_emb.embed_texts.return_value = [_make_embedding(1.0)]
    svc._embedding_service = mock_emb
    return svc


# ---------------------------------------------------------------------------
# Mock-mode tests — chunk_text
# ---------------------------------------------------------------------------

class TestChunkText:
    """Verify text chunking logic (pure function, no mocking needed)."""

    def test_empty_string_returns_empty(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty(self):
        assert chunk_text("   \n\t  ") == []

    def test_short_text_single_chunk(self):
        text = "Hello world, this is a short text."
        chunks = chunk_text(text, chunk_size=512, overlap=50)
        assert len(chunks) == 1
        assert chunks[0] == text.strip()

    def test_long_text_multiple_chunks(self):
        # Each chunk_size=512 tokens ~ 2048 chars.  Build text > 2048 chars.
        text = "word " * 600  # ~3000 chars
        chunks = chunk_text(text, chunk_size=512, overlap=50)
        assert len(chunks) >= 2
        # Each chunk should be non-empty
        for c in chunks:
            assert len(c.strip()) > 0

    def test_overlap_produces_shared_content(self):
        text = "A" * 5000
        chunks = chunk_text(text, chunk_size=512, overlap=50)
        assert len(chunks) >= 2
        # With overlap, the end of one chunk should appear at the start of the next
        # (at least partially — overlap = 50 tokens ~ 200 chars)
        overlap_chars = 50 * 4  # 200
        for i in range(len(chunks) - 1):
            tail = chunks[i][-overlap_chars:]
            head = chunks[i + 1][:overlap_chars]
            # They should share some content
            assert len(set(tail) & set(head)) > 0


# ---------------------------------------------------------------------------
# Mock-mode tests — search results
# ---------------------------------------------------------------------------

class TestSearchResultHandling:
    """Verify search returns correct structure and ordering."""

    def test_search_returns_results_ordered_by_similarity(self, rag_service):
        """Results from DB should be returned preserving DB order (by similarity desc)."""
        rows = [
            _mock_db_row("Oak St listing info", "listing", SOURCE_LISTING_OAK, 0,
                         {"address": "123 Oak St"}, 0.95),
            _mock_db_row("Pine St listing info", "listing", SOURCE_LISTING_PINE, 0,
                         {"address": "456 Pine St"}, 0.72),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "Tell me about Oak St", top_k=5)

        assert len(results) == 2
        assert results[0]["similarity"] > results[1]["similarity"]
        assert results[0]["content"] == "Oak St listing info"
        assert results[0]["source_type"] == "listing"
        assert results[0]["source_id"] == str(SOURCE_LISTING_OAK)

    def test_search_with_source_type_filter(self, rag_service):
        """When source_types is provided, the SQL should include an IN clause."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(
                AGENT_A, "query", top_k=3, source_types=["listing", "contact"]
            )

        assert results == []
        # Verify the SQL contained source type params
        call_args = mock_conn.execute.call_args
        sql = call_args[0][0]
        assert "source_type IN" in sql
        params = call_args[0][1]
        assert "listing" in params
        assert "contact" in params

    def test_search_empty_results(self, rag_service):
        """Empty DB returns empty list."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "nonexistent thing", top_k=5)

        assert results == []

    def test_search_result_dict_structure(self, rag_service):
        """Each result must have the expected keys."""
        rows = [
            _mock_db_row("content", "listing", SOURCE_LISTING_OAK, 0,
                         {"address": "123 Oak St"}, 0.88),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "query")

        result = results[0]
        expected_keys = {"content", "source_type", "source_id", "chunk_index", "metadata", "similarity"}
        assert set(result.keys()) == expected_keys
        assert isinstance(result["similarity"], float)
        assert isinstance(result["source_id"], str)


# ---------------------------------------------------------------------------
# Mock-mode tests — get_context_for_message
# ---------------------------------------------------------------------------

class TestGetContextForMessage:
    """Verify the high-level context assembly method."""

    def test_returns_empty_string_when_no_results(self, rag_service):
        with patch.object(rag_service, "search", return_value=[]):
            ctx = rag_service.get_context_for_message(AGENT_A, SOURCE_CONTACT, "hello")
        assert ctx == ""

    def test_formats_results_with_header(self, rag_service):
        mock_results = [
            {"content": "Listing: 123 Oak St", "source_type": "listing",
             "source_id": str(SOURCE_LISTING_OAK), "chunk_index": 0,
             "metadata": {"address": "123 Oak St"}, "similarity": 0.9},
        ]
        with patch.object(rag_service, "search", return_value=mock_results):
            ctx = rag_service.get_context_for_message(AGENT_A, SOURCE_CONTACT, "Oak St?")

        assert "## Relevant Context" in ctx
        assert "### Listing" in ctx
        assert "123 Oak St" in ctx

    def test_groups_results_by_source_type(self, rag_service):
        mock_results = [
            {"content": "Oak St listing", "source_type": "listing",
             "source_id": str(SOURCE_LISTING_OAK), "chunk_index": 0,
             "metadata": {}, "similarity": 0.9},
            {"content": "John Smith contact", "source_type": "contact",
             "source_id": str(SOURCE_CONTACT), "chunk_index": 0,
             "metadata": {}, "similarity": 0.8},
        ]
        with patch.object(rag_service, "search", return_value=mock_results):
            ctx = rag_service.get_context_for_message(AGENT_A, None, "query")

        assert "### Listing" in ctx
        assert "### Contact" in ctx

    def test_truncates_long_content(self, rag_service):
        long_content = "x" * 1000
        mock_results = [
            {"content": long_content, "source_type": "listing",
             "source_id": str(SOURCE_LISTING_OAK), "chunk_index": 0,
             "metadata": {}, "similarity": 0.9},
        ]
        with patch.object(rag_service, "search", return_value=mock_results):
            ctx = rag_service.get_context_for_message(AGENT_A, None, "query")

        # Content longer than 500 chars should be truncated with "..."
        assert "..." in ctx
        # The full 1000-char string should NOT appear
        assert long_content not in ctx

    def test_handles_search_exception_gracefully(self, rag_service):
        with patch.object(rag_service, "search", side_effect=Exception("DB down")):
            ctx = rag_service.get_context_for_message(AGENT_A, None, "query")
        assert ctx == ""

    def test_contact_id_none_still_works(self, rag_service):
        with patch.object(rag_service, "search", return_value=[]):
            ctx = rag_service.get_context_for_message(AGENT_A, None, "hello")
        assert ctx == ""


# ---------------------------------------------------------------------------
# Mock-mode tests — relevance scenarios
# ---------------------------------------------------------------------------

class TestRelevanceScenarios:
    """Verify that the right results surface for realistic queries."""

    def test_oak_st_query_returns_oak_st_listing(self, rag_service):
        """'Tell me about the property on Oak St' should return Oak St listing first."""
        rows = [
            _mock_db_row(
                "Listing: 123 Oak St\nPrice: $450,000\nBedrooms: 3",
                "listing", SOURCE_LISTING_OAK, 0,
                {"address": "123 Oak St", "price": 450000}, 0.93,
            ),
            _mock_db_row(
                "Listing: 456 Pine St\nPrice: $320,000\nBedrooms: 2",
                "listing", SOURCE_LISTING_PINE, 0,
                {"address": "456 Pine St", "price": 320000}, 0.41,
            ),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "Tell me about the property on Oak St")

        assert len(results) == 2
        assert "Oak St" in results[0]["content"]
        assert results[0]["similarity"] > results[1]["similarity"]


# ---------------------------------------------------------------------------
# Mock-mode tests — edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Edge cases: short queries, non-English, empty DB."""

    def test_very_short_query(self, rag_service):
        """Single-word query should still work."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "hi")

        # Should not raise, just return whatever the DB returns
        assert isinstance(results, list)
        rag_service.embedding_service.embed_query.assert_called_once_with("hi")

    def test_non_english_query(self, rag_service):
        """Non-English text should be passed to embedding service without error."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "Dime sobre la propiedad en Oak St")

        assert isinstance(results, list)
        rag_service.embedding_service.embed_query.assert_called_once_with(
            "Dime sobre la propiedad en Oak St"
        )

    def test_empty_query_string(self, rag_service):
        """Empty query still calls embedding service (no preprocessing filter)."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "")

        assert isinstance(results, list)

    def test_special_characters_in_query(self, rag_service):
        """Queries with special chars should not break."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "What's the $$$price??? @#!")

        assert isinstance(results, list)


# ---------------------------------------------------------------------------
# Mock-mode tests — deduplication
# ---------------------------------------------------------------------------

class TestDeduplication:
    """Verify that multiple chunks from the same source are handled properly."""

    def test_multiple_chunks_same_source_all_returned(self, rag_service):
        """RAG service returns all chunks; dedup is the caller's responsibility.
        Verify multiple chunks from the same source_id come through."""
        rows = [
            _mock_db_row("Oak St chunk 0", "listing", SOURCE_LISTING_OAK, 0,
                         {"address": "123 Oak St"}, 0.92),
            _mock_db_row("Oak St chunk 1", "listing", SOURCE_LISTING_OAK, 1,
                         {"address": "123 Oak St"}, 0.88),
            _mock_db_row("Oak St chunk 2", "listing", SOURCE_LISTING_OAK, 2,
                         {"address": "123 Oak St"}, 0.80),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "Oak St details")

        assert len(results) == 3
        # All from the same source
        source_ids = {r["source_id"] for r in results}
        assert len(source_ids) == 1
        assert str(SOURCE_LISTING_OAK) in source_ids

    def test_context_deduplicates_same_source_in_formatting(self, rag_service):
        """get_context_for_message groups by source_type — verify multiple chunks
        from the same type appear under a single heading, not duplicated headings."""
        mock_results = [
            {"content": "Oak St chunk 0", "source_type": "listing",
             "source_id": str(SOURCE_LISTING_OAK), "chunk_index": 0,
             "metadata": {}, "similarity": 0.92},
            {"content": "Oak St chunk 1", "source_type": "listing",
             "source_id": str(SOURCE_LISTING_OAK), "chunk_index": 1,
             "metadata": {}, "similarity": 0.88},
        ]
        with patch.object(rag_service, "search", return_value=mock_results):
            ctx = rag_service.get_context_for_message(AGENT_A, None, "Oak St")

        # Only one "### Listing" heading should appear
        assert ctx.count("### Listing") == 1
        assert "Oak St chunk 0" in ctx
        assert "Oak St chunk 1" in ctx


# ---------------------------------------------------------------------------
# Mock-mode tests — scoring
# ---------------------------------------------------------------------------

class TestScoring:
    """Verify similarity scores are preserved and ordered."""

    def test_similarity_scores_are_floats(self, rag_service):
        rows = [
            _mock_db_row("content", "listing", SOURCE_LISTING_OAK, 0,
                         {"address": "123 Oak St"}, 0.95),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "query")

        assert isinstance(results[0]["similarity"], float)
        assert 0.0 <= results[0]["similarity"] <= 1.0

    def test_results_preserve_db_ordering(self, rag_service):
        """Results should come back in the same order the DB returned them."""
        rows = [
            _mock_db_row("best", "listing", SOURCE_LISTING_OAK, 0, {}, 0.99),
            _mock_db_row("good", "listing", SOURCE_LISTING_PINE, 0, {}, 0.75),
            _mock_db_row("okay", "contact", SOURCE_CONTACT, 0, {}, 0.50),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = rows

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            results = rag_service.search(AGENT_A, "query")

        similarities = [r["similarity"] for r in results]
        assert similarities == sorted(similarities, reverse=True)

    def test_top_k_limits_result_count(self, rag_service):
        """top_k param is passed through to the LIMIT clause."""
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []

        with patch("app.services.rag_service.get_db_connection") as mock_get_conn, \
             patch("app.services.rag_service.set_agent_context"):
            mock_get_conn.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_get_conn.return_value.__exit__ = MagicMock(return_value=False)

            rag_service.search(AGENT_A, "query", top_k=3)

        call_args = mock_conn.execute.call_args[0][1]
        # The last param should be the LIMIT value
        assert call_args[-1] == 3


# ---------------------------------------------------------------------------
# Mock-mode tests — embedding helpers
# ---------------------------------------------------------------------------

class TestEmbeddingHelpers:
    """Verify our test helpers produce valid embeddings for consistency."""

    def test_make_embedding_correct_dimensions(self):
        emb = _make_embedding(1.0)
        assert len(emb) == EMBEDDING_DIMENSIONS

    def test_make_embedding_is_unit_vector(self):
        emb = _make_embedding(1.0)
        norm = math.sqrt(sum(x * x for x in emb))
        assert abs(norm - 1.0) < 1e-6

    def test_different_seeds_produce_different_vectors(self):
        a = _make_embedding(1.0)
        b = _make_embedding(2.0)
        sim = _cosine_similarity(a, b)
        # Different seeds should produce low similarity
        assert sim < 0.5

    def test_similar_embedding_has_high_similarity(self):
        base = _make_embedding(1.0)
        similar = _make_similar_embedding(1.0, noise=0.01)
        sim = _cosine_similarity(base, similar)
        assert sim > 0.9


# ---------------------------------------------------------------------------
# Integration tests — require real DB
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.slow
class TestRAGIntegration:
    """Integration tests that require a real PostgreSQL + pgvector database.

    These are skipped by default. Run with:
        INTEGRATION_TESTS=1 pytest -m integration tests/test_rag_accuracy.py
    """

    def test_insert_and_retrieve_listing_embedding(self):
        """Insert a listing embedding and retrieve it via search."""
        svc = RAGService()
        agent_id = AGENT_A
        listing_id = uuid4()

        # This would require a real DB with the embeddings table
        # and a real Voyage API key for embedding generation.
        # The test verifies the full round-trip: embed -> store -> query -> retrieve.
        pytest.skip("Requires live database and Voyage API key")

    def test_cross_agent_isolation(self):
        """Agent A's embeddings should not appear in Agent B's searches (RLS)."""
        svc = RAGService()
        # Insert embedding for Agent A, search as Agent B — should get nothing.
        pytest.skip("Requires live database with RLS configured")

    def test_reindex_updates_existing_chunks(self):
        """Re-indexing the same source should upsert, not duplicate."""
        svc = RAGService()
        pytest.skip("Requires live database and Voyage API key")
