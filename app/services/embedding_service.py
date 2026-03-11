"""Embedding service using Voyage AI for RAG vector generation."""
import logging
import time
from typing import List

from app.config import get_settings

logger = logging.getLogger(__name__)

# voyage-3-lite outputs 512 dimensions
EMBEDDING_MODEL = "voyage-3-lite"
EMBEDDING_DIMENSIONS = 512
MAX_BATCH_SIZE = 128


class EmbeddingService:
    """Generate embeddings using Voyage AI."""

    def __init__(self, api_key: str | None = None):
        settings = get_settings()
        self._api_key = api_key or settings.VOYAGE_API_KEY
        self._client = None

    @property
    def client(self):
        """Lazy-init the Voyage client."""
        if self._client is None:
            if not self._api_key:
                raise RuntimeError("VOYAGE_API_KEY is not configured")
            import voyageai
            self._client = voyageai.Client(api_key=self._api_key)
        return self._client

    def embed_texts(
        self, texts: List[str], max_retries: int = 3
    ) -> List[List[float]]:
        """Embed a list of texts using Voyage AI with retry logic.

        Args:
            texts: List of text strings to embed (max 128 per batch).
            max_retries: Number of retries with exponential backoff.

        Returns:
            List of embedding vectors (each 512 floats).
        """
        if not texts:
            return []

        all_embeddings = []

        # Process in batches of MAX_BATCH_SIZE
        for i in range(0, len(texts), MAX_BATCH_SIZE):
            batch = texts[i : i + MAX_BATCH_SIZE]
            embeddings = self._embed_batch_with_retry(batch, max_retries)
            all_embeddings.extend(embeddings)

        return all_embeddings

    def embed_text(self, text: str, max_retries: int = 3) -> List[float]:
        """Embed a single text string.

        Args:
            text: Text to embed.
            max_retries: Number of retries with exponential backoff.

        Returns:
            Embedding vector (512 floats).
        """
        results = self.embed_texts([text], max_retries=max_retries)
        return results[0]

    def _embed_batch_with_retry(
        self, texts: List[str], max_retries: int
    ) -> List[List[float]]:
        """Embed a batch with exponential backoff retry."""
        for attempt in range(max_retries + 1):
            try:
                result = self.client.embed(
                    texts, model=EMBEDDING_MODEL, input_type="document"
                )
                return result.embeddings
            except Exception as e:
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "Voyage API error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, max_retries + 1, wait, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error("Voyage API failed after %d attempts: %s", max_retries + 1, e)
                    raise

    def embed_query(self, query: str, max_retries: int = 3) -> List[float]:
        """Embed a search query (uses 'query' input_type for better retrieval).

        Args:
            query: Search query text.
            max_retries: Number of retries with exponential backoff.

        Returns:
            Embedding vector (512 floats).
        """
        for attempt in range(max_retries + 1):
            try:
                result = self.client.embed(
                    [query], model=EMBEDDING_MODEL, input_type="query"
                )
                return result.embeddings[0]
            except Exception as e:
                if attempt < max_retries:
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "Voyage API query embed error (attempt %d/%d), retrying in %ds: %s",
                        attempt + 1, max_retries + 1, wait, e,
                    )
                    time.sleep(wait)
                else:
                    logger.error("Voyage API query embed failed after %d attempts: %s", max_retries + 1, e)
                    raise


def chunk_text(text: str, chunk_size: int = 512, overlap: int = 50) -> List[str]:
    """Split text into overlapping chunks by approximate token count.

    Uses a simple word-based approximation (1 token ~ 0.75 words).
    This avoids needing a tokenizer dependency.

    Args:
        text: Text to split.
        chunk_size: Target chunk size in tokens.
        overlap: Overlap between chunks in tokens.

    Returns:
        List of text chunks.
    """
    if not text or not text.strip():
        return []

    # Approximate: 1 token ≈ 4 characters (conservative)
    char_chunk_size = chunk_size * 4
    char_overlap = overlap * 4

    text = text.strip()

    if len(text) <= char_chunk_size:
        return [text]

    chunks = []
    start = 0

    while start < len(text):
        end = start + char_chunk_size

        # If this isn't the last chunk, try to break at a sentence or word boundary
        if end < len(text):
            # Look for sentence boundary near the end
            for boundary in [". ", ".\n", "\n\n", "\n", " "]:
                boundary_pos = text.rfind(boundary, start + char_chunk_size // 2, end)
                if boundary_pos != -1:
                    end = boundary_pos + len(boundary)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        # Move start forward, accounting for overlap
        start = end - char_overlap
        if start <= (end - char_chunk_size):
            # Prevent infinite loop if overlap is too large
            start = end

    return chunks


# Singleton
_service: EmbeddingService | None = None


def get_embedding_service() -> EmbeddingService:
    """Get the singleton EmbeddingService instance."""
    global _service
    if _service is None:
        _service = EmbeddingService()
    return _service
