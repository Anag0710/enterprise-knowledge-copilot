"""
Caching layer for frequently asked questions.
"""
import hashlib
from typing import Optional
from cachetools import TTLCache, LRUCache
from dataclasses import asdict
import json

from src.agent.types import AgentResponse


class ResponseCache:
    """
    In-memory cache for agent responses.
    
    Supports:
    - TTL (Time-To-Live) based expiration
    - LRU (Least Recently Used) eviction
    - Query normalization for better hit rates
    """
    
    def __init__(
        self,
        max_size: int = 1000,
        ttl_seconds: int = 3600,  # 1 hour default
        use_ttl: bool = True
    ):
        """
        Initialize response cache.
        
        Args:
            max_size: Maximum number of cached responses
            ttl_seconds: Time-to-live for cached entries (seconds)
            use_ttl: If True, use TTL cache; if False, use LRU only
        """
        if use_ttl:
            self.cache = TTLCache(maxsize=max_size, ttl=ttl_seconds)
        else:
            self.cache = LRUCache(maxsize=max_size)
        
        self.hits = 0
        self.misses = 0
    
    def _normalize_query(self, query: str) -> str:
        """
        Normalize query for consistent cache keys.
        
        - Convert to lowercase
        - Remove extra whitespace
        - Strip punctuation at ends
        """
        normalized = query.lower().strip()
        normalized = ' '.join(normalized.split())
        normalized = normalized.strip('.?!')
        return normalized
    
    def _make_key(self, query: str, conversation_history: list) -> str:
        """
        Create cache key from query and conversation history.
        
        Uses hash of normalized content for consistent keys.
        """
        normalized_query = self._normalize_query(query)
        
        # Include conversation history in key
        history_str = "|".join([self._normalize_query(q) for q in conversation_history])
        full_key = f"{history_str}||{normalized_query}"
        
        # Hash for fixed-length key
        key_hash = hashlib.sha256(full_key.encode()).hexdigest()[:16]
        return key_hash
    
    def get(
        self,
        query: str,
        conversation_history: Optional[list] = None
    ) -> Optional[AgentResponse]:
        """
        Retrieve cached response if available.
        
        Args:
            query: User's question
            conversation_history: Previous questions in conversation
            
        Returns:
            Cached AgentResponse or None if cache miss
        """
        history = conversation_history or []
        key = self._make_key(query, history)
        
        cached = self.cache.get(key)
        if cached:
            self.hits += 1
            # Deserialize back to AgentResponse
            return self._deserialize_response(cached)
        else:
            self.misses += 1
            return None
    
    def set(
        self,
        query: str,
        response: AgentResponse,
        conversation_history: Optional[list] = None
    ):
        """
        Cache a response.
        
        Args:
            query: User's question
            response: Agent's response to cache
            conversation_history: Previous questions in conversation
        """
        history = conversation_history or []
        key = self._make_key(query, history)
        
        # Serialize response for storage
        serialized = self._serialize_response(response)
        self.cache[key] = serialized
    
    def _serialize_response(self, response: AgentResponse) -> str:
        """Serialize AgentResponse to JSON string."""
        # Convert to dict
        data = {
            "answer": response.answer,
            "sources": response.sources,
            "confidence": response.confidence,
            "status": response.status,
            "language": response.language,
            "steps": [
                {
                    "decision": step.decision.value if hasattr(step.decision, 'value') else step.decision,
                    "reason": step.reason,
                    "tool_calls": [
                        {
                            "tool_name": tc.tool_name,
                            "inputs": tc.inputs,
                            "outputs": tc.outputs,
                            "success": tc.success
                        } for tc in step.tool_calls
                    ]
                } for step in response.steps
            ],
            "retrieved_chunks": [asdict(chunk) for chunk in response.retrieved_chunks]
            ],
            "retrieved_chunks": [asdict(chunk) for chunk in (response.retrieved_chunks or [])]
    
    def _deserialize_response(self, serialized: str) -> AgentResponse:
        """Deserialize JSON string back to AgentResponse."""
        from src.agent.types import AgentDecision, AgentStep, ToolCallLog, SourceInfo
        from src.agent.types import AgentDecision, AgentStep, ToolCallLog
        
        data = json.loads(serialized)
        
        # Reconstruct AgentResponse
        return AgentResponse(
            answer=data["answer"],
            sources=data["sources"],
            confidence=data["confidence"],
            status=data["status"],
            steps=[
                AgentStep(
                    decision=AgentDecision(step_data["decision"]),
                    reason=step_data["reason"],
                    tool_calls=[ToolCallLog(**tc) for tc in step_data["tool_calls"]]
                ) for step_data in data["steps"]
            ],
            retrieved_chunks=[RetrievedChunk(**chunk) for chunk in data.get("retrieved_chunks", [])],
            language=data.get("language")
        )
    
    def clear(self):
        """Clear all cached entries."""
        self.cache.clear()
        self.hits = 0
        self.misses = 0
    
    def get_stats(self) -> dict:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0.0
        
        return {
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total,
            "hit_rate": hit_rate,
            "cache_size": len(self.cache),
            "max_size": self.cache.maxsize
        }
