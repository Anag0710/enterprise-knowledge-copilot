import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Tuple

from src.agent.types import AgentResponse


logger = logging.getLogger(__name__)


@dataclass
class EvaluationCase:
    question: str
    expected_behavior: str = "answer"  # answer | clarify | refuse
    expected_sources: List[str] = field(default_factory=list)


@dataclass
class EvaluationMetrics:
    total_cases: int
    passed: int
    failed: int
    details: List[str] = field(default_factory=list)


class EvaluationSuite:
    """Lightweight harness to probe the agent for regressions."""

    def __init__(self, agent, dataset_path: Path):
        self.agent = agent
        self.dataset_path = Path(dataset_path)
        self.cases = self._load_cases()

    def _load_cases(self) -> List[EvaluationCase]:
        if not self.dataset_path.exists():
            logger.warning("Evaluation dataset not found at %s", self.dataset_path)
            return []

        with self.dataset_path.open("r", encoding="utf-8") as f:
            raw = json.load(f) or []

        cases = [
            EvaluationCase(
                question=item.get("question", ""),
                expected_behavior=item.get("expected_behavior", "answer"),
                expected_sources=item.get("expected_sources", []),
            )
            for item in raw
            if item.get("question")
        ]

        logger.info("Loaded %d evaluation cases", len(cases))
        return cases

    def run(self) -> EvaluationMetrics:
        if not self.cases:
            logger.warning("No evaluation cases available")
            return EvaluationMetrics(total_cases=0, passed=0, failed=0)

        passed = 0
        details: List[str] = []

        for case in self.cases:
            response = self.agent.run(case.question)
            case_passed, message = self._evaluate_case(case, response)
            if case_passed:
                passed += 1
            else:
                details.append(message)

        failed = len(self.cases) - passed
        return EvaluationMetrics(
            total_cases=len(self.cases),
            passed=passed,
            failed=failed,
            details=details,
        )

    def _evaluate_case(self, case: EvaluationCase, response: AgentResponse) -> Tuple[bool, str]:
        expected = case.expected_behavior

        behavior_match = self._behavior_matches(expected, response)
        if not behavior_match:
            return False, f"Behavior mismatch for question='{case.question}'"

        faithfulness_ok = self._test_faithfulness(response)
        if not faithfulness_ok:
            return False, f"Faithfulness failure for question='{case.question}'"

        retrieval_ok = self._test_retrieval(case, response)
        if not retrieval_ok:
            return False, f"Retrieval failure for question='{case.question}'"

        hallucination_ok = self._test_hallucination(expected, response)
        if not hallucination_ok:
            return False, f"Hallucination guard failure for question='{case.question}'"

        return True, ""

    @staticmethod
    def _behavior_matches(expected: str, response: AgentResponse) -> bool:
        if expected == "answer":
            return response.status == "answered"
        if expected == "clarify":
            return response.status == "clarification_needed"
        if expected == "refuse":
            return response.status == "no_context"
        return False

    @staticmethod
    def _test_faithfulness(response: AgentResponse) -> bool:
        if response.status != "answered":
            return True
        if not response.sources:
            return False
        if not response.retrieved_chunks:
            return False

        valid_pairs = {
            (chunk.metadata.get("source"), chunk.metadata.get("page"))
            for chunk in response.retrieved_chunks
        }
        for citation in response.sources:
            pair = (citation.get("source"), citation.get("page"))
            if pair not in valid_pairs:
                return False
        return True

    @staticmethod
    def _test_retrieval(case: EvaluationCase, response: AgentResponse) -> bool:
        if not case.expected_sources:
            return True
        if not response.sources:
            return False
        cited = {source.get("source") for source in response.sources}
        return any(expected in cited for expected in case.expected_sources)

    @staticmethod
    def _test_hallucination(expected: str, response: AgentResponse) -> bool:
        if expected == "refuse":
            return "I don't know" in response.answer
        if expected == "answer":
            return response.status == "answered"
        if expected == "clarify":
            return response.status == "clarification_needed"
        return True
