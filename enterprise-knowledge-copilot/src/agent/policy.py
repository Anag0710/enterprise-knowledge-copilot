import re
from typing import List, Optional

from src.agent.types import AgentDecision


def _normalize(text: str) -> str:
    return text.lower().strip()


class AgentPolicy:
    """Rule-based guardrails for the agent's high-level choices."""

    PRONOUN_PATTERN = re.compile(r"\b(it|they|them|this|that|those|these)\b", re.IGNORECASE)
    AMBIGUOUS_KEYWORDS = {"policy", "process", "procedure", "document", "info", "details"}
    VAGUE_QUESTIONS = [
        "tell me more",
        "explain",
        "what about",
        "how about",
        "anything else",
        "more info",
        "details",
    ]
    STOPWORDS = {
        "the",
        "and",
        "or",
        "a",
        "an",
        "of",
        "to",
        "for",
        "this",
        "that",
        "it",
        "is",
        "are",
        "be",
        "do",
        "does",
    }

    def __init__(
        self,
        min_question_words: int = 3,
        min_specific_terms: int = 1,
        vagueness_threshold: float = 0.7,
        embedding_model=None
    ):
        self.min_question_words = min_question_words
        self.min_specific_terms = min_specific_terms
        self.vagueness_threshold = vagueness_threshold
        self.embedding_model = embedding_model

    def entrypoint_decision(self, question: str, conversation_history: Optional[List[str]]) -> AgentDecision:
        tokens = _normalize(question).split()
        history = conversation_history or []

        if len(tokens) < self.min_question_words:
            return AgentDecision.CLARIFY

        if self._pronoun_without_history(question, history):
            return AgentDecision.CLARIFY

        if self._lacks_specific_terms(tokens):
            return AgentDecision.CLARIFY

        if self._ambiguous_without_modifiers(tokens):
            return AgentDecision.CLARIFY

        if self._is_semantically_vague(question):
            return AgentDecision.CLARIFY

        return AgentDecision.RETRIEVE

    def should_refuse(self, retrieval_confidence: float, threshold: float) -> bool:
        """Decide whether to refuse answering based on retrieval confidence."""
        return retrieval_confidence < threshold

    def refusal_message(self) -> str:
        """Provide a consistent refusal response for low-confidence retrievals."""
        return (
            "I could not find enough grounded context in the indexed documents to answer. "
            "Please rephrase the question or add more detail."
        )

    def _pronoun_without_history(self, question: str, history: List[str]) -> bool:
        return not history and bool(self.PRONOUN_PATTERN.search(question))

    def _lacks_specific_terms(self, tokens: List[str]) -> bool:
        significant = [token for token in tokens if token not in self.STOPWORDS and len(token) > 4]
        return len(significant) < self.min_specific_terms

    def _ambiguous_without_modifiers(self, tokens: List[str]) -> bool:
        contains_ambiguous = any(token in self.AMBIGUOUS_KEYWORDS for token in tokens)
        has_modifier = any(
            token not in self.AMBIGUOUS_KEYWORDS and len(token) >= 6 and token not in self.STOPWORDS
            for token in tokens
        )
        return contains_ambiguous and not has_modifier

    def _is_semantically_vague(self, question: str) -> bool:
        """Check if question matches common vague patterns using semantic similarity."""
        normalized = _normalize(question)
        
        # Quick keyword check
        for vague_phrase in self.VAGUE_QUESTIONS:
            if vague_phrase in normalized:
                return True
        
        # Semantic similarity check if embedding model available
        if self.embedding_model:
            try:
                question_embedding = self.embedding_model.encode([question])
                vague_embeddings = self.embedding_model.encode(self.VAGUE_QUESTIONS)
                
                from sklearn.metrics.pairwise import cosine_similarity
                import numpy as np
                
                similarities = cosine_similarity(question_embedding, vague_embeddings)[0]
                max_similarity = float(np.max(similarities))
                
                return max_similarity >= self.vagueness_threshold
            except Exception:
                pass  # Fall back to keyword-only detection
        
        return False
