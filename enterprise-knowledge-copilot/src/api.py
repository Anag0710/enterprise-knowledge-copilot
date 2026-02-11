"""FastAPI REST API for the Enterprise Knowledge Copilot."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List, Optional
import asyncio
import json

from fastapi import FastAPI, HTTPException, status, Request, Depends
from fastapi.responses import PlainTextResponse, StreamingResponse, FileResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from sse_starlette.sse import EventSourceResponse

from src.main import initialize_agent
from src.agent.cache import ResponseCache
from src.agent.feedback import FeedbackLogger
from src.agent.suggested_questions import SuggestedQuestions
from src.agent.export import ConversationExporter
from src.auth import (
    get_auth_manager,
    is_auth_available,
    User,
    TokenData,
    AuthenticationError,
    AuthorizationError
)


logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Authentication
security = HTTPBearer(auto_error=False)
_auth_manager = None

# Global instances
_agent = None
_metrics_registry = None
_cache = None
_feedback_logger = None
_suggested_questions = None
_exporter = None


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
    cache_enabled: bool


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str = Field(..., description="'positive' or 'negative'")
    comment: Optional[str] = None
    confidence: float
    status: str
    sources: List[dict]


class ExportRequest(BaseModel):
    conversation: List[dict]
    format: str = Field(..., description="'json', 'text', or 'pdf'")
    filename: Optional[str] = None


class CacheStatsResponse(BaseModel):
    hits: int
    misses: int
    total_requests: int
    hit_rate: float
    cache_size: int
    max_size: int


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str
    roles: List[str]


class UserInfo(BaseModel):
    username: str
    email: str
    roles: List[str]
    disabled: bool


# Authentication dependencies
async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[User]:
    """Get current user from JWT token (optional - returns None if not authenticated)."""
    if not is_auth_available() or not _auth_manager:
        return None
    
    if not credentials:
        return None
    
    try:
        token_data = _auth_manager.verify_token(credentials.credentials)
        user = _auth_manager.get_user(token_data.username)
        return user
    except (AuthenticationError, Exception):
        return None


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> User:
    """Get current user from JWT token (required - raises 401 if not authenticated)."""
    if not is_auth_available() or not _auth_manager:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication not available. Install: pip install python-jose[cryptography] passlib[bcrypt]"
        )
    
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    try:
        token_data = _auth_manager.verify_token(credentials.credentials)
        user = _auth_manager.get_user(token_data.username)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )
        return user
    except AuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )


async def require_admin(user: User = Depends(get_current_user)) -> User:
    """Require user to have admin role."""
    if "admin" not in user.roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return user


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize agent and services on startup and clean up on shutdown."""
    global _agent, _metrics_registry, _cache, _feedback_logger, _suggested_questions, _exporter, _auth_manager
    logger.info("Initializing Enterprise Knowledge Copilot API...")
    
    from prometheus_client import CollectorRegistry
    _metrics_registry = CollectorRegistry()
    
    try:
        # Initialize authentication if available
        if is_auth_available():
            _auth_manager = get_auth_manager()
            logger.info("Authentication manager initialized (default users: admin/user/readonly)")
        else:
            logger.warning("Authentication not available - install: pip install python-jose[cryptography] passlib[bcrypt]")
        
        # Initialize agent with metrics
        _agent = initialize_agent(enable_metrics=True)
        
        # Patch metrics registry
        if _agent.metrics:
            _agent.metrics.registry = _metrics_registry
        
        # Initialize response cache
        _cache = ResponseCache(max_size=1000, ttl_seconds=3600)
        logger.info("Response cache initialized")
        
        # Initialize feedback logger
        feedback_path = Path("data/logs/feedback.jsonl")
        _feedback_logger = FeedbackLogger(feedback_path)
        logger.info("Feedback logger initialized")
        
        # Initialize suggested questions
        log_path = Path("data/logs/agent_runs.jsonl")
        _suggested_questions = SuggestedQuestions(log_path if log_path.exists() else None)
        logger.info("Suggested questions initialized")
        
        # Initialize conversation exporter
        _exporter = ConversationExporter()
        logger.info("Conversation exporter initialized")
        
        logger.info("Agent initialized successfully")
    except Exception as exc:
        logger.error("Failed to initialize agent: %s", exc)
        raise
    
    yield
    
    logger.info("Shutting down Enterprise Knowledge Copilot API")


