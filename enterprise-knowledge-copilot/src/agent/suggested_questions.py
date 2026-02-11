"""
Suggested questions feature based on query analysis.
"""
from pathlib import Path
from typing import List, Dict
from collections import Counter
import json
import re


class SuggestedQuestions:
    """
    Generate suggested questions based on:
    1. Most frequently asked questions from logs
    2. Predefined common queries
    3. Document-based suggestions
    """
    
    # Default suggested questions (category-based)
    DEFAULT_SUGGESTIONS = {
        "HR & Policies": [
            "What is the PTO policy?",
            "How many vacation days do I get?",
            "What are the working hours?",
            "How do I request time off?"
        ],
        "IT & Equipment": [
            "How do I reset my password?",
            "What is the VPN setup process?",
            "How do I request new equipment?",
            "What software is available?"
        ],
        "General": [
            "What documents are available?",
            "How can I find information about...?",
            "Tell me about company policies"
        ]
    }
    
    def __init__(self, log_path: Path | None = None):
        """
        Initialize suggested questions generator.
        
        Args:
            log_path: Path to agent runs log (JSONL)
        """
        self.log_path = log_path
        self.question_cache = []
        self.category_suggestions = self.DEFAULT_SUGGESTIONS.copy()
    
    def get_from_logs(self, limit: int = 100, min_confidence: float = 0.6) -> List[str]:
        """
        Extract popular questions from logs.
        
        Args:
            limit: Max number of log entries to analyze
            min_confidence: Minimum confidence to consider (filters low-quality)
            
        Returns:
            List of popular questions
        """
        if not self.log_path or not self.log_path.exists():
            return []
        
        questions = []
        
        with open(self.log_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            
            for line in lines[-limit:]:
                try:
                    entry = json.loads(line.strip())
                    
                    # Filter by confidence and status
                    if (entry.get('confidence', 0) >= min_confidence and
                        entry.get('status') == 'answered'):
                        question = entry.get('question', '').strip()
                        if question and len(question) > 10:  # Filter very short
                            questions.append(question)
                
                except Exception:
                    continue
        
        # Count frequency
        if not questions:
            return []
        
        question_counts = Counter(questions)
        
        # Return top 10 most common
        popular = [q for q, count in question_counts.most_common(10)]
        return popular
    
    def get_by_category(self, category: str | None = None) -> List[str]:
        """
        Get suggested questions by category.
        
        Args:
            category: Category name (e.g., "HR & Policies"). If None, returns all.
            
        Returns:
            List of suggested questions
        """
        if category and category in self.category_suggestions:
            return self.category_suggestions[category]
        
        # Return all categories
        all_suggestions = []
        for cat_questions in self.category_suggestions.values():
            all_suggestions.extend(cat_questions)
        return all_suggestions
    
    def get_all_categories(self) -> Dict[str, List[str]]:
        """Get all categories with their questions."""
        return self.category_suggestions.copy()
    
    def get_smart_suggestions(
        self,
        current_context: List[str] | None = None,
        limit: int = 5
    ) -> List[str]:
        """
        Get smart suggestions based on context and popularity.
        
        Args:
            current_context: Recent questions in conversation
            limit: Number of suggestions to return
            
        Returns:
            List of relevant suggested questions
        """
        suggestions = []
        
        # Strategy 1: Get from logs (popular questions)
        log_based = self.get_from_logs(limit=200)
        suggestions.extend(log_based[:2])  # Top 2 from logs
        
        # Strategy 2: Get from defaults
        default_suggestions = []
        for cat_questions in self.category_suggestions.values():
            default_suggestions.extend(cat_questions)
        
        # If we have context, try to match related questions
        if current_context and current_context[-1]:
            last_question = current_context[-1].lower()
            
            # Simple keyword matching for related questions
            for q in default_suggestions:
                if any(word in q.lower() for word in last_question.split() if len(word) > 3):
                    if q not in suggestions:
                        suggestions.append(q)
        
        # Fill remaining with defaults
        for q in default_suggestions:
            if q not in suggestions:
                suggestions.append(q)
            if len(suggestions) >= limit:
                break
        
        return suggestions[:limit]
    
    def add_custom_category(self, category_name: str, questions: List[str]):
        """
        Add a custom category with questions.
        
        Args:
            category_name: Name of the category
            questions: List of questions for this category
        """
        self.category_suggestions[category_name] = questions
