"""Simple translation wrapper used when multilingual mode is enabled."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

try:
    from deep_translator import GoogleTranslator
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "deep-translator is required for multilingual support. Install with: pip install deep-translator"
    ) from exc


logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    text: str
    provider: str
    source_language: str
    target_language: str
    cached: bool = False


class Translator:
    """Stateless helper that wraps deep_translator providers with error handling."""

    def __init__(self, default_target: str = "en", provider: str = "google"):
        self.default_target = default_target
        self.provider = provider

    def translate(self, text: str, source_language: Optional[str], target_language: Optional[str]) -> TranslationResult:
        source = (source_language or self.default_target).lower()
        target = (target_language or self.default_target).lower()

        if not text or source == target:
            return TranslationResult(text=text, provider=self.provider, source_language=source, target_language=target)

        try:
            translated = GoogleTranslator(source=source, target=target).translate(text)
            return TranslationResult(
                text=translated,
                provider=self.provider,
                source_language=source,
                target_language=target
            )
        except Exception as exc:  # pragma: no cover - network failure fallback
            logger.warning("Translation failed (%s -> %s): %s", source, target, exc)
            return TranslationResult(
                text=text,
                provider=self.provider,
                source_language=source,
                target_language=target
            )

    def normalize_target(self, user_language: Optional[str]) -> str:
        return (user_language or self.default_target).split("-")[0].lower()
