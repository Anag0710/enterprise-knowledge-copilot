import logging
import os
import re
import time
from typing import Iterable, List, Optional

from openai import OpenAI
from openai import APIConnectionError, APIError, APITimeoutError, RateLimitError

from src.agent.tools import LLMClient


logger = logging.getLogger(__name__)


class OpenAIChatClient(LLMClient):
    """OpenAI-backed client with retry, backoff, and prompt redaction."""

    DEFAULT_REDACTION_PATTERNS = [
        re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE),
        re.compile(r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b"),  # SSN-like
        re.compile(r"\b\d{10,16}\b"),  # generic account numbers
    ]

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.1,
        max_retries: int = 4,
        backoff_factor: float = 2.0,
        redact_patterns: Optional[Iterable[re.Pattern]] = None,
        system_prompt: str = "You are the Enterprise Knowledge Copilot. Ground every answer in the provided context.",
        api_key: Optional[str] = None,
        organization: Optional[str] = None,
    ):
        key = api_key or os.getenv("OPENAI_API_KEY")
        if not key:
            raise ValueError("OPENAI_API_KEY is required to initialize OpenAIChatClient")

        self.client = OpenAI(api_key=key, organization=organization or os.getenv("OPENAI_ORG"))
        self.model = model
        self.temperature = temperature
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.system_prompt = system_prompt
        self.redaction_patterns: List[re.Pattern] = list(redact_patterns or self.DEFAULT_REDACTION_PATTERNS)

    def generate(self, prompt: str, **kwargs) -> str:
        sanitized_prompt = self._redact(prompt)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": sanitized_prompt},
            ],
            "temperature": kwargs.get("temperature", self.temperature),
        }

        if "max_tokens" in kwargs:
            payload["max_tokens"] = kwargs["max_tokens"]

        return self._execute_with_retry(payload)

    def _execute_with_retry(self, payload):
        for attempt in range(1, self.max_retries + 1):
            try:
                response = self.client.chat.completions.create(**payload)
                message = response.choices[0].message.content or ""
                return message.strip()
            except RateLimitError as exc:
                self._sleep(attempt, exc, "rate limit")
            except (APIConnectionError, APITimeoutError) as exc:
                self._sleep(attempt, exc, "transient network")
            except APIError as exc:
                status = getattr(exc, "status_code", None)
                if status and 500 <= status < 600:
                    self._sleep(attempt, exc, "server error")
                else:
                    raise
        raise RuntimeError("OpenAIChatClient exhausted retries")

    def _sleep(self, attempt: int, exc: Exception, reason: str):
        delay = self.backoff_factor * (2 ** (attempt - 1))
        logger.warning("OpenAIChatClient retrying | attempt=%d | reason=%s | delay=%.2fs", attempt, reason, delay)
        time.sleep(delay)

    def _redact(self, prompt: str) -> str:
        redacted = prompt
        for pattern in self.redaction_patterns:
            redacted = pattern.sub("[REDACTED]", redacted)
        return redacted
