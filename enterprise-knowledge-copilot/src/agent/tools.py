import logging
from dataclasses import dataclass
from typing import Optional, Protocol

from src.agent.types import AnswerResult
from src.retrieval.engine import RetrievalEngine
from src.retrieval.types import RetrievalResult


logger = logging.getLogger(__name__)


class LLMClient(Protocol):
    """Minimal protocol for pluggable LLM providers."""

    def generate(self, prompt: str, **kwargs) -> str:  # pragma: no cover - interface
        ...


@dataclass
class ClarificationPrompt:
    prompt: str
    rationale: str


class RetrievalTool:
    def __init__(self, engine: RetrievalEngine):
        self.engine = engine

    def run(self, query: str) -> RetrievalResult:
        logger.info("RetrievalTool triggered | query=%s", query)
        return self.engine.retrieve(query)


class AnswerGenerationTool:
    def __init__(self, llm_client: Optional[LLMClient] = None):
        self.llm_client = llm_client

    def run(self, question: str, retrieval_result: RetrievalResult) -> AnswerResult:
        if not retrieval_result.chunks:
            raise ValueError("Cannot craft an answer without retrieved context")

        prompt = self._build_prompt(question, retrieval_result.chunks)
        logger.debug("AnswerGenerationTool prompt length=%d", len(prompt))

        if self.llm_client:
            answer_text = self.llm_client.generate(prompt)
        else:
            answer_text = self._fallback_answer(question, retrieval_result)

        citations = retrieval_result.top_sources()
        confidence = min(1.0, retrieval_result.confidence + 0.15)
        return AnswerResult(answer=answer_text, citations=citations, confidence=confidence)

    @staticmethod
    def _build_prompt(question: str, chunks) -> str:
        context_lines = []
        for idx, chunk in enumerate(chunks, start=1):
            source = chunk.metadata.get("source", "unknown")
            page = chunk.metadata.get("page", "?")
            context_lines.append(f"[{idx}] ({source} p{page}) {chunk.text}")

        instructions = (
            "You are the Enterprise Knowledge Copilot. Answer using ONLY the provided context. "
            "Cite sources in-line using [source|page] format. If the answer is not in the context, say 'I don't know.'"
        )

        return (
            f"{instructions}\n\n"
            f"Question: {question}\n\n"
            f"Context:\n" + "\n".join(context_lines)
        )

    @staticmethod
    def _fallback_answer(question: str, retrieval_result: RetrievalResult) -> str:
        """Deterministic response when no LLM client is configured."""
        summaries = []
        for chunk in retrieval_result.chunks[:2]:
            source = chunk.metadata.get("source", "source")
            page = chunk.metadata.get("page", "?")
            summaries.append(f"[{source}|p{page}] {chunk.text[:200]}...")

        joined = " ".join(summaries)
        return (
            "Contextual summary (LLM disabled): "
            f"Based on available evidence, {joined}"
        )


class ClarificationTool:
    def run(self, question: str) -> ClarificationPrompt:
        prompt = (
            "I need a bit more detail to give a grounded answer. "
            "Can you clarify what aspect of that topic you care about?"
        )
        rationale = (
            "Question either too short or relies on pronouns without conversation history."
        )
        return ClarificationPrompt(prompt=prompt, rationale=rationale)
