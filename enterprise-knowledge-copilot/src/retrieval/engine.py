import logging
from typing import Optional

from src.embeddings.vector_store import VectorStore
from src.retrieval.types import RetrievedChunk, RetrievalResult

try:
    from src.retrieval.reranker import Reranker, RerankConfig
    RERANKER_AVAILABLE = True
except ImportError:
    RERANKER_AVAILABLE = False

try:
    from src.retrieval.hybrid_search import HybridSearchEngine, HybridSearchConfig
    HYBRID_AVAILABLE = True
except ImportError:
    HYBRID_AVAILABLE = False

try:
    from src.retrieval.query_reformulation import QueryReformulator
    REFORMULATION_AVAILABLE = True
except ImportError:
    REFORMULATION_AVAILABLE = False


logger = logging.getLogger(__name__)


class RetrievalEngine:
    """
    Advanced retrieval engine with optional enhancements:
    - Query reformulation
    - Hybrid search (dense + sparse)
    - Reranking with cross-encoder
    """

    def __init__(
        self, 
        store: VectorStore, 
        default_top_k: int = 5,
        enable_reranking: bool = True,
        enable_hybrid_search: bool = True,
        enable_query_reformulation: bool = True
    ):
        self.store = store
        self.default_top_k = default_top_k
        
        # Initialize optional components
        self.reranker = None
        self.hybrid_search = None
        self.query_reformulator = None
        
        if enable_reranking and RERANKER_AVAILABLE:
            try:
                self.reranker = Reranker(RerankConfig(
                    enabled=True,
                    top_k_before_rerank=20,
                    top_k_after_rerank=default_top_k
                ))
                logger.info("Reranking enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize reranker: {e}")
        
        if enable_hybrid_search and HYBRID_AVAILABLE:
            try:
                self.hybrid_search = HybridSearchEngine(HybridSearchConfig(
                    enabled=True,
                    dense_weight=0.7,
                    sparse_weight=0.3,
                    top_k=default_top_k
                ))
                logger.info("Hybrid search enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize hybrid search: {e}")
        
        if enable_query_reformulation and REFORMULATION_AVAILABLE:
            try:
                self.query_reformulator = QueryReformulator(max_variations=3)
                logger.info("Query reformulation enabled")
            except Exception as e:
                logger.warning(f"Failed to initialize query reformulator: {e}")

    def retrieve(self, query: str, top_k: Optional[int] = None) -> RetrievalResult:
        if not query or not query.strip():
            raise ValueError("Query must be a non-empty string")

        limit = top_k or self.default_top_k
        logger.info("RetrievalEngine invoked | query=%s | top_k=%d", query, limit)
        
        # Step 1: Query reformulation (if enabled)
        queries_to_try = [query]
        if self.query_reformulator:
            try:
                reformulated = self.query_reformulator.reformulate(query)
                queries_to_try = reformulated
                logger.info(f"Query reformulated into {len(queries_to_try)} variations")
            except Exception as e:
                logger.warning(f"Query reformulation failed: {e}")
        
        # Step 2: Retrieve from multiple query variations
        all_chunks = []
        for q in queries_to_try:
            # Get more results if reranking is enabled
            retrieve_k = limit * 4 if self.reranker else limit
            
            store_results = self.store.search(q, retrieve_k)
            chunks = [
                RetrievedChunk(
                    text=record["text"],
                    metadata=record.get("metadata", {}),
                    score=float(record.get("score", 0.0)),
                    distance=float(record.get("distance", 0.0))
                )
                for record in store_results
            ]
            all_chunks.extend(chunks)
        
        # Deduplicate chunks by (source, page)
        seen = set()
        unique_chunks = []
        for chunk in all_chunks:
            key = (chunk.metadata.get('source'), chunk.metadata.get('page'))
            if key not in seen:
                seen.add(key)
                unique_chunks.append(chunk)
        
        # Sort by score
        unique_chunks.sort(key=lambda x: x.score, reverse=True)
        
        # Step 3: Hybrid search (if enabled)
        if self.hybrid_search and self.hybrid_search.config.enabled:
            try:
                # Get BM25 results
                bm25_results = self.hybrid_search.search_bm25(query, top_k=limit * 2)
                
                # Combine with dense results
                unique_chunks = self.hybrid_search.combine_results(
                    unique_chunks[:limit * 2],
                    bm25_results,
                    query
                )
                logger.info("Hybrid search applied")
            except Exception as e:
                logger.warning(f"Hybrid search failed: {e}")
        
        # Step 4: Reranking (if enabled)
        final_chunks = unique_chunks[:limit]
        if self.reranker and self.reranker.config.enabled and len(unique_chunks) > limit:
            try:
                final_chunks = self.reranker.rerank(query, unique_chunks[:limit * 2])
                logger.info("Reranking applied")
            except Exception as e:
                logger.warning(f"Reranking failed: {e}")
        
        # Final limit
        final_chunks = final_chunks[:limit]
        
        confidence = max((chunk.score for chunk in final_chunks), default=0.0)
        logger.info(
            "RetrievalEngine completed | query=%s | chunks=%d | confidence=%.3f",
            query,
            len(final_chunks),
            confidence
        )

        return RetrievalResult(query=query, chunks=final_chunks, confidence=confidence)
    
    def index_for_hybrid_search(self, chunks):
        """Build BM25 index for hybrid search."""
        if self.hybrid_search:
            try:
                self.hybrid_search.index_documents(chunks)
                logger.info("BM25 index built for hybrid search")
            except Exception as e:
                logger.warning(f"Failed to build BM25 index: {e}")
