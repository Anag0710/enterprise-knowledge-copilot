"""Language detection utilities for multilingual support."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import List, Optional

try:
    from langdetect import DetectorFactory, LangDetectException, detect
except ImportError as exc:  # pragma: no cover - optional dependency guard
    raise ImportError(
        "langdetect is required for multilingual support. Install with: pip install langdetect"
    ) from exc


logger = logging.getLogger(__name__)
DetectorFactory.seed = 0  # Deterministic results for repeatability


class LanguageDetector:
    """Thin wrapper around langdetect with sane defaults and caching."""

    def __init__(self, fallback_language: str = "en"):
        self.fallback_language = fallback_language

    def detect(self, text: str) -> str:
        if not text:
            return self.fallback_language
        detected = self._detect_cached(text[:1000])  # truncate to keep runtime bounded
        return self.normalize(detected)

    def detect_batch(self, texts: List[str]) -> List[str]:
        return [self.detect(text) for text in texts]

    @staticmethod
    @lru_cache(maxsize=4096)
    def _detect_cached(sample: str) -> str:
        try:
            return detect(sample)
        except LangDetectException:
            logger.debug("Falling back to default language for sample of length %d", len(sample))
            return "en"

    def normalize(self, language_code: Optional[str]) -> str:
        """Normalize various detector outputs into ISO 639-1 codes."""
        if not language_code:
            return self.fallback_language
        return language_code.split("-")[0].lower()
