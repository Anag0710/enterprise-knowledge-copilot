"""
Additional specialized tools for the agent.
"""
import re
from typing import Dict, List, Optional
from dataclasses import dataclass


@dataclass
class CalculationResult:
    """Result from calculator tool."""
    expression: str
    result: float
    success: bool
    error: Optional[str] = None


@dataclass
class ComparisonResult:
    """Result from comparison tool."""
    items: List[str]
    comparison: str
    retrieved_info: Dict[str, str]
    success: bool


@dataclass
class SummaryResult:
    """Result from summarization tool."""
    summary: str
    source_count: int
    confidence: float
    success: bool


class CalculatorTool:
    """
    Performs basic arithmetic calculations.
    
    Useful for queries like:
    - "What is 15 + 20?"
    - "Calculate 365 days * 8 hours"
    - "How much is 50000 * 0.15?"
    """
    
    def __init__(self):
        self.safe_functions = {
            'abs': abs,
            'round': round,
            'min': min,
            'max': max,
            'sum': sum,
        }
    
    def run(self, expression: str) -> CalculationResult:
        """
        Evaluate mathematical expression safely.
        
        Args:
            expression: Math expression (e.g., "15 + 20")
            
        Returns:
            CalculationResult with computed value
        """
        try:
            # Clean the expression
            expression = expression.strip()
            
            # Remove common words
            expression = re.sub(r'\b(what is|calculate|compute|equals?)\b', '', expression, flags=re.IGNORECASE)
            expression = expression.strip()
            
            # Safety check - only allow numbers, operators, and safe functions
            allowed_chars = set('0123456789+-*/().%^ ')
            if not all(c in allowed_chars or c.isalpha() for c in expression):
                return CalculationResult(
                    expression=expression,
                    result=0.0,
                    success=False,
                    error="Invalid characters in expression"
                )
            
            # Replace ^ with **
            expression = expression.replace('^', '**')
            
            # Evaluate
            result = eval(expression, {"__builtins__": {}}, self.safe_functions)
            
            return CalculationResult(
                expression=expression,
                result=float(result),
                success=True
            )
        
        except Exception as e:
            return CalculationResult(
                expression=expression,
                result=0.0,
                success=False,
                error=str(e)
            )
    
    def can_handle(self, question: str) -> bool:
        """Check if question requires calculation."""
        calc_keywords = [
            'calculate', 'compute', 'what is', 'how much',
            'add', 'subtract', 'multiply', 'divide',
            '+', '-', '*', '/', '='
        ]
        
        question_lower = question.lower()
        
        # Must have a calc keyword
        has_keyword = any(kw in question_lower for kw in calc_keywords)
        
        # Must have numbers
        has_numbers = bool(re.search(r'\d', question))
        
        return has_keyword and has_numbers


