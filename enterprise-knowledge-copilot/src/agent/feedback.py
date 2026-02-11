"""
User feedback system for tracking answer quality.
"""
from pathlib import Path
from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional, List
import json


@dataclass
class FeedbackEntry:
    """Single feedback entry."""
    question: str
    answer: str
    rating: str  # 'positive' or 'negative'
    comment: Optional[str]
    timestamp: str
    confidence: float
    status: str
    sources: List[dict]


class FeedbackLogger:
    """
    Log user feedback on agent responses.
    
    Stores feedback in JSONL format for later analysis and model improvement.
    """
    
    def __init__(self, log_path: Path):
        """
        Initialize feedback logger.
        
        Args:
            log_path: Path to feedback JSONL file
        """
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
    
    def log_feedback(
        self,
        question: str,
        answer: str,
        rating: str,
        confidence: float,
        status: str,
        sources: List[dict],
        comment: Optional[str] = None
    ):
        """
        Log feedback entry.
        
        Args:
            question: Original user question
            answer: Agent's answer
            rating: 'positive' (👍) or 'negative' (👎)
            confidence: Agent's confidence score
            status: Agent's response status
            sources: List of source citations
            comment: Optional user comment
        """
        if rating not in ['positive', 'negative']:
            raise ValueError(f"Invalid rating: {rating}. Must be 'positive' or 'negative'")
        
        entry = FeedbackEntry(
            question=question,
            answer=answer,
            rating=rating,
            comment=comment,
            timestamp=datetime.now().isoformat(),
            confidence=confidence,
            status=status,
            sources=sources
        )
        
        # Append to JSONL file
        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(asdict(entry)) + '\n')
    
    def get_recent_feedback(self, limit: int = 100) -> List[FeedbackEntry]:
        """
        Retrieve recent feedback entries.
        
        Args:
            limit: Maximum number of entries to return
            
        Returns:
            List of recent FeedbackEntry objects
        """
        if not self.log_path.exists():
            return []
        
        entries = []
        with open(self.log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            # Get last N lines
            for line in lines[-limit:]:
                try:
                    data = json.loads(line.strip())
                    entries.append(FeedbackEntry(**data))
                except Exception as e:
                    print(f"Warning: Failed to parse feedback entry: {e}")
        
        return entries
    
    def get_statistics(self) -> dict:
        """
        Calculate feedback statistics.
        
        Returns:
            Dictionary with feedback metrics
        """
        entries = self.get_recent_feedback(limit=10000)  # All entries
        
        if not entries:
            return {
                "total": 0,
                "positive": 0,
                "negative": 0,
                "positive_rate": 0.0,
                "avg_confidence_positive": 0.0,
                "avg_confidence_negative": 0.0
            }
        
        positive = [e for e in entries if e.rating == 'positive']
        negative = [e for e in entries if e.rating == 'negative']
        
        avg_conf_pos = sum(e.confidence for e in positive) / len(positive) if positive else 0.0
        avg_conf_neg = sum(e.confidence for e in negative) / len(negative) if negative else 0.0
        
        return {
            "total": len(entries),
            "positive": len(positive),
            "negative": len(negative),
            "positive_rate": len(positive) / len(entries) if entries else 0.0,
            "avg_confidence_positive": avg_conf_pos,
            "avg_confidence_negative": avg_conf_neg,
            "recent_entries": [asdict(e) for e in entries[-10:]]  # Last 10
        }
