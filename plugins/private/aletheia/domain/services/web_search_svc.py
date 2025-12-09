"""
Web Search Service - Implements fetch→extract→rank→synthesize pattern.

This service orchestrates web search with the following steps:
1. Fetch: Search web using Tavily API
2. Extract: Normalize and clean search results
3. Rank: Score sources by relevance (BM25-like scoring)
4. Synthesize: Generate answer with citations using Saptiva model
"""

import os
import re
from typing import List, Dict, Optional
from datetime import datetime
from adapters.tavily_search.tavily_client import TavilySearchAdapter
from adapters.saptiva_model.saptiva_client import SaptivaModelAdapter


class WebSearchService:
    """
    Service for web search with synthesis and citation support.
    """

    def __init__(self):
        # Initialize Tavily search adapter
        self.search_adapter = TavilySearchAdapter()

        # Initialize Saptiva model for synthesis
        self.model_adapter = SaptivaModelAdapter()
        self.synthesis_model = os.getenv("SAPTIVA_MODEL_WRITER", "Saptiva Cortex")

        # Configuration from environment
        self.max_results = int(os.getenv("TAVILY_MAX_RESULTS", "15"))
        self.search_depth = os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
        self.timeout = int(os.getenv("TAVILY_TIMEOUT", "60"))

    async def search_and_synthesize(
        self,
        query: str,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        max_results: Optional[int] = None,
        max_depth: Optional[int] = 2,
        locale: Optional[str] = "es",
        time_window: Optional[str] = None
    ) -> Dict:
        """
        Performs web search and synthesizes an answer with citations.

        Args:
            query: Search query
            allowed_domains: List of allowed domains (whitelist)
            blocked_domains: List of blocked domains (blacklist)
            max_results: Maximum number of results to fetch
            max_depth: Search depth (1=basic, 2=advanced)
            locale: Language/locale for search (e.g., "es", "en")
            time_window: Time window for results (e.g., "month", "year")

        Returns:
            Dictionary with answer, confidence, sources, and diagnostics
        """
        # Step 1: Fetch - Search web with Tavily
        search_results = await self._fetch_results(
            query=query,
            max_results=max_results or self.max_results,
            allowed_domains=allowed_domains,
            blocked_domains=blocked_domains,
            time_window=time_window
        )

        if not search_results:
            return {
                "answer": "No se encontraron resultados para la consulta.",
                "confidence": 0.0,
                "sources": [],
                "fetches": 0
            }

        # Step 2: Extract - Normalize and clean results
        extracted_sources = self._extract_and_normalize(search_results)

        # Step 3: Rank - Score sources by relevance
        ranked_sources = self._rank_sources(extracted_sources, query)

        # Limit to max_results
        if max_results:
            ranked_sources = ranked_sources[:max_results]

        # Step 4: Synthesize - Generate answer with citations
        synthesis_result = await self._synthesize_answer(query, ranked_sources)

        return {
            "answer": synthesis_result["answer"],
            "confidence": synthesis_result["confidence"],
            "sources": ranked_sources,
            "fetches": len(search_results)
        }

    async def _fetch_results(
        self,
        query: str,
        max_results: int,
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None,
        time_window: Optional[str] = None
    ) -> List[Dict]:
        """
        Fetch search results from Tavily API.
        """
        try:
            # Build search parameters
            search_params = {
                "query": query,
                "search_depth": self.search_depth,
                "max_results": max_results
            }

            # Add domain filters if specified
            if allowed_domains:
                search_params["include_domains"] = allowed_domains
            if blocked_domains:
                search_params["exclude_domains"] = blocked_domains

            # Perform search
            results = self.search_adapter.search(
                query=query,
                max_results=max_results
            )

            # Filter results based on domain constraints
            if allowed_domains or blocked_domains:
                results = self._filter_by_domains(
                    results,
                    allowed_domains,
                    blocked_domains
                )

            return results

        except Exception as e:
            print(f"Error fetching search results: {e}")
            return []

    def _filter_by_domains(
        self,
        results: List[Dict],
        allowed_domains: Optional[List[str]] = None,
        blocked_domains: Optional[List[str]] = None
    ) -> List[Dict]:
        """
        Filter search results based on domain constraints.
        """
        filtered = []

        for result in results:
            url = result.get("url", "")
            domain = self._extract_domain(url)

            # Check blocked domains
            if blocked_domains and domain in blocked_domains:
                continue

            # Check allowed domains (if whitelist is provided)
            if allowed_domains and domain not in allowed_domains:
                continue

            filtered.append(result)

        return filtered

    def _extract_domain(self, url: str) -> str:
        """
        Extract domain from URL.
        """
        # Simple regex to extract domain
        match = re.search(r'https?://(?:www\.)?([^/]+)', url)
        return match.group(1) if match else ""

    def _extract_and_normalize(self, search_results: List[Dict]) -> List[Dict]:
        """
        Extract and normalize search results into standard format.
        """
        normalized = []

        for result in search_results:
            source = {
                "url": result.get("url", ""),
                "title": result.get("title", ""),
                "snippet": result.get("content", "")[:500],  # Limit snippet length
                "published_at": result.get("published_date"),
                "first_seen_at": datetime.utcnow().isoformat() + "Z",
                "source_type": "WEB",
                "raw_score": result.get("score", 0.5),  # Tavily's relevance score
                "content": result.get("content", "")  # Full content for synthesis
            }
            normalized.append(source)

        return normalized

    def _rank_sources(self, sources: List[Dict], query: str) -> List[Dict]:
        """
        Rank sources by relevance using BM25-like scoring.

        Scoring factors:
        - Tavily's native relevance score
        - Query term frequency in title and content
        - Content length (prefer substantial content)
        - Recency (if available)
        """
        query_terms = set(query.lower().split())

        for source in sources:
            # Start with Tavily's score
            base_score = source.get("raw_score", 0.5)

            # Term frequency in title (higher weight)
            title_terms = set(source.get("title", "").lower().split())
            title_overlap = len(query_terms.intersection(title_terms))
            title_score = title_overlap * 0.3

            # Term frequency in content
            content_terms = set(source.get("content", "").lower().split())
            content_overlap = len(query_terms.intersection(content_terms))
            content_score = content_overlap * 0.1

            # Content length bonus (prefer substantial sources)
            content_length = len(source.get("content", ""))
            length_score = min(content_length / 1000, 1.0) * 0.1

            # Combined score
            source["relevance_score"] = base_score + title_score + content_score + length_score

        # Sort by relevance score (descending)
        sources.sort(key=lambda x: x.get("relevance_score", 0), reverse=True)

        return sources

    async def _synthesize_answer(self, query: str, sources: List[Dict]) -> Dict:
        """
        Synthesize an answer from ranked sources using Saptiva model.

        The model is instructed to:
        - Generate a comprehensive answer based on sources
        - Include exact citations [1], [2], etc.
        - Provide a confidence score based on source quality and consistency
        """
        # Build context from sources
        context_parts = []
        for idx, source in enumerate(sources, 1):
            context_parts.append(
                f"[{idx}] {source['title']}\n"
                f"URL: {source['url']}\n"
                f"Content: {source['content'][:1000]}...\n"
            )

        context = "\n".join(context_parts)

        # Build synthesis prompt
        synthesis_prompt = f"""Eres un asistente de investigación que sintetiza información de múltiples fuentes web.

PREGUNTA DEL USUARIO:
{query}

FUENTES DISPONIBLES:
{context}

INSTRUCCIONES:
1. Responde la pregunta del usuario de manera completa y precisa
2. Usa SOLO la información de las fuentes proporcionadas
3. Incluye citas exactas usando el formato [1], [2], etc. para cada afirmación
4. Si las fuentes son contradictorias, menciona las diferentes perspectivas
5. Si la información es insuficiente, indícalo claramente
6. Genera una respuesta en español, clara y bien estructurada

FORMATO DE RESPUESTA:
Responde con un JSON que contenga:
- "answer": tu respuesta con citas [1], [2], etc.
- "confidence": un valor entre 0.0 y 1.0 que refleje:
  * 1.0 = información completa, consistente, de fuentes autorizadas
  * 0.7-0.9 = información buena pero con algunos gaps o fuentes menos autorizadas
  * 0.4-0.6 = información parcial o fuentes de calidad mixta
  * 0.0-0.3 = información muy limitada o poco confiable

Responde SOLO con el JSON, sin texto adicional."""

        try:
            # Call Saptiva model for synthesis
            response = self.model_adapter.generate(
                model=self.synthesis_model,
                prompt=synthesis_prompt,
                max_tokens=2000,
                temperature=0.3  # Low temperature for factual synthesis
            )

            # Parse response - extract content from Saptiva response
            import json
            content = response.get("content", "")

            try:
                result = json.loads(content)
                return {
                    "answer": result.get("answer", content),
                    "confidence": float(result.get("confidence", 0.7))
                }
            except json.JSONDecodeError:
                # Fallback: use raw response and estimate confidence
                return {
                    "answer": content,
                    "confidence": 0.7 if len(sources) >= 3 else 0.5
                }

        except Exception as e:
            print(f"Error during synthesis: {e}")
            # Fallback: generate simple answer from sources
            return {
                "answer": f"Se encontraron {len(sources)} fuentes relevantes, pero hubo un error al sintetizar la respuesta.",
                "confidence": 0.3
            }
