import logging
import time
from typing import List, Optional

from src.agent.logger import AgentRunLogger
from src.agent.metrics import AgentMetrics
from src.agent.policy import AgentPolicy
from src.agent.tools import AnswerGenerationTool, ClarificationTool, RetrievalTool
from src.agent.types import AgentDecision, AgentResponse, AgentStep, ToolCallLog
from src.agent.specialized_tools import MultiToolRouter


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
        enable_specialized_tools: bool = True,
        language_detector=None,
        translator=None,
        default_language: str = "en",
    ):
        self.retrieval_tool = retrieval_tool
        self.answer_tool = answer_tool
        self.clarification_tool = clarification_tool
        self.policy = policy or AgentPolicy()
        self.retrieval_confidence_threshold = retrieval_confidence_threshold
        self.run_logger = run_logger
        self.metrics = metrics
        self.enable_specialized_tools = enable_specialized_tools
        self.language_detector = language_detector
        self.translator = translator
        self.default_language = default_language
        
        # Initialize multi-tool router
        if enable_specialized_tools:
            llm_client = getattr(answer_tool, 'llm_client', None)
            self.router = MultiToolRouter(
                retrieval_tool=retrieval_tool,
                answer_tool=answer_tool,
                llm_client=llm_client
            )
        else:
            self.router = None

    def run(self, question: str, conversation_history: Optional[List[str]] = None) -> AgentResponse:
        start_time = time.time()
        conversation_history = conversation_history or []
        steps: List[AgentStep] = []
        working_question = question
        working_history = list(conversation_history)
        user_language = None

        if self.language_detector:
            detected = self._detect_language(question)
            if detected:
                user_language = detected
            if (
                self.translator
                and user_language
                and user_language != self.default_language
            ):
                translated = self.translator.translate(
                    question,
                    source_language=user_language,
                    target_language=self.default_language
                )
                working_question = translated.text
                working_history = [
                    self.translator.translate(
                        turn,
                        source_language=self._detect_language(turn) or user_language,
                        target_language=self.default_language
                    ).text if turn else turn
                    for turn in working_history
                ]
                if working_question != question:
                    steps.append(
                        AgentStep(
                            decision=AgentDecision.TRANSFORM,
                            reason="Translated question to default language",
                            tool_calls=[
                                ToolCallLog(
                                    name="translation_service",
                                    inputs={
                                        "source_language": user_language,
                                        "target_language": self.default_language
                                    },
                                    outputs={"characters": len(question)},
                                    success=True
                                )
                            ]
                        )
                    )

        if self.metrics:
            self.metrics.increment_active_requests()

        try:
            decision = self.policy.entrypoint_decision(working_question, working_history)
            logger.info("Agent starting decision=%s", decision.value)
            if self.metrics:
                self.metrics.record_decision(decision.value)

            if decision == AgentDecision.CLARIFY:
                clarification = self.clarification_tool.run(working_question)
                prompt_text = clarification.prompt
                if user_language and user_language != self.default_language:
                    prompt_text = self._maybe_translate_output(prompt_text, user_language)
                steps.append(
                    AgentStep(
                        decision=AgentDecision.CLARIFY,
                        reason=clarification.rationale,
                        tool_calls=[
                            ToolCallLog(
                                name="clarification_tool",
                                inputs={"question": working_question},
                                outputs={"prompt": clarification.prompt},
                                success=True
                            )
                        ]
                    )
                )
                response = AgentResponse(
                    answer=prompt_text,
                    sources=[],
                    confidence=0.0,
                    status="clarification_needed",
                    steps=steps,
                    language=user_language or self.default_language
                )
                self._log_run(question, response)
                if self.metrics:
                    duration = time.time() - start_time
                    self.metrics.record_request("clarification_needed", duration)
                return response

            # Check if specialized tool should handle this
            if self.router:
                tool_name, tool = self.router.route(working_question)
                
                if tool_name == "calculator":
                    calc_result = tool.run(working_question)
                    steps.append(
                        AgentStep(
                            decision=AgentDecision.ANSWER,
                            reason="Calculator tool selected",
                            tool_calls=[
                                ToolCallLog(
                                    name="calculator_tool",
                                    inputs={"expression": calc_result.expression},
                                    outputs={"result": calc_result.result} if calc_result.success else {"error": calc_result.error},
                                    success=calc_result.success
                                )
                            ]
                        )
                    )
                    if calc_result.success:
                        answer = f"The result is: **{calc_result.result}**\n\nCalculation: `{calc_result.expression} = {calc_result.result}`"
                    else:
                        answer = f"I couldn't perform that calculation: {calc_result.error}"
                    answer = self._maybe_translate_output(answer, user_language)
                    
                    response = AgentResponse(
                        answer=answer,
                        sources=[],
                        confidence=1.0 if calc_result.success else 0.0,
                        status="answered" if calc_result.success else "error",
                        steps=steps,
                        language=user_language or self.default_language
                    )
                    self._log_run(question, response)
                    if self.metrics:
                        duration = time.time() - start_time
                        self.metrics.record_request("answered", duration)
                    return response
                
                elif tool_name == "comparison":
                    items = tool.extract_items(working_question)
                    if items:
                        comp_result = tool.run(working_question, items)
                        steps.append(
                            AgentStep(
                                decision=AgentDecision.ANSWER,
                                reason="Comparison tool selected",
                                tool_calls=[
                                    ToolCallLog(
                                        name="comparison_tool",
                                        inputs={"items": items},
                                        outputs={"success": comp_result.success},
                                        success=comp_result.success
                                    )
                                ]
                            )
                        )
                        translated_answer = self._maybe_translate_output(comp_result.comparison, user_language)
                        response = AgentResponse(
                            answer=translated_answer,
                            sources=list(comp_result.retrieved_info.keys()),
                            confidence=0.8 if comp_result.success else 0.0,
                            status="answered" if comp_result.success else "error",
                            steps=steps,
                            language=user_language or self.default_language
                        )
                        self._log_run(question, response)
                        if self.metrics:
                            duration = time.time() - start_time
                            self.metrics.record_request("answered", duration)
                        return response
                
                elif tool_name == "summarization":
                    # Extract topic from question
                    topic = working_question.replace("summarize", "").replace("summary of", "").replace("overview of", "").strip()
                    if not topic:
                        topic = working_question
                    
                    summ_result = tool.run(working_question, topic)
                    steps.append(
                        AgentStep(
                            decision=AgentDecision.ANSWER,
                            reason="Summarization tool selected",
                            tool_calls=[
                                ToolCallLog(
                                    name="summarization_tool",
                                    inputs={"topic": topic},
                                    outputs={"source_count": summ_result.source_count},
                                    success=summ_result.success
                                )
                            ]
                        )
                    )
                    translated_summary = self._maybe_translate_output(summ_result.summary, user_language)
                    response = AgentResponse(
                        answer=translated_summary,
                        sources=[f"{summ_result.source_count} documents"],
                        confidence=summ_result.confidence,
                        status="answered" if summ_result.success else "error",
                        steps=steps,
                        language=user_language or self.default_language
                    )
                    self._log_run(question, response)
                    if self.metrics:
                        duration = time.time() - start_time
                        self.metrics.record_request("answered", duration)
                    return response

            # Standard retrieval + answer flow
            retrieval_result = self.retrieval_tool.run(working_question)
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
                            inputs={"question": working_question},
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
                answer_text = self._maybe_translate_output(refusal, user_language)
                response = AgentResponse(
                    answer=answer_text,
                    sources=[],
                    confidence=retrieval_result.confidence,
                    status="no_context",
                    steps=steps,
                    retrieved_chunks=retrieval_result.chunks,
                    language=user_language or self.default_language
                )
                self._log_run(question, response)
                if self.metrics:
                    duration = time.time() - start_time
                    self.metrics.record_request("no_context", duration)
                return response

            answer_result = self.answer_tool.run(working_question, retrieval_result)
            steps.append(
                AgentStep(
                    decision=AgentDecision.ANSWER,
                    reason="Context sufficient, invoking answer generator",
                    tool_calls=[
                        ToolCallLog(
                            name="answer_generation_tool",
                            inputs={"question": working_question},
                            outputs={"confidence": answer_result.confidence},
                            success=True
                        )
                    ]
                )
            )

            logger.info("Agent finished with answer | confidence=%.3f", answer_result.confidence)
            final_answer = self._maybe_translate_output(answer_result.answer, user_language)
            response = AgentResponse(
                answer=final_answer,
                sources=answer_result.citations,
                confidence=answer_result.confidence,
                status="answered",
                steps=steps,
                retrieved_chunks=retrieval_result.chunks,
                language=user_language or self.default_language
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

    def _detect_language(self, text: Optional[str]) -> Optional[str]:
        if not text or not self.language_detector:
            return None
        return self.language_detector.normalize(self.language_detector.detect(text))

    def _maybe_translate_output(self, text: str, user_language: Optional[str]) -> str:
        if not text or not self.translator or not user_language:
            return text
        if user_language == self.default_language:
            return text
        result = self.translator.translate(
            text,
            source_language=self.default_language,
            target_language=user_language
        )
        return result.text
