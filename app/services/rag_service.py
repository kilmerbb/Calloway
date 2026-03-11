"""RAG service — index and retrieve contextual information for conversations."""
import json
import logging
from typing import List, Optional
from uuid import UUID

from app.config import get_settings
from app.db.connection import get_db_connection, set_agent_context
from app.services.embedding_service import (
    get_embedding_service,
    chunk_text,
    EMBEDDING_DIMENSIONS,
)

logger = logging.getLogger(__name__)


class RAGService:
    """Retrieval-Augmented Generation service for contextual memory."""

    def __init__(self):
        self._embedding_service = None

    @property
    def embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # ── Indexing ───────────────────────────────────────────────

    def index_conversation(self, agent_id: UUID, conversation_id: UUID) -> int:
        """Embed all messages in a conversation.

        Returns the number of chunks indexed.
        """
        with get_db_connection() as conn:
            set_agent_context(conn, agent_id)
            rows = conn.execute(
                """SELECT id, sender_type, body, created_at
                   FROM messages
                   WHERE conversation_id = %s
                   ORDER BY created_at""",
                [str(conversation_id)],
            ).fetchall()

        if not rows:
            return 0

        # Combine messages into a single text block for the conversation
        parts = []
        for row in rows:
            sender = "Agent" if row["sender_type"] == "agent" else "Client"
            parts.append(f"{sender}: {row['body']}")

        full_text = "\n".join(parts)
        settings = get_settings()
        chunks = chunk_text(
            full_text,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )

        if not chunks:
            return 0

        metadata = {"conversation_id": str(conversation_id)}
        self._upsert_chunks(agent_id, "conversation", conversation_id, chunks, metadata)
        return len(chunks)

    def index_contact(self, agent_id: UUID, contact_id: UUID) -> int:
        """Embed a contact's profile, preferences, and notes.

        Returns the number of chunks indexed.
        """
        with get_db_connection() as conn:
            set_agent_context(conn, agent_id)
            row = conn.execute(
                "SELECT * FROM contacts WHERE id = %s",
                [str(contact_id)],
            ).fetchone()

        if not row:
            return 0

        # Build a text representation of the contact
        parts = [
            f"Contact: {row['name']}",
            f"Phone: {row['phone']}",
            f"Role: {row['role']}",
            f"Stage: {row['lifecycle_stage']}",
        ]
        if row.get("email"):
            parts.append(f"Email: {row['email']}")
        if row.get("preferences"):
            prefs = row["preferences"]
            if isinstance(prefs, str):
                prefs = json.loads(prefs)
            if prefs:
                parts.append(f"Preferences: {json.dumps(prefs)}")
        if row.get("notes"):
            parts.append(f"Notes: {row['notes']}")
        if row.get("lead_source"):
            parts.append(f"Lead source: {row['lead_source']}")

        # Also fetch lead_preferences if they exist
        with get_db_connection() as conn:
            set_agent_context(conn, agent_id)
            lp = conn.execute(
                "SELECT * FROM lead_preferences WHERE contact_id = %s",
                [str(contact_id)],
            ).fetchone()

        if lp:
            lp_parts = []
            if lp.get("areas"):
                lp_parts.append(f"Areas: {', '.join(lp['areas'])}")
            if lp.get("timeline"):
                lp_parts.append(f"Timeline: {lp['timeline']}")
            if lp.get("price_min") or lp.get("price_max"):
                lp_parts.append(
                    f"Budget: ${lp.get('price_min', '?'):,}-${lp.get('price_max', '?'):,}"
                )
            if lp.get("bedrooms_min"):
                lp_parts.append(f"Min beds: {lp['bedrooms_min']}")
            if lp.get("property_type"):
                lp_parts.append(f"Property type: {lp['property_type']}")
            if lp_parts:
                parts.append("Lead preferences: " + "; ".join(lp_parts))

        full_text = "\n".join(parts)
        settings = get_settings()
        chunks = chunk_text(
            full_text,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )

        if not chunks:
            return 0

        metadata = {"contact_name": row["name"]}
        self._upsert_chunks(agent_id, "contact", contact_id, chunks, metadata)
        return len(chunks)

    def index_listing(self, agent_id: UUID, listing_id: UUID) -> int:
        """Embed listing details.

        Returns the number of chunks indexed.
        """
        with get_db_connection() as conn:
            set_agent_context(conn, agent_id)
            row = conn.execute(
                "SELECT * FROM listings WHERE id = %s",
                [str(listing_id)],
            ).fetchone()

        if not row:
            return 0

        parts = [
            f"Listing: {row['address']}",
            f"Price: ${row['price']:,}",
        ]
        if row.get("beds"):
            parts.append(f"Bedrooms: {row['beds']}")
        if row.get("baths"):
            parts.append(f"Bathrooms: {row['baths']}")
        if row.get("sqft"):
            parts.append(f"Square feet: {row['sqft']:,}")
        if row.get("hoa"):
            parts.append(f"HOA: ${row['hoa']}/month")
        if row.get("features"):
            features = row["features"]
            if isinstance(features, str):
                features = json.loads(features)
            if features:
                parts.append(f"Features: {', '.join(features)}")
        if row.get("showing_instructions"):
            parts.append(f"Showing instructions: {row['showing_instructions']}")
        if row.get("notes"):
            parts.append(f"Notes: {row['notes']}")
        if row.get("status"):
            parts.append(f"Status: {row['status']}")

        full_text = "\n".join(parts)
        settings = get_settings()
        chunks = chunk_text(
            full_text,
            chunk_size=settings.RAG_CHUNK_SIZE,
            overlap=settings.RAG_CHUNK_OVERLAP,
        )

        if not chunks:
            return 0

        metadata = {"address": row["address"], "price": row["price"]}
        self._upsert_chunks(agent_id, "listing", listing_id, chunks, metadata)
        return len(chunks)

    def _upsert_chunks(
        self,
        agent_id: UUID,
        source_type: str,
        source_id: UUID,
        chunks: List[str],
        metadata: dict,
    ) -> None:
        """Embed and upsert chunks into the embeddings table.

        Uses ON CONFLICT on (source_id, chunk_index) for deduplication.
        """
        embeddings = self.embedding_service.embed_texts(chunks)

        with get_db_connection() as conn:
            set_agent_context(conn, agent_id)

            # Delete any old chunks beyond the current count (handles re-indexing
            # where the content got shorter)
            conn.execute(
                """DELETE FROM embeddings
                   WHERE source_id = %s AND chunk_index >= %s""",
                [str(source_id), len(chunks)],
            )

            for i, (chunk, embedding) in enumerate(zip(chunks, embeddings)):
                conn.execute(
                    """INSERT INTO embeddings
                       (agent_id, source_type, source_id, chunk_index, content,
                        embedding, metadata, updated_at)
                       VALUES (%s, %s, %s, %s, %s, %s::vector, %s, now())
                       ON CONFLICT (source_id, chunk_index)
                       DO UPDATE SET
                           content = EXCLUDED.content,
                           embedding = EXCLUDED.embedding,
                           metadata = EXCLUDED.metadata,
                           updated_at = now()""",
                    [
                        str(agent_id),
                        source_type,
                        str(source_id),
                        i,
                        chunk,
                        str(embedding),
                        json.dumps(metadata),
                    ],
                )
            conn.commit()

        logger.info(
            "Indexed %d chunks for %s/%s (agent %s)",
            len(chunks), source_type, source_id, agent_id,
        )

    # ── Search ─────────────────────────────────────────────────

    def search(
        self,
        agent_id: UUID,
        query: str,
        top_k: int = 5,
        source_types: Optional[List[str]] = None,
    ) -> List[dict]:
        """Search for relevant chunks using cosine similarity.

        Args:
            agent_id: Agent to search within (RLS enforced).
            query: Search query text.
            top_k: Number of results to return.
            source_types: Optional filter by source type(s).

        Returns:
            List of dicts with keys: content, source_type, source_id,
            chunk_index, metadata, similarity.
        """
        query_embedding = self.embedding_service.embed_query(query)

        type_filter = ""
        params = [str(agent_id), str(query_embedding), top_k]

        if source_types:
            placeholders = ", ".join(["%s"] * len(source_types))
            type_filter = f"AND source_type IN ({placeholders})"
            params = [str(agent_id)] + source_types + [str(query_embedding), top_k]

        if source_types:
            sql = f"""
                SELECT content, source_type, source_id, chunk_index, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM embeddings
                WHERE agent_id = %s AND source_type IN ({", ".join(["%s"] * len(source_types))})
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params = [
                str(query_embedding),
                str(agent_id),
                *source_types,
                str(query_embedding),
                top_k,
            ]
        else:
            sql = """
                SELECT content, source_type, source_id, chunk_index, metadata,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM embeddings
                WHERE agent_id = %s
                ORDER BY embedding <=> %s::vector
                LIMIT %s
            """
            params = [
                str(query_embedding),
                str(agent_id),
                str(query_embedding),
                top_k,
            ]

        with get_db_connection() as conn:
            set_agent_context(conn, agent_id)
            rows = conn.execute(sql, params).fetchall()

        return [
            {
                "content": row["content"],
                "source_type": row["source_type"],
                "source_id": str(row["source_id"]),
                "chunk_index": row["chunk_index"],
                "metadata": row["metadata"],
                "similarity": float(row["similarity"]),
            }
            for row in rows
        ]

    def get_context_for_message(
        self,
        agent_id: UUID,
        contact_id: UUID | None,
        message_text: str,
    ) -> str:
        """High-level function to retrieve relevant context for an inbound message.

        Searches across all source types and formats results into a string
        ready to inject into the LLM system prompt.

        Args:
            agent_id: The agent receiving the message.
            contact_id: The contact sending the message (optional).
            message_text: The inbound message text.

        Returns:
            Formatted context string, or empty string if nothing found.
        """
        settings = get_settings()

        try:
            results = self.search(
                agent_id=agent_id,
                query=message_text,
                top_k=settings.RAG_TOP_K,
            )
        except Exception as e:
            logger.warning("RAG search failed, proceeding without context: %s", e)
            return ""

        if not results:
            return ""

        # Format results grouped by source type
        sections = {}
        for result in results:
            stype = result["source_type"]
            if stype not in sections:
                sections[stype] = []
            sections[stype].append(result["content"])

        parts = ["## Relevant Context"]
        for stype, contents in sections.items():
            label = stype.replace("_", " ").title()
            parts.append(f"\n### {label}")
            for content in contents:
                # Truncate very long chunks for prompt efficiency
                if len(content) > 500:
                    content = content[:500] + "..."
                parts.append(content)

        return "\n".join(parts)


# Singleton
_service: RAGService | None = None


def get_rag_service() -> RAGService:
    """Get the singleton RAGService instance."""
    global _service
    if _service is None:
        _service = RAGService()
    return _service
