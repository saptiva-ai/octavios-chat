import os
from typing import List
from domain.models.evidence import Evidence
from adapters.saptiva_model.saptiva_client import SaptivaModelAdapter

class WriterService:
    def __init__(self):
        self.model_adapter = SaptivaModelAdapter()
        # As per README, Writer uses 'Saptiva Cortex'
        self.writer_model = os.getenv("SAPTIVA_MODEL_WRITER", "Saptiva Cortex")

    def write_report(self, query: str, evidence_list: List[Evidence]) -> str:
        """
        Generates a markdown report based on the collected evidence.
        """
        prompt = self._build_prompt(query, evidence_list)
        
        response = self.model_adapter.generate(
            model=self.writer_model,
            prompt=prompt,
            max_tokens=3000,
            temperature=0.7
        )
        
        return response.get("content", "# Empty Report")

    def _build_prompt(self, query: str, evidence_list: List[Evidence]) -> str:
        evidence_str = "\n\n".join(
            [f"Source: {ev.source.url}\nTitle: {ev.source.title}\nExcerpt: {ev.excerpt}" for ev in evidence_list]
        )

        return f"""
Based on the following user query and the collected evidence, please write a comprehensive markdown report.
Cite the evidence by referencing the source URL in the format [Source](URL).

Use the following structure:
# {query}

## Executive Summary
[Brief summary of key findings]

## Key Findings
[Main insights from the research]

## Detailed Analysis
[In-depth analysis with citations]

## Conclusions
[Summary of conclusions and implications]

## Sources
[Bibliography of all sources used]

User Query: "{query}"

Evidence:
---
{evidence_str}
---

Markdown Report:
"""
