"""RAG indexer — background functions to index/re-index agent data for RAG."""
import logging
from uuid import UUID

from app.config import get_settings
from app.db.connection import get_db_connection, set_agent_context

logger = logging.getLogger(__name__)


def index_agent_data(agent_id: UUID) -> dict:
    """Index or re-index all data for an agent.

    Indexes all conversations, contacts, and listings.

    Returns:
        Dict with counts of indexed items per type.
    """
    settings = get_settings()
    if not settings.RAG_ENABLED:
        logger.info("RAG is disabled, skipping indexing for agent %s", agent_id)
        return {"skipped": True}

    from app.services.rag_service import get_rag_service
    rag = get_rag_service()
    counts = {"conversations": 0, "contacts": 0, "listings": 0, "errors": 0}

    # Index all conversations
    with get_db_connection() as conn:
        set_agent_context(conn, agent_id)
        conversations = conn.execute(
            "SELECT id FROM conversations WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchall()

    for row in conversations:
        try:
            rag.index_conversation(agent_id, row["id"])
            counts["conversations"] += 1
        except Exception as e:  # Broad catch: mixed DB + embedding API call
            logger.error("Failed to index conversation %s: %s", row["id"], e)
            counts["errors"] += 1

    # Index all contacts
    with get_db_connection() as conn:
        set_agent_context(conn, agent_id)
        contacts = conn.execute(
            "SELECT id FROM contacts WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchall()

    for row in contacts:
        try:
            rag.index_contact(agent_id, row["id"])
            counts["contacts"] += 1
        except Exception as e:  # Broad catch: mixed DB + embedding API call
            logger.error("Failed to index contact %s: %s", row["id"], e)
            counts["errors"] += 1

    # Index all listings
    with get_db_connection() as conn:
        set_agent_context(conn, agent_id)
        listings = conn.execute(
            "SELECT id FROM listings WHERE agent_id = %s",
            [str(agent_id)],
        ).fetchall()

    for row in listings:
        try:
            rag.index_listing(agent_id, row["id"])
            counts["listings"] += 1
        except Exception as e:  # Broad catch: mixed DB + embedding API call
            logger.error("Failed to index listing %s: %s", row["id"], e)
            counts["errors"] += 1

    logger.info(
        "RAG indexing complete for agent %s: %d conversations, %d contacts, "
        "%d listings, %d errors",
        agent_id, counts["conversations"], counts["contacts"],
        counts["listings"], counts["errors"],
    )
    return counts


def index_conversation_async(agent_id: UUID, conversation_id: UUID) -> None:
    """Index a single conversation after it's been saved.

    Call this after saving new messages to keep RAG up to date.
    Fails silently if RAG is disabled or indexing fails.
    """
    settings = get_settings()
    if not settings.RAG_ENABLED:
        return

    try:
        from app.services.rag_service import get_rag_service
        rag = get_rag_service()
        rag.index_conversation(agent_id, conversation_id)
    except Exception as e:  # Broad catch: RAG indexing is non-critical
        logger.warning(
            "Failed to index conversation %s for RAG (non-fatal): %s",
            conversation_id, e,
        )
