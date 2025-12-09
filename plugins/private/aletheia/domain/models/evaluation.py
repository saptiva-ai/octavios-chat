from pydantic import BaseModel
from typing import List, Optional
from enum import Enum

class CompletionLevel(str, Enum):
    """Levels of research completion based on Together AI pattern"""
    INSUFFICIENT = "insufficient"  # < 40% complete
    PARTIAL = "partial"           # 40-70% complete  
    ADEQUATE = "adequate"         # 70-85% complete
    COMPREHENSIVE = "comprehensive" # 85%+ complete

class InformationGap(BaseModel):
    """Represents an identified gap in research coverage"""
    gap_type: str  # e.g., "missing_competitor", "lacking_financial_data", "no_recent_updates"
    description: str
    priority: int  # 1-5, where 5 is highest priority
    suggested_query: str
    
class CompletionScore(BaseModel):
    """Evaluation of research completeness using Together AI scoring approach"""
    overall_score: float  # 0.0 - 1.0
    completion_level: CompletionLevel
    coverage_areas: dict  # {"competitors": 0.8, "market_size": 0.6, "regulations": 0.9}
    identified_gaps: List[InformationGap]
    confidence: float  # 0.0 - 1.0, confidence in the evaluation
    reasoning: str
    
class RefinementQuery(BaseModel):
    """Generated follow-up query to address information gaps"""
    query: str
    gap_addressed: str  # which gap this query targets
    priority: int
    expected_sources: List[str]  # ["web", "academic", "financial_reports"]