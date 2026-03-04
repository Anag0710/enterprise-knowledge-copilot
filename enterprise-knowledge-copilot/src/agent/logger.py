import json
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from src.agent.log_shipper import LogShipper

from src.agent.types import AgentResponse


logger = logging.getLogger(__name__)


class AgentRunLogger:
    """Persists agent runs as JSON lines with optional rotation + shipping."""

    def __init__(
        self,
        log_path: Path,
        *,
        max_bytes: int = 5_000_000,
        backup_count: int = 5,
        retention_days: int = 30,
        shipper: Optional[LogShipper] = None
    ):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.retention_window = timedelta(days=retention_days)
        self.shipper = shipper

    def log(self, question: str, response: AgentResponse):
        self._rotate_if_needed()
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

        self._ship(payload)

    @staticmethod
    def _serialize_step(step) -> Dict[str, Any]:
        """Convert AgentStep to JSON-serializable dict, handling enums."""
        step_dict = asdict(step)
        # Convert AgentDecision enum to its string value
        step_dict["decision"] = step.decision.value
        return step_dict

    def _rotate_if_needed(self) -> None:
        if self.max_bytes <= 0 or not self.log_path.exists():
            return

        if self.log_path.stat().st_size < self.max_bytes:
            return

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        rotated_name = f"{self.log_path.stem}_{timestamp}{self.log_path.suffix}"
        rotated_path = self.log_path.with_name(rotated_name)
        self.log_path.rename(rotated_path)
        self._cleanup_old_logs()

    def _cleanup_old_logs(self) -> None:
        cutoff = datetime.now(timezone.utc) - self.retention_window
        siblings = sorted(
            self.log_path.parent.glob(f"{self.log_path.stem}_*{self.log_path.suffix}")
        )

        for path in siblings:
            stat = path.stat()
            modified = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            if modified < cutoff:
                path.unlink(missing_ok=True)

        # Enforce backup count newest-first
        if len(siblings) > self.backup_count:
            for stale_path in siblings[:-self.backup_count]:
                stale_path.unlink(missing_ok=True)

    def _ship(self, payload: Dict[str, Any]) -> None:
        if not self.shipper:
            return
        try:
            self.shipper.enqueue(payload)
        except Exception as exc:  # pragma: no cover - ship failures shouldn't block logging
            logger.exception("Failed to enqueue payload for shipping: %s", exc)
