import os
import json
from typing import List, Dict, Any
from domain.models.evidence import Evidence
from domain.models.evaluation import CompletionScore, InformationGap, RefinementQuery, CompletionLevel
from adapters.saptiva_model.saptiva_client import SaptivaModelAdapter

class EvaluationService:
    """
    Evaluation Agent implementing Together AI pattern with Saptiva models.
    Assesses research completeness and identifies information gaps.
    """
    
    def __init__(self):
        self.model_adapter = SaptivaModelAdapter()
        # Use Saptiva Cortex for evaluation (analytical tasks)
        self.evaluation_model = os.getenv("SAPTIVA_MODEL_WRITER", "SAPTIVA_CORTEX")
    
    def evaluate_research_completeness(self, query: str, evidence: List[Evidence]) -> CompletionScore:
        """
        Evaluates completeness of research using Together AI pattern.
        """
        prompt = self._build_evaluation_prompt(query, evidence)
        
        response = self.model_adapter.generate(
            model=self.evaluation_model,
            prompt=prompt,
            temperature=0.3,  # Lower temperature for analytical tasks
            max_tokens=1500
        )
        
        return self._parse_evaluation_response(response.get("content", ""))
    
    def identify_information_gaps(self, query: str, evidence: List[Evidence]) -> List[InformationGap]:
        """
        Identifies specific information gaps in research coverage.
        """
        prompt = self._build_gap_analysis_prompt(query, evidence)
        
        response = self.model_adapter.generate(
            model=self.evaluation_model,
            prompt=prompt,
            temperature=0.2,
            max_tokens=1000
        )
        
        return self._parse_gaps_response(response.get("content", ""))
    
    def generate_refinement_queries(self, gaps: List[InformationGap], original_query: str) -> List[RefinementQuery]:
        """
        Generates targeted follow-up queries to address identified gaps.
        """
        prompt = self._build_refinement_prompt(gaps, original_query)
        
        response = self.model_adapter.generate(
            model=self.evaluation_model,
            prompt=prompt,
            temperature=0.4,  # Slightly higher for creative query generation
            max_tokens=800
        )
        
        return self._parse_refinement_response(response.get("content", ""))
    
    def _build_evaluation_prompt(self, query: str, evidence: List[Evidence]) -> str:
        """Build prompt for research completeness evaluation."""
        evidence_summary = self._summarize_evidence(evidence)
        
        return f"""
You are an expert research evaluation agent. Analyze the completeness of research conducted for the given query.

ORIGINAL QUERY: "{query}"

EVIDENCE COLLECTED:
{evidence_summary}

Evaluate the research completeness and provide a JSON response with the following structure:
{{
    "overall_score": 0.75,  // 0.0-1.0 scale
    "completion_level": "adequate",  // insufficient/partial/adequate/comprehensive
    "coverage_areas": {{
        "competitors": 0.8,
        "market_analysis": 0.6,
        "financial_data": 0.4,
        "regulations": 0.9,
        "recent_developments": 0.3
    }},
    "confidence": 0.85,  // 0.0-1.0 confidence in evaluation
    "reasoning": "Detailed explanation of the evaluation..."
}}

Focus on:
1. Coverage depth across different aspects of the query
2. Source diversity and quality
3. Recency of information
4. Completeness for decision-making

Provide your evaluation:
"""

    def _build_gap_analysis_prompt(self, query: str, evidence: List[Evidence]) -> str:
        """Build prompt for gap identification."""
        evidence_summary = self._summarize_evidence(evidence)
        
        return f"""
You are a research gap analysis expert. Identify specific information gaps in the research.

ORIGINAL QUERY: "{query}"

CURRENT EVIDENCE:
{evidence_summary}

Identify information gaps and provide a JSON array response:
[
    {{
        "gap_type": "missing_competitor_analysis",
        "description": "Lack of detailed competitive positioning data",
        "priority": 4,  // 1-5 scale, 5 = highest priority
        "suggested_query": "Competitive analysis and market positioning of [specific competitors]"
    }}
]

Look for gaps in:
- Competitor analysis and positioning
- Market size and growth data
- Financial performance metrics
- Regulatory environment changes
- Technology trends and innovations
- Customer sentiment and reviews
- Geographic coverage
- Recent news and developments

Provide 3-7 specific gaps:
"""

    def _build_refinement_prompt(self, gaps: List[InformationGap], original_query: str) -> str:
        """Build prompt for generating refinement queries."""
        gaps_text = "\n".join([
            f"- {gap.gap_type}: {gap.description} (Priority: {gap.priority})"
            for gap in gaps
        ])
        
        return f"""
You are a research query refinement expert. Generate specific follow-up queries to address identified gaps.

ORIGINAL QUERY: "{original_query}"

IDENTIFIED GAPS:
{gaps_text}

Generate targeted follow-up queries as JSON array:
[
    {{
        "query": "Specific, actionable search query",
        "gap_addressed": "gap_type from above",
        "priority": 4,  // 1-5 scale
        "expected_sources": ["web", "financial_reports", "news"]
    }}
]

Make queries:
1. Specific and actionable for search engines
2. Focused on filling one gap at a time
3. Optimized for current web search (2024 context)
4. Include specific company/location names when relevant

Generate 3-5 refinement queries:
"""

    def _summarize_evidence(self, evidence: List[Evidence]) -> str:
        """Create a concise summary of evidence for prompts."""
        if not evidence:
            return "No evidence collected yet."
        
        summary_lines = []
        for i, ev in enumerate(evidence[:10], 1):  # Limit to first 10 for prompt efficiency
            summary_lines.append(f"{i}. Source: {ev.source.title} ({ev.source.url})")
            summary_lines.append(f"   Content: {ev.excerpt[:150]}...")
        
        if len(evidence) > 10:
            summary_lines.append(f"... and {len(evidence) - 10} more evidence items")
        
        return "\n".join(summary_lines)
    
    def _parse_evaluation_response(self, response: str) -> CompletionScore:
        """Parse JSON response into CompletionScore object."""
        try:
            # Extract JSON from response
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_text = response[json_start:json_end]
                data = json.loads(json_text)
                
                return CompletionScore(
                    overall_score=data.get("overall_score", 0.5),
                    completion_level=CompletionLevel(data.get("completion_level", "partial")),
                    coverage_areas=data.get("coverage_areas", {}),
                    identified_gaps=[],  # Will be filled separately
                    confidence=data.get("confidence", 0.7),
                    reasoning=data.get("reasoning", "")
                )
        except Exception as e:
            print(f"Error parsing evaluation response: {e}")
        
        # Fallback response
        return CompletionScore(
            overall_score=0.5,
            completion_level=CompletionLevel.PARTIAL,
            coverage_areas={},
            identified_gaps=[],
            confidence=0.5,
            reasoning="Could not parse evaluation response."
        )
    
    def _parse_gaps_response(self, response: str) -> List[InformationGap]:
        """Parse JSON response into InformationGap objects."""
        try:
            # Extract JSON from response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_text = response[json_start:json_end]
                data = json.loads(json_text)
                
                gaps = []
                for gap_data in data:
                    gaps.append(InformationGap(
                        gap_type=gap_data.get("gap_type", "unknown"),
                        description=gap_data.get("description", ""),
                        priority=gap_data.get("priority", 3),
                        suggested_query=gap_data.get("suggested_query", "")
                    ))
                return gaps
        except Exception as e:
            print(f"Error parsing gaps response: {e}")
        
        return []
    
    def _parse_refinement_response(self, response: str) -> List[RefinementQuery]:
        """Parse JSON response into RefinementQuery objects."""
        try:
            # Extract JSON from response
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_text = response[json_start:json_end]
                data = json.loads(json_text)
                
                queries = []
                for query_data in data:
                    queries.append(RefinementQuery(
                        query=query_data.get("query", ""),
                        gap_addressed=query_data.get("gap_addressed", ""),
                        priority=query_data.get("priority", 3),
                        expected_sources=query_data.get("expected_sources", ["web"])
                    ))
                return queries
        except Exception as e:
            print(f"Error parsing refinement response: {e}")
        
        return []