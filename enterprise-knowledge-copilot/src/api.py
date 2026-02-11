"""FastAPI REST API for the Enterprise Knowledge Copilot."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, HTTPException, status
from fastapi.responses import PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from pydantic import BaseModel, Field

from src.main import initialize_agent


logger = logging.getLogger(__name__)


# Global agent instance
_agent = None
_metrics_registry = None


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, description="The user's question")
    conversation_history: Optional[List[str]] = Field(default=None, description="Optional conversation history")


class SourceInfo(BaseModel):
    source: str
    page: Optional[int] = None
    chunk: Optional[int] = None


class AgentResponseModel(BaseModel):
    answer: str
    sources: List[SourceInfo]
    confidence: float
    status: str


class HealthResponse(BaseModel):
    status: str
    vector_store_ready: bool
    llm_enabled: bool


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent on startup and clean up on shutdown."""
    global _agent, _metrics_registry
    logger.info("Initializing Enterprise Knowledge Copilot API...")
    
    from prometheus_client import CollectorRegistry
    _metrics_registry = CollectorRegistry()
    
    try:
        _agent = initialize_agent(enable_metrics=True)
        # Patch metrics registry
        if _agent.metrics:
            _agent.metrics.registry = _metrics_registry
        logger.info("Agent initialized successfully")
    except Exception as exc:
        logger.error("Failed to initialize agent: %s", exc)
        raise
    
    yield
    
    logger.info("Shutting down Enterprise Knowledge Copilot API")


app = FastAPI(
    title="Enterprise Knowledge Copilot API",
    description="Production RAG system with agentic decision-making",
    version="1.0.0",
    lifespan=lifespan
)


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Check system health and readiness."""
    if not _agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not initialized"
        )
    
    vector_store_ready = (
        _agent.retrieval_tool 
        and _agent.retrieval_tool.engine 
        and _agent.retrieval_tool.engine.store.is_ready()
    )
    
    llm_enabled = _agent.answer_tool.llm_client is not None
    
    return HealthResponse(
        status="healthy",
        vector_store_ready=vector_store_ready,
        llm_enabled=llm_enabled
    )


@app.post("/ask", response_model=AgentResponseModel, tags=["Agent"])
async def ask_question(request: QuestionRequest):
    """Submit a question to the agent and get an answer with sources."""
    if not _agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not initialized"
        )
    
    try:
        response = _agent.run(
            question=request.question,
            conversation_history=request.conversation_history
        )
        
        sources = [
            SourceInfo(
                source=src.get("source", "unknown"),
                page=src.get("page"),
                chunk=src.get("chunk")
            )
            for src in response.sources
        ]
        
        return AgentResponseModel(
            answer=response.answer,
            sources=sources,
            confidence=response.confidence,
            status=response.status
        )
    except Exception as exc:
        logger.exception("Error processing question: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process question: {str(exc)}"
        )


@app.get("/metrics", response_class=PlainTextResponse, tags=["System"])
async def metrics():
    """Expose Prometheus metrics."""
    if not _metrics_registry:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metrics not enabled"
        )
    
    return generate_latest(_metrics_registry).decode("utf-8")


@app.get("/", tags=["System"])
async def root():
    """API root endpoint."""
    return {
        "name": "Enterprise Knowledge Copilot API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
