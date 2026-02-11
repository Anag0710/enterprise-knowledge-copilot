"""
Enhanced PII (Personally Identifiable Information) detection using NER.
"""
import re
import logging
from typing import List, Optional, Set
from dataclasses import dataclass

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False


logger = logging.getLogger(__name__)


@dataclass
class PIIEntity:
    """Detected PII entity."""
    text: str
    label: str  # PERSON, ORG, GPE, DATE, MONEY, EMAIL, PHONE, etc.
    start: int
    end: int
    confidence: float = 1.0


class PIIDetector:
    """
    Detect and redact Personally Identifiable Information (PII).
    
    Uses:
    - spaCy NER for entity detection (PERSON, ORG, GPE, DATE, etc.)
    - Regex patterns for emails, phones, SSNs, credit cards
    - Configurable redaction policies
    
    Features:
    - Multi-entity type detection
    - Confidence scoring
    - Whitelist support (approved names/orgs)
    - Multiple redaction modes
    """
    
    # Regex patterns for common PII
    EMAIL_PATTERN = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    PHONE_PATTERN = r'\b(?:\+?1[-.]?)?\(?([0-9]{3})\)?[-.]?([0-9]{3})[-.]?([0-9]{4})\b'
    SSN_PATTERN = r'\b\d{3}-\d{2}-\d{4}\b'
    CREDIT_CARD_PATTERN = r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b'
    IP_ADDRESS_PATTERN = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
    
    def __init__(
        self,
        model_name: str = "en_core_web_sm",
        entity_types: Optional[Set[str]] = None,
        whitelist: Optional[Set[str]] = None
    ):
        """
        Initialize PII detector.
        
        Args:
            model_name: spaCy model name (default: en_core_web_sm)
            entity_types: Set of entity types to detect (default: all)
            whitelist: Set of approved names/terms to not redact
        """
        self.model_name = model_name
        self.entity_types = entity_types or {
            'PERSON', 'ORG', 'GPE', 'DATE', 'MONEY', 'CARDINAL',
            'TIME', 'PERCENT', 'QUANTITY'
        }
        self.whitelist = whitelist or set()
        
        # Initialize spaCy
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load(model_name)
                self.use_spacy = True
                logger.info(f"spaCy model '{model_name}' loaded successfully")
            except OSError:
                logger.warning(
                    f"spaCy model '{model_name}' not found. "
                    "Install with: python -m spacy download en_core_web_sm"
                )
                self.nlp = None
                self.use_spacy = False
        else:
            logger.warning(
                "spaCy not available. Install with: pip install spacy && python -m spacy download en_core_web_sm"
            )
            self.nlp = None
            self.use_spacy = False
    
    def detect_entities(self, text: str) -> List[PIIEntity]:
        """
        Detect PII entities in text.
        
        Args:
            text: Input text
            
        Returns:
            List of PIIEntity objects
        """
        entities = []
        
        # Detect with spaCy NER
        if self.use_spacy and self.nlp:
            doc = self.nlp(text)
            for ent in doc.ents:
                if ent.label_ in self.entity_types:
                    # Skip whitelisted entities
                    if ent.text.lower() in self.whitelist:
                        continue
                    
                    entities.append(PIIEntity(
                        text=ent.text,
                        label=ent.label_,
                        start=ent.start_char,
                        end=ent.end_char
                    ))
        
        # Detect with regex patterns
        patterns = {
            'EMAIL': self.EMAIL_PATTERN,
            'PHONE': self.PHONE_PATTERN,
            'SSN': self.SSN_PATTERN,
            'CREDIT_CARD': self.CREDIT_CARD_PATTERN,
            'IP_ADDRESS': self.IP_ADDRESS_PATTERN
        }
        
        for label, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                if match.group().lower() not in self.whitelist:
                    entities.append(PIIEntity(
                        text=match.group(),
                        label=label,
                        start=match.start(),
                        end=match.end()
                    ))
        
        # Sort by start position and remove overlaps
        entities.sort(key=lambda e: e.start)
        entities = self._remove_overlaps(entities)
        
        return entities
    
    def _remove_overlaps(self, entities: List[PIIEntity]) -> List[PIIEntity]:
        """Remove overlapping entities (keep longest)."""
        if not entities:
            return []
        
        result = [entities[0]]
        for entity in entities[1:]:
            prev = result[-1]
            if entity.start >= prev.end:
                # No overlap
                result.append(entity)
            elif entity.end > prev.end:
                # Overlaps but longer - replace
                result[-1] = entity
        
        return result
    
    def redact(
        self,
        text: str,
        mode: str = "mask",
        mask_char: str = "*"
    ) -> tuple[str, List[PIIEntity]]:
        """
        Redact PII from text.
        
        Args:
            text: Input text
            mode: Redaction mode:
                - "mask": Replace with mask_char (e.g., *** PERSON ***)
                - "label": Replace with label (e.g., [PERSON])
                - "remove": Remove completely
                - "hash": Replace with hash
            mask_char: Character for masking (default: *)
            
        Returns:
            Tuple of (redacted_text, detected_entities)
        """
        entities = self.detect_entities(text)
        
        if not entities:
            return text, []
        
        # Build redacted text from end to start (preserves positions)
        result = text
        for entity in reversed(entities):
            replacement = self._get_replacement(entity, mode, mask_char)
            result = result[:entity.start] + replacement + result[entity.end:]
        
        return result, entities
    
    def _get_replacement(
        self,
        entity: PIIEntity,
        mode: str,
        mask_char: str
    ) -> str:
        """Get replacement text for entity."""
        if mode == "mask":
            return f"{mask_char * 3} {entity.label} {mask_char * 3}"
        elif mode == "label":
            return f"[{entity.label}]"
        elif mode == "remove":
            return ""
        elif mode == "hash":
            import hashlib
            hashed = hashlib.sha256(entity.text.encode()).hexdigest()[:8]
            return f"[{entity.label}:{hashed}]"
        else:
            return f"[{entity.label}]"
    
    def has_pii(self, text: str) -> bool:
        """Check if text contains PII."""
        return len(self.detect_entities(text)) > 0
    
    def get_statistics(self, text: str) -> dict:
        """Get PII statistics for text."""
        entities = self.detect_entities(text)
        
        by_type = {}
        for entity in entities:
            by_type[entity.label] = by_type.get(entity.label, 0) + 1
        
        return {
            "total_entities": len(entities),
            "by_type": by_type,
            "has_pii": len(entities) > 0,
            "unique_values": len(set(e.text for e in entities))
        }


# Global instance
_pii_detector: Optional[PIIDetector] = None


def get_pii_detector(
    entity_types: Optional[Set[str]] = None,
    whitelist: Optional[Set[str]] = None
) -> PIIDetector:
    """Get or create global PII detector instance."""
    global _pii_detector
    if _pii_detector is None:
        _pii_detector = PIIDetector(
            entity_types=entity_types,
            whitelist=whitelist
        )
    return _pii_detector


def is_pii_detection_available() -> bool:
    """Check if spaCy PII detection is available."""
    return SPACY_AVAILABLE
