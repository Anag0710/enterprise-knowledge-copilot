from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from src.retrieval.types import RetrievedChunk


class AgentDecision(Enum):
    RETRIEVE = "retrieve"
    CLARIFY = "clarify"
    ANSWER = "answer"
    REFUSE = "refuse"


@dataclass
class ToolCallLog:
    name: str
    inputs: Dict[str, Any]
    outputs: Dict[str, Any]
    success: bool


@dataclass
class AgentStep:
    decision: AgentDecision
    reason: str
    tool_calls: List[ToolCallLog] = field(default_factory=list)


@dataclass
class AnswerResult:
    answer: str
    citations: List[Dict[str, Any]]
    confidence: float


@dataclass
class AgentResponse:
    answer: str
    sources: List[Dict[str, Any]]
    confidence: float
    status: str
    steps: List[AgentStep] = field(default_factory=list)
    retrieved_chunks: Optional[List[RetrievedChunk]] = None

    def requires_clarification(self) -> bool:
        return self.status == "clarification_needed"
