"""
Hybrid search combining dense (FAISS) and sparse (BM25) retrieval.
"""
from typing import List, Dict
from dataclasses import dataclass
import numpy as np

try:
    from rank_bm25 import BM25Okapi
    BM25_AVAILABLE = True
except ImportError:
    BM25_AVAILABLE = False

from src.retrieval.types import RetrievedChunk


@dataclass
class HybridSearchConfig:
    """Configuration for hybrid search."""
    enabled: bool = True
    dense_weight: float = 0.7  # Weight for FAISS scores
    sparse_weight: float = 0.3  # Weight for BM25 scores
    top_k: int = 10


class HybridSearchEngine:
    """
    Combines dense (semantic) and sparse (keyword) search for better recall.
    
    Dense search (FAISS): Good for semantic similarity
    Sparse search (BM25): Good for exact keyword matches
    """
    
    def __init__(self, config: HybridSearchConfig | None = None):
        self.config = config or HybridSearchConfig()
        self.bm25 = None
        self.corpus = []
        self.chunks_lookup = {}
        
        if not BM25_AVAILABLE:
            print("Warning: rank-bm25 not available, hybrid search disabled")
            self.config.enabled = False
    
    def index_documents(self, chunks: List[Dict]):
        """
        Build BM25 index from document chunks.
        
        Args:
            chunks: List of chunk dictionaries with 'id', 'text', 'metadata'
        """
        if not self.config.enabled:
            return
        
        # Tokenize documents for BM25
        self.corpus = []
        self.chunks_lookup = {}
        
        for chunk in chunks:
            chunk_id = chunk.get('id', f"{chunk['metadata']['source']}_chunk_{len(self.corpus)}")
            text = chunk['text']
            tokens = text.lower().split()
            
            self.corpus.append(tokens)
            self.chunks_lookup[chunk_id] = chunk
        
        if self.corpus:
            try:
                self.bm25 = BM25Okapi(self.corpus)
                print(f"BM25 index built with {len(self.corpus)} documents")
            except Exception as e:
                print(f"Warning: Failed to build BM25 index: {e}")
                self.config.enabled = False
    
    def search_bm25(self, query: str, top_k: int = 10) -> List[tuple]:
        """
        Search using BM25.
        
        Returns:
            List of (chunk_index, score) tuples
        """
        if not self.config.enabled or not self.bm25:
            return []
        
        query_tokens = query.lower().split()
        scores = self.bm25.get_scores(query_tokens)
        
        # Get top k indices
        top_indices = np.argsort(scores)[::-1][:top_k]
        results = [(int(idx), float(scores[idx])) for idx in top_indices if scores[idx] > 0]
        
        return results
    
    def combine_results(
        self,
        dense_results: List[RetrievedChunk],
        sparse_results: List[tuple],
        query: str
    ) -> List[RetrievedChunk]:
        """
        Combine dense and sparse search results with weighted scoring.
        
        Args:
            dense_results: Results from FAISS (RetrievedChunk objects)
            sparse_results: Results from BM25 (index, score tuples)
            query: Original query
            
        Returns:
            Combined and reranked results
        """
        if not self.config.enabled:
            return dense_results[:self.config.top_k]
        
        # Normalize scores to [0, 1] range
        def normalize_scores(scores):
            if not scores:
                return []
            min_s = min(scores)
            max_s = max(scores)
            if max_s == min_s:
                return [1.0] * len(scores)
            return [(s - min_s) / (max_s - min_s) for s in scores]
        
        # Build score lookup for dense results
        dense_lookup = {}
        dense_scores = [chunk.score for chunk in dense_results]
        normalized_dense = normalize_scores(dense_scores)
        
        for chunk, norm_score in zip(dense_results, normalized_dense):
            key = f"{chunk.metadata['source']}_p{chunk.metadata['page']}"
            dense_lookup[key] = (chunk, norm_score)
        
        # Build score lookup for sparse results
        sparse_lookup = {}
        if sparse_results:
            sparse_scores = [score for _, score in sparse_results]
            normalized_sparse = normalize_scores(sparse_scores)
            
            for (idx, _), norm_score in zip(sparse_results, normalized_sparse):
                if idx < len(self.corpus):
                    chunk_data = list(self.chunks_lookup.values())[idx]
                    key = f"{chunk_data['metadata']['source']}_p{chunk_data['metadata']['page']}"
                    sparse_lookup[key] = (chunk_data, norm_score)
        
        # Combine scores
        combined = {}
        all_keys = set(dense_lookup.keys()) | set(sparse_lookup.keys())
        
        for key in all_keys:
            dense_score = dense_lookup[key][1] if key in dense_lookup else 0.0
            sparse_score = sparse_lookup[key][1] if key in sparse_lookup else 0.0
            
            # Weighted combination
            final_score = (
                self.config.dense_weight * dense_score +
                self.config.sparse_weight * sparse_score
            )
            
            # Get the chunk (prefer dense if available)
            if key in dense_lookup:
                chunk = dense_lookup[key][0]
            else:
                chunk_data = sparse_lookup[key][0]
                chunk = RetrievedChunk(
                    text=chunk_data['text'],
                    metadata=chunk_data['metadata'],
                    score=final_score,
                    distance=0.0
                )
            
            # Update score
            combined[key] = RetrievedChunk(
                text=chunk.text,
                metadata=chunk.metadata,
                score=final_score,
                distance=chunk.distance
            )
        
        # Sort by combined score
        sorted_chunks = sorted(combined.values(), key=lambda x: x.score, reverse=True)
        
        return sorted_chunks[:self.config.top_k]
