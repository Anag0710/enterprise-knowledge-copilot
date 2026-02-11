from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class RetrievedChunk:
    """Normalized representation of a chunk returned by FAISS."""

    text: str
    metadata: Dict[str, Any]
    score: float
    distance: float


@dataclass
class RetrievalResult:
    """Container for retrieved evidence and aggregate confidence."""

    query: str
    chunks: List[RetrievedChunk]
    confidence: float

    def top_sources(self, limit: int = 3) -> List[Dict[str, Any]]:
        unique_sources = []
        seen = set()
        for chunk in self.chunks:
            key = (chunk.metadata.get("source"), chunk.metadata.get("page"))
            if key in seen:
                continue
            seen.add(key)
            unique_sources.append({
                "source": chunk.metadata.get("source", "unknown"),
                "page": chunk.metadata.get("page"),
                "chunk": chunk.metadata.get("chunk")
            })
            if len(unique_sources) >= limit:
                break
        return unique_sources
