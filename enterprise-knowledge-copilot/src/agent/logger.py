import json
from dataclasses import asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict

from src.agent.types import AgentResponse


class AgentRunLogger:
    """Persists agent runs as JSON lines for observability."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, question: str, response: AgentResponse):
        payload: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "question": question,
            "status": response.status,
            "confidence": response.confidence,
            "answer_preview": response.answer[:280],
            "sources": response.sources,
            "steps": [self._serialize_step(step) for step in response.steps],
        }

        if response.retrieved_chunks:
            payload["retrieved_chunks"] = [asdict(chunk) for chunk in response.retrieved_chunks]

        with self.log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")

    @staticmethod
    def _serialize_step(step) -> Dict[str, Any]:
        """Convert AgentStep to JSON-serializable dict, handling enums."""
        step_dict = asdict(step)
        # Convert AgentDecision enum to its string value
        step_dict["decision"] = step.decision.value
        return step_dict
