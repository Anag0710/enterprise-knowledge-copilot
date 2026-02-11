"""
Query reformulation to improve retrieval by generating alternative phrasings.
"""
from typing import List
import re


class QueryReformulator:
    """
    Generate alternative query phrasings for better retrieval.
    
    Strategies:
    1. Expand abbreviations
    2. Add synonyms
    3. Rephrase questions
    """
    
    # Common enterprise abbreviations
    ABBREVIATIONS = {
        "pto": ["paid time off", "vacation", "leave"],
        "hr": ["human resources", "personnel"],
        "eod": ["end of day", "close of business"],
        "asap": ["as soon as possible", "urgent"],
        "fte": ["full time employee", "full time equivalent"],
        "wfh": ["work from home", "remote work", "telecommute"],
        "ooo": ["out of office", "away"],
        "etc": ["equipment", "camera equipment"],
        "eos": ["canon eos", "eos camera"],
        "iso": ["light sensitivity", "film speed"],
        "wb": ["white balance", "color temperature"],
        "af": ["autofocus", "focus system"],
    }
    
    def __init__(self, max_variations: int = 3):
        self.max_variations = max_variations
    
    def reformulate(self, query: str) -> List[str]:
        """
        Generate alternative phrasings of the query.
        
        Args:
            query: Original query string
            
        Returns:
            List of query variations (including original)
        """
        variations = [query]
        query_lower = query.lower()
        
        # Strategy 1: Expand abbreviations
        for abbrev, expansions in self.ABBREVIATIONS.items():
            # Check if abbreviation appears as whole word
            if re.search(r'\b' + re.escape(abbrev) + r'\b', query_lower):
                for expansion in expansions[:self.max_variations - 1]:
                    # Replace abbreviation with expansion
                    expanded = re.sub(
                        r'\b' + re.escape(abbrev) + r'\b',
                        expansion,
                        query_lower,
                        flags=re.IGNORECASE
                    )
                    if expanded not in [v.lower() for v in variations]:
                        variations.append(expanded)
        
        # Strategy 2: Add question variants
        variations.extend(self._generate_question_variants(query))
        
        # Strategy 3: Simplify (remove question words)
        simplified = self._simplify_query(query)
        if simplified and simplified not in variations:
            variations.append(simplified)
        
        # Limit total variations
        return variations[:self.max_variations + 1]  # +1 for original
    
    def _generate_question_variants(self, query: str) -> List[str]:
        """Generate different question formulations."""
        variants = []
        query_lower = query.lower().strip()
        
        # If starts with "what is", try "explain"
        if query_lower.startswith("what is ") or query_lower.startswith("what's "):
            topic = re.sub(r'^what\s+(is|\'s)\s+', '', query_lower, flags=re.IGNORECASE)
            variants.append(f"explain {topic}")
            variants.append(f"{topic} definition")
        
        # If starts with "how to", try "steps for"
        if query_lower.startswith("how to "):
            topic = query_lower.replace("how to ", "")
            variants.append(f"steps for {topic}")
            variants.append(f"{topic} instructions")
        
        # If starts with "how many", try "count of"
        if query_lower.startswith("how many "):
            topic = query_lower.replace("how many ", "")
            variants.append(f"count of {topic}")
            variants.append(f"total {topic}")
        
        return variants
    
    def _simplify_query(self, query: str) -> str:
        """
        Simplify query by removing question words.
        Useful for keyword matching.
        """
        # Remove common question words
        simplified = re.sub(
            r'\b(what|how|where|when|why|who|which|is|are|the|a|an)\b',
            '',
            query.lower(),
            flags=re.IGNORECASE
        )
        
        # Clean up extra spaces
        simplified = ' '.join(simplified.split())
        return simplified.strip()