class ComparisonTool:
    """
    Compares multiple items from retrieved documents.
    
    Useful for queries like:
    - "Compare policy A vs policy B"
    - "What's the difference between X and Y?"
    - "Which is better: A or B?"
    """
    
    def __init__(self, retrieval_tool):
        self.retrieval_tool = retrieval_tool
    
    def run(self, question: str, items_to_compare: List[str]) -> ComparisonResult:
        """
        Compare multiple items.
        
        Args:
            question: Original question
            items_to_compare: List of items to compare
            
        Returns:
            ComparisonResult with comparison info
        """
        try:
            # Retrieve info for each item
            retrieved_info = {}
            
            for item in items_to_compare:
                query = f"{item} details specifications"
                result = self.retrieval_tool.run(query)
                
                if result.chunks:
                    # Get top context
                    context = result.chunks[0].text[:500]
                    retrieved_info[item] = context
                else:
                    retrieved_info[item] = "No information found"
            
            # Build comparison text
            comparison_lines = [f"Comparison of {', '.join(items_to_compare)}:\n"]
            
            for item, info in retrieved_info.items():
                comparison_lines.append(f"\n**{item}:**")
                comparison_lines.append(f"{info}\n")
            
            comparison = "\n".join(comparison_lines)
            
            return ComparisonResult(
                items=items_to_compare,
                comparison=comparison,
                retrieved_info=retrieved_info,
                success=True
            )
        
        except Exception as e:
            return ComparisonResult(
                items=items_to_compare,
                comparison=f"Comparison failed: {str(e)}",
                retrieved_info={},
                success=False
            )
    
    def can_handle(self, question: str) -> bool:
        """Check if question requires comparison."""
        compare_keywords = [
            'compare', 'comparison', 'difference between', 'vs',
            'versus', 'better than', 'which is', 'contrast'
        ]
        
        question_lower = question.lower()
        return any(kw in question_lower for kw in compare_keywords)
    
    def extract_items(self, question: str) -> List[str]:
        """Extract items to compare from question."""
        # Look for "X vs Y", "X and Y", "X or Y" patterns
        patterns = [
            r'compare\s+(.+?)\s+(?:vs|versus|and|with)\s+(.+?)(?:\?|$)',
            r'difference between\s+(.+?)\s+and\s+(.+?)(?:\?|$)',
            r'(.+?)\s+(?:vs|versus)\s+(.+?)(?:\?|$)',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                items = [match.group(1).strip(), match.group(2).strip()]
                return items
        
        return []


class SummarizationTool:
    """
    Summarizes information across multiple documents.
    
    Useful for queries like:
    - "Summarize all policies"
    - "Give me an overview of X"
    - "What are the main points about Y?"
    """
    
    def __init__(self, retrieval_tool, llm_client=None):
        self.retrieval_tool = retrieval_tool
        self.llm_client = llm_client
    
    def run(self, question: str, topic: str) -> SummaryResult:
        """
        Create summary of topic from documents.
        
        Args:
            question: Original question
            topic: Topic to summarize
            
        Returns:
            SummaryResult with summary text
        """
        try:
            # Retrieve relevant chunks
            result = self.retrieval_tool.run(f"{topic} overview summary")
            
            if not result.chunks:
                return SummaryResult(
                    summary=f"No information found about {topic}",
                    source_count=0,
                    confidence=0.0,
                    success=False
                )
            
            # Combine top chunks
            combined_context = "\n\n".join([
                f"From {chunk.metadata.get('source', 'unknown')} (page {chunk.metadata.get('page', '?')}):\n{chunk.text}"
                for chunk in result.chunks[:5]  # Top 5 chunks
            ])
            
            # Generate summary
            if self.llm_client:
                prompt = f"""Summarize the following information about {topic}:

{combined_context}

Provide a concise summary highlighting the key points."""
                
                try:
                    summary = self.llm_client.generate(prompt)
                except Exception:
                    summary = self._fallback_summary(combined_context)
            else:
                summary = self._fallback_summary(combined_context)
            
            return SummaryResult(
                summary=summary,
                source_count=len(result.chunks),
                confidence=result.confidence,
                success=True
            )
        
        except Exception as e:
            return SummaryResult(
                summary=f"Summarization failed: {str(e)}",
                source_count=0,
                confidence=0.0,
                success=False
            )
    
    def _fallback_summary(self, context: str) -> str:
        """Create basic summary without LLM."""
        # Take first 3 sentences from combined context
        sentences = re.split(r'[.!?]+', context)
        summary_sentences = [s.strip() for s in sentences[:3] if s.strip()]
        return ". ".join(summary_sentences) + "."
    
    def can_handle(self, question: str) -> bool:
        """Check if question requires summarization."""
        summary_keywords = [
            'summarize', 'summary', 'overview', 'main points',
            'key points', 'highlights', 'brief', 'in short'
        ]
        
        question_lower = question.lower()
        return any(kw in question_lower for kw in summary_keywords)


class MultiToolRouter:
    """
    Routes questions to appropriate specialized tools.
    
    Decision order:
    1. Calculator - for math operations
    2. Comparison - for comparing items
    3. Summarization - for overviews
    4. Standard retrieval + answer - default
    """
    
    def __init__(
        self,
        retrieval_tool,
        answer_tool,
        llm_client=None
    ):
        self.retrieval_tool = retrieval_tool
        self.answer_tool = answer_tool
        
        # Initialize specialized tools
        self.calculator = CalculatorTool()
        self.comparison = ComparisonTool(retrieval_tool)
        self.summarization = SummarizationTool(retrieval_tool, llm_client)
    
    def route(self, question: str) -> tuple[str, object]:
        """
        Route question to appropriate tool.
        
        Args:
            question: User's question
            
        Returns:
            Tuple of (tool_name, tool_instance)
        """
        # Check calculator
        if self.calculator.can_handle(question):
            return ("calculator", self.calculator)
        
        # Check comparison
        if self.comparison.can_handle(question):
            items = self.comparison.extract_items(question)
            if items:
                return ("comparison", self.comparison)
        
        # Check summarization
        if self.summarization.can_handle(question):
            return ("summarization", self.summarization)
        
        # Default to standard retrieval + answer
        return ("standard", None)