app = FastAPI(
    title="Enterprise Knowledge Copilot API",
    description="Production RAG system with agentic decision-making and advanced features",
    version="2.0.0",
    lifespan=lifespan
)

#Add rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.get("/health", response_model=HealthResponse, tags=["System"])
@limiter.limit("60/minute")
async def health_check(request: Request):
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
    cache_enabled = _cache is not None
    
    return HealthResponse(
        status="healthy",
        vector_store_ready=vector_store_ready,
        llm_enabled=llm_enabled,
        cache_enabled=cache_enabled
    )


# === Authentication Endpoints ===

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
@limiter.limit("10/minute")
async def login(request: LoginRequest, http_request: Request):
    """
    Authenticate with username/password and get JWT access token.
    
    Default users:
    - admin/admin123 (roles: admin, user)
    - user/user123 (roles: user)
    - readonly/readonly123 (roles: readonly)
    """
    if not is_auth_available() or not _auth_manager:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Authentication not available. Install: pip install python-jose[cryptography] passlib[bcrypt]"
        )
    
    user = _auth_manager.authenticate_user(request.username, request.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token = _auth_manager.create_access_token(
        username=user.username,
        roles=user.roles
    )
    
    return TokenResponse(
        access_token=access_token,
        username=user.username,
        roles=user.roles
    )


@app.get("/auth/me", response_model=UserInfo, tags=["Authentication"])
@limiter.limit("30/minute")
async def get_current_user_info(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Get information about the currently authenticated user."""
    return UserInfo(
        username=current_user.username,
        email=current_user.email,
        roles=current_user.roles,
        disabled=current_user.disabled
    )


# === Agent Endpoints ===

@app.post("/ask", response_model=AgentResponseModel, tags=["Agent"])
@limiter.limit("30/minute")
async def ask_question(request: QuestionRequest, http_request: Request):
    """Submit a question to the agent and get an answer with sources."""
    if not _agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not initialized"
        )
    
    try:
        # Check cache first
        if _cache:
            cached_response = _cache.get(request.question, request.conversation_history or [])
            if cached_response:
                logger.info(f"Cache hit for question: {request.question[:50]}")
                sources = [
                    SourceInfo(
                        source=src.get("source", "unknown"),
                        page=src.get("page"),
                        chunk=src.get("chunk")
                    )
                    for src in cached_response.sources
                ]
                
                return AgentResponseModel(
                    answer=cached_response.answer,
                    sources=sources,
                    confidence=cached_response.confidence,
                    status=cached_response.status
                )
        
        # Process with agent
        response = _agent.run(
            question=request.question,
            conversation_history=request.conversation_history
        )
        
        # Cache the response
        if _cache:
            _cache.set(request.question, response, request.conversation_history or [])
        
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


@app.post("/ask/stream", tags=["Agent"])
@limiter.limit("20/minute")
async def ask_question_stream(request: QuestionRequest, http_request: Request):
    """Submit a question and get streaming response (Server-Sent Events)."""
    if not _agent:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent not initialized"
        )
    
    async def generate_stream():
        try:
            # Send initial event
            yield {"event": "start", "data": json.dumps({"status": "processing"})}
            
            # Process with agent (simulation of streaming - in production, integrate with LLM streaming)
            response = _agent.run(
                question=request.question,
                conversation_history=request.conversation_history
            )
            
            # Stream answer in chunks (simulate word-by-word)
            words = response.answer.split()
            for i, word in enumerate(words):
                await asyncio.sleep(0.05)  # Simulate streaming delay
                yield {
                    "event": "token",
                    "data": json.dumps({"word": word, "index": i})
                }
            
            # Send final metadata
            sources_data = [
                {
                    "source": src.get("source", "unknown"),
                    "page": src.get("page"),
                    "chunk": src.get("chunk")
                }
                for src in response.sources
            ]
            
            yield {
                "event": "complete",
                "data": json.dumps({
                    "confidence": response.confidence,
                    "status": response.status,
                    "sources": sources_data
                })
            }
        
        except Exception as exc:
            logger.exception("Error in streaming: %s", exc)
            yield {
                "event": "error",
                "data": json.dumps({"error": str(exc)})
            }
    
    return EventSourceResponse(generate_stream())


@app.post("/feedback", tags=["Feedback"])
@limiter.limit("100/minute")
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    """Submit user feedback on an answer (thumbs up/down)."""
    if not _feedback_logger:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feedback system not initialized"
        )
    
    try:
        _feedback_logger.log_feedback(
            question=feedback.question,
            answer=feedback.answer,
            rating=feedback.rating,
            confidence=feedback.confidence,
            status=feedback.status,
            sources=feedback.sources,
            comment=feedback.comment
        )
        
        return {"status": "success", "message": "Feedback recorded"}
    
    except Exception as exc:
        logger.exception("Error recording feedback: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record feedback: {str(exc)}"
        )


@app.get("/feedback/stats", tags=["Feedback"])
@limiter.limit("60/minute")
async def get_feedback_stats(request: Request):
    """Get feedback statistics."""
    if not _feedback_logger:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Feedback system not initialized"
        )
    
    try:
        stats = _feedback_logger.get_statistics()
        return stats
    except Exception as exc:
        logger.exception("Error retrieving feedback stats: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve feedback stats: {str(exc)}"
        )


@app.get("/suggestions", tags=["Suggestions"])
@limiter.limit("60/minute")
async def get_suggested_questions(request: Request, limit: int = 5):
    """Get suggested questions for the user."""
    if not _suggested_questions:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Suggestions system not initialized"
        )
    
    try:
        suggestions = _suggested_questions.get_smart_suggestions(limit=limit)
        return {"suggestions": suggestions}
    except Exception as exc:
        logger.exception("Error getting suggestions: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get suggestions: {str(exc)}"
        )


@app.get("/suggestions/categories", tags=["Suggestions"])
@limiter.limit("60/minute")
async def get_suggestion_categories(request: Request):
    """Get all suggestion categories with their questions."""
    if not _suggested_questions:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Suggestions system not initialized"
        )
    
    try:
        categories = _suggested_questions.get_all_categories()
        return {"categories": categories}
    except Exception as exc:
        logger.exception("Error getting categories: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get categories: {str(exc)}"
        )


@app.post("/export", tags=["Export"])
@limiter.limit("10/minute")
async def export_conversation(export_req: ExportRequest, request: Request):
    """Export conversation to JSON, text, or PDF format."""
    if not _exporter:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Export system not initialized"
        )
    
    try:
        # Generate filename
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = export_req.filename or f"conversation_{timestamp}"
        
        export_dir = Path("data/exports")
        export_dir.mkdir(parents=True, exist_ok=True)
        
        if export_req.format == "json":
            output_path = export_dir / f"{filename}.json"
            _exporter.export_to_json(export_req.conversation, output_path)
        
        elif export_req.format == "text":
            output_path = export_dir / f"{filename}.txt"
            _exporter.export_to_text(export_req.conversation, output_path)
        
        elif export_req.format == "pdf":
            output_path = export_dir / f"{filename}.pdf"
            _exporter.export_to_pdf(export_req.conversation, output_path)
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported format: {export_req.format}"
            )
        
        # Return file for download
        return FileResponse(
            path=output_path,
            filename=output_path.name,
            media_type='application/octet-stream'
        )
    
    except Exception as exc:
        logger.exception("Error exporting conversation: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to export conversation: {str(exc)}"
        )


@app.get("/cache/stats", response_model=CacheStatsResponse, tags=["Cache"])
@limiter.limit("60/minute")
async def get_cache_stats(request: Request):
    """Get cache statistics."""
    if not _cache:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache not enabled"
        )
    
    try:
        stats = _cache.get_stats()
        return CacheStatsResponse(**stats)
    except Exception as exc:
        logger.exception("Error retrieving cache stats: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve cache stats: {str(exc)}"
        )


@app.delete("/cache", tags=["Cache"])
@limiter.limit("10/minute")
async def clear_cache(request: Request):
    """Clear the response cache."""
    if not _cache:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Cache not enabled"
        )
    
    try:
        _cache.clear()
        return {"status": "success", "message": "Cache cleared"}
    except Exception as exc:
        logger.exception("Error clearing cache: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to clear cache: {str(exc)}"
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
    """API root endpoint with available endpoints."""
    return {
        "name": "Enterprise Knowledge Copilot API",
        "version": "2.0.0",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "ask": "/ask",
            "ask_stream": "/ask/stream",
            "feedback": "/feedback",
            "feedback_stats": "/feedback/stats",
            "suggestions": "/suggestions",
            "suggestions_categories": "/suggestions/categories",
            "export": "/export",
            "cache_stats": "/cache/stats",
            "clear_cache": "/cache",
            "metrics": "/metrics"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
