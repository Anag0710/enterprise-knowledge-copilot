"""
Reranking layer to improve retrieval relevance.
Uses cross-encoder models to score query-document pairs.
"""
from typing import List
from dataclasses import dataclass

try:
    from sentence_transformers import CrossEncoder
    CROSS_ENCODER_AVAILABLE = True
except ImportError:
    CROSS_ENCODER_AVAILABLE = False

from src.retrieval.types import RetrievedChunk, RetrievalResult


@dataclass
class RerankConfig:
    """Configuration for reranking."""
    enabled: bool = True
    model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    top_k_before_rerank: int = 20  # Retrieve top 20 initially
    top_k_after_rerank: int = 5    # Return top 5 after reranking
    batch_size: int = 32


class Reranker:
    """
    Rerank retrieved chunks using a cross-encoder model.
    
    Cross-encoders jointly encode query + document for better relevance scoring
    but are slower than bi-encoders, so we use them only on top candidates.
    """
    
    def __init__(self, config: RerankConfig | None = None):
        self.config = config or RerankConfig()
        self.model = None
        
        if self.config.enabled:
            if not CROSS_ENCODER_AVAILABLE:
                print("Warning: sentence-transformers not available for reranking")
                self.config.enabled = False
            else:
                try:
                    self.model = CrossEncoder(self.config.model_name)
                    print(f"Reranker loaded: {self.config.model_name}")
                except Exception as e:
                    print(f"Warning: Failed to load reranker: {e}")
                    self.config.enabled = False
    
    def rerank(self, query: str, chunks: List[RetrievedChunk]) -> List[RetrievedChunk]:
        """
        Rerank the retrieved chunks using cross-encoder scoring.
        
        Args:
            query: User's query
            chunks: Initial retrieved chunks
            
        Returns:
            Reranked chunks (limited to top_k_after_rerank)
        """
        if not self.config.enabled or not self.model or not chunks:
            return chunks[:self.config.top_k_after_rerank]
        
        # Prepare query-document pairs
        pairs = [[query, chunk.text] for chunk in chunks]
        
        # Get cross-encoder scores
        try:
            scores = self.model.predict(pairs, batch_size=self.config.batch_size)
            
            # Combine chunks with new scores
            scored_chunks = []
            for chunk, score in zip(chunks, scores):
                # Create new chunk with reranked score
                reranked_chunk = RetrievedChunk(
                    text=chunk.text,
                    metadata=chunk.metadata,
                    score=float(score),  # Use cross-encoder score
                    distance=chunk.distance  # Preserve original distance
                )
                scored_chunks.append(reranked_chunk)
            
            # Sort by new scores (descending)
            scored_chunks.sort(key=lambda x: x.score, reverse=True)
            
            return scored_chunks[:self.config.top_k_after_rerank]
        
        except Exception as e:
            print(f"Warning: Reranking failed: {e}")
            return chunks[:self.config.top_k_after_rerank]
    
    def rerank_result(self, query: str, result: RetrievalResult) -> RetrievalResult:
        """
        Rerank a RetrievalResult object.
        
        Args:
            query: User's query
            result: Original retrieval result
            
        Returns:
            New RetrievalResult with reranked chunks
        """
        reranked_chunks = self.rerank(query, result.chunks)
        
        # Recalculate confidence from reranked scores
        new_confidence = max([chunk.score for chunk in reranked_chunks]) if reranked_chunks else 0.0
        
        return RetrievalResult(
            query=result.query,
            chunks=reranked_chunks,
            confidence=new_confidence
        )
