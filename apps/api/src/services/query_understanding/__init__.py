"""
Query Understanding Module - NLP Pipeline for Query Analysis

Responsible for analyzing user queries to determine:
- Intent (what the user wants to know)
- Complexity (how specific/vague the query is)
- Entities (named entities mentioned)
- Query expansion (improving vague queries)

Architecture:
- Hybrid approach: Rule-based + ML (zero-shot classification)
- SOLID principles: Each component has single responsibility
- Strategy pattern: Different analyzers for different aspects
"""

from .types import (
    QueryIntent,
    QueryComplexity,
    QueryAnalysis,
    QueryContext,
)
from .intent_classifier import IntentClassifier
from .complexity_analyzer import ComplexityAnalyzer
from .query_understanding_service import (
    QueryUnderstandingService,
    get_query_understanding_service,
)

__all__ = [
    "QueryIntent",
    "QueryComplexity",
    "QueryAnalysis",
    "QueryContext",
    "IntentClassifier",
    "ComplexityAnalyzer",
    "QueryUnderstandingService",
    "get_query_understanding_service",
]
