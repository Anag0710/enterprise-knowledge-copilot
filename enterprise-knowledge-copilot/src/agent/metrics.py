"""Prometheus metrics for agent observability and monitoring."""

import logging
from typing import Optional

from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry


logger = logging.getLogger(__name__)


class AgentMetrics:
    """Centralized metrics for agent performance tracking."""

    def __init__(self, registry: Optional[CollectorRegistry] = None):
        self.registry = registry or CollectorRegistry()

        # Request metrics
        self.requests_total = Counter(
            "agent_requests_total",
            "Total number of agent requests",
            ["status"],
            registry=self.registry
        )

        self.request_duration = Histogram(
            "agent_request_duration_seconds",
            "Time spent processing requests",
            ["status"],
            registry=self.registry
        )

        # Retrieval metrics
        self.retrieval_confidence = Histogram(
            "agent_retrieval_confidence",
            "Distribution of retrieval confidence scores",
            registry=self.registry
        )

        self.chunks_retrieved = Histogram(
            "agent_chunks_retrieved",
            "Number of chunks retrieved per query",
            registry=self.registry
        )

        # Decision metrics
        self.decisions_total = Counter(
            "agent_decisions_total",
            "Total agent decisions by type",
            ["decision"],
            registry=self.registry
        )

        # LLM metrics
        self.llm_calls_total = Counter(
            "agent_llm_calls_total",
            "Total LLM API calls",
            ["success"],
            registry=self.registry
        )

        self.llm_errors = Counter(
            "agent_llm_errors_total",
            "Total LLM errors",
            ["error_type"],
            registry=self.registry
        )

        # Cache metrics
        self.cache_hits = Counter(
            "vector_cache_hits_total",
            "Vector cache hit count",
            registry=self.registry
        )

        self.cache_misses = Counter(
            "vector_cache_misses_total",
            "Vector cache miss count",
            registry=self.registry
        )

        self.cache_rebuild_duration = Histogram(
            "vector_cache_rebuild_duration_seconds",
            "Time spent rebuilding vector cache",
            registry=self.registry
        )

        # Current state gauges
        self.active_requests = Gauge(
            "agent_active_requests",
            "Number of requests currently being processed",
            registry=self.registry
        )

        self.vector_store_chunks = Gauge(
            "vector_store_chunks_total",
            "Total chunks in vector store",
            registry=self.registry
        )

    def record_request(self, status: str, duration: float):
        """Record a completed request."""
        self.requests_total.labels(status=status).inc()
        self.request_duration.labels(status=status).observe(duration)

    def record_retrieval(self, confidence: float, num_chunks: int):
        """Record retrieval metrics."""
        self.retrieval_confidence.observe(confidence)
        self.chunks_retrieved.observe(num_chunks)

    def record_decision(self, decision: str):
        """Record agent decision."""
        self.decisions_total.labels(decision=decision).inc()

    def record_llm_call(self, success: bool, error_type: Optional[str] = None):
        """Record LLM call outcome."""
        self.llm_calls_total.labels(success=str(success).lower()).inc()
        if not success and error_type:
            self.llm_errors.labels(error_type=error_type).inc()

    def record_cache_hit(self):
        """Record vector cache hit."""
        self.cache_hits.inc()

    def record_cache_miss(self, rebuild_duration: float):
        """Record vector cache miss and rebuild time."""
        self.cache_misses.inc()
        self.cache_rebuild_duration.observe(rebuild_duration)

    def set_vector_store_size(self, num_chunks: int):
        """Update vector store chunk count."""
        self.vector_store_chunks.set(num_chunks)

    def increment_active_requests(self):
        """Increment active request counter."""
        self.active_requests.inc()

    def decrement_active_requests(self):
        """Decrement active request counter."""
        self.active_requests.dec()
