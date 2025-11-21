"""
Retrieval Strategy Module - Adaptive Document Retrieval

Implements Strategy Pattern for different retrieval approaches:
- OverviewRetrieval: For generic document questions
- SemanticSearch: For specific fact-finding
- HybridRetrieval: BM25 + Semantic (best of both worlds)

Architecture:
- Strategy Pattern: Different strategies for different query types
- Adaptive Orchestrator: Selects strategy based on query analysis
- Observable: Detailed logging and metrics
"""

from .types import Segment, RetrievalResult
from .retrieval_strategy import RetrievalStrategy
from .overview_strategy import OverviewRetrievalStrategy
from .semantic_search_strategy import SemanticSearchStrategy
from .adaptive_orchestrator import AdaptiveRetrievalOrchestrator

__all__ = [
    "Segment",
    "RetrievalResult",
    "RetrievalStrategy",
    "OverviewRetrievalStrategy",
    "SemanticSearchStrategy",
    "AdaptiveRetrievalOrchestrator",
]
