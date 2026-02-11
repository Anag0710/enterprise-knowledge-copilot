import logging
import time
from typing import List, Optional

from src.agent.logger import AgentRunLogger
from src.agent.metrics import AgentMetrics
from src.agent.policy import AgentPolicy
from src.agent.tools import AnswerGenerationTool, ClarificationTool, RetrievalTool
from src.agent.types import AgentDecision, AgentResponse, AgentStep, ToolCallLog


logger = logging.getLogger(__name__)


class EnterpriseKnowledgeAgent:
    def __init__(
        self,
        retrieval_tool: RetrievalTool,
        answer_tool: AnswerGenerationTool,
        clarification_tool: ClarificationTool,
        policy: Optional[AgentPolicy] = None,
        retrieval_confidence_threshold: float = 0.35,
        run_logger: Optional[AgentRunLogger] = None,
        metrics: Optional[AgentMetrics] = None,
    ):
        self.retrieval_tool = retrieval_tool
        self.answer_tool = answer_tool
        self.clarification_tool = clarification_tool
        self.policy = policy or AgentPolicy()
        self.retrieval_confidence_threshold = retrieval_confidence_threshold
        self.run_logger = run_logger
        self.metrics = metrics

    def run(self, question: str, conversation_history: Optional[List[str]] = None) -> AgentResponse:
        start_time = time.time()
        conversation_history = conversation_history or []
        steps: List[AgentStep] = []

        if self.metrics:
            self.metrics.increment_active_requests()

        try:
            decision = self.policy.entrypoint_decision(question, conversation_history)
            logger.info("Agent starting decision=%s", decision.value)
            if self.metrics:
                self.metrics.record_decision(decision.value)

            if decision == AgentDecision.CLARIFY:
                clarification = self.clarification_tool.run(question)
                steps.append(
                    AgentStep(
                        decision=AgentDecision.CLARIFY,
                        reason=clarification.rationale,
                        tool_calls=[
                            ToolCallLog(
                                name="clarification_tool",
                                inputs={"question": question},
                                outputs={"prompt": clarification.prompt},
                                success=True
                            )
                        ]
                    )
                )
                response = AgentResponse(
                    answer=clarification.prompt,
                    sources=[],
                    confidence=0.0,
                    status="clarification_needed",
                    steps=steps
                )
                self._log_run(question, response)
                if self.metrics:
                    duration = time.time() - start_time
                    self.metrics.record_request("clarification_needed", duration)
                return response

            retrieval_result = self.retrieval_tool.run(question)
            if self.metrics:
                self.metrics.record_retrieval(
                    retrieval_result.confidence,
                    len(retrieval_result.chunks)
                )
            steps.append(
                AgentStep(
                    decision=AgentDecision.RETRIEVE,
                    reason="Initial retrieval for grounding",
                    tool_calls=[
                        ToolCallLog(
                            name="retrieval_tool",
                            inputs={"question": question},
                            outputs={
                                "chunks": len(retrieval_result.chunks),
                                "confidence": retrieval_result.confidence
                            },
                            success=True
                        )
                    ]
                )
            )

            if self.policy.should_refuse(retrieval_result.confidence, self.retrieval_confidence_threshold):
                refusal = self.policy.refusal_message()
                logger.warning(
                    "Agent refusing to answer | confidence=%.3f", retrieval_result.confidence
                )
                steps.append(
                    AgentStep(
                        decision=AgentDecision.REFUSE,
                        reason="Retrieval confidence below threshold",
                        tool_calls=[]
                    )
                )
                response = AgentResponse(
                    answer=refusal,
                    sources=[],
                    confidence=retrieval_result.confidence,
                    status="no_context",
                    steps=steps,
                    retrieved_chunks=retrieval_result.chunks
                )
                self._log_run(question, response)
                if self.metrics:
                    duration = time.time() - start_time
                    self.metrics.record_request("no_context", duration)
                return response

            answer_result = self.answer_tool.run(question, retrieval_result)
            steps.append(
                AgentStep(
                    decision=AgentDecision.ANSWER,
                    reason="Context sufficient, invoking answer generator",
                    tool_calls=[
                        ToolCallLog(
                            name="answer_generation_tool",
                            inputs={"question": question},
                            outputs={"confidence": answer_result.confidence},
                            success=True
                        )
                    ]
                )
            )

            logger.info("Agent finished with answer | confidence=%.3f", answer_result.confidence)
            response = AgentResponse(
                answer=answer_result.answer,
                sources=answer_result.citations,
                confidence=answer_result.confidence,
                status="answered",
                steps=steps,
                retrieved_chunks=retrieval_result.chunks
            )
            self._log_run(question, response)
            if self.metrics:
                duration = time.time() - start_time
                self.metrics.record_request("answered", duration)
            return response
        finally:
            if self.metrics:
                self.metrics.decrement_active_requests()

    def _log_run(self, question: str, response: AgentResponse):
        if not self.run_logger:
            return
        try:
            self.run_logger.log(question, response)
        except Exception as exc:  # pragma: no cover - logging must not break agent flow
            logger.exception("AgentRunLogger failed | reason=%s", exc)
