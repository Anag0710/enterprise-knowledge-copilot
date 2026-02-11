import logging
from typing import Optional

from src.embeddings.vector_store import VectorStore
from src.retrieval.types import RetrievedChunk, RetrievalResult


logger = logging.getLogger(__name__)


class RetrievalEngine:
    """Thin layer over the vector store that normalizes outputs."""

    def __init__(self, store: VectorStore, default_top_k: int = 5):
        self.store = store
        self.default_top_k = default_top_k

    def retrieve(self, query: str, top_k: Optional[int] = None) -> RetrievalResult:
        if not query or not query.strip():
            raise ValueError("Query must be a non-empty string")

        limit = top_k or self.default_top_k
        logger.info("RetrievalEngine invoked | query=%s | top_k=%d", query, limit)

        store_results = self.store.search(query, limit)
        chunks = [
            RetrievedChunk(
                text=record["text"],
                metadata=record.get("metadata", {}),
                score=float(record.get("score", 0.0)),
                distance=float(record.get("distance", 0.0))
            )
            for record in store_results
        ]

        confidence = max((chunk.score for chunk in chunks), default=0.0)
        logger.info(
            "RetrievalEngine completed | query=%s | chunks=%d | confidence=%.3f",
            query,
            len(chunks),
            confidence
        )

        return RetrievalResult(query=query, chunks=chunks, confidence=confidence)
