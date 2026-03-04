"""In-memory store for managing clarification loops across transports."""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple


@dataclass
class ClarificationSession:
    session_id: str
    question: str
    prompt: str
    conversation_history: List[str]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    language: Optional[str] = None
    experiment_assignment: Optional[Tuple[str, str]] = None


class ClarificationSessionManager:
    def __init__(self, ttl_seconds: int = 900):
        self.ttl = timedelta(seconds=ttl_seconds)
        self.sessions: Dict[str, ClarificationSession] = {}
        self._lock = threading.Lock()

    def create(
        self,
        question: str,
        prompt: str,
        conversation_history: List[str],
        language: Optional[str] = None,
        experiment_assignment: Optional[Tuple[str, str]] = None
    ) -> ClarificationSession:
        session = ClarificationSession(
            session_id=uuid.uuid4().hex,
            question=question,
            prompt=prompt,
            conversation_history=list(conversation_history),
            language=language,
            experiment_assignment=experiment_assignment
        )
        with self._lock:
            self.sessions[session.session_id] = session
            self._prune_unlocked()
        return session

    def resolve(self, session_id: str, clarification: str) -> ClarificationSession:
        with self._lock:
            session = self.sessions.pop(session_id, None)
        if not session:
            raise KeyError(f"Clarification session {session_id} not found or expired")
        session.conversation_history.extend([session.question, clarification])
        return session

    def peek(self, session_id: str) -> Optional[ClarificationSession]:
        with self._lock:
            session = self.sessions.get(session_id)
            if session and self._is_expired(session):
                self.sessions.pop(session_id, None)
                return None
            return session

    def _prune_unlocked(self) -> None:
        expired_ids = [sid for sid, sess in self.sessions.items() if self._is_expired(sess)]
        for sid in expired_ids:
            self.sessions.pop(sid, None)

    def _is_expired(self, session: ClarificationSession) -> bool:
        return datetime.now(timezone.utc) - session.created_at > self.ttl
