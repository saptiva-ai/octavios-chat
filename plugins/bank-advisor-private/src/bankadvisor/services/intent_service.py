"""
Intent classification service for NLP query interpretation.

HU3 - NLP Query Interpretation:
- NlpIntentService: LLM-based intent classification (no fallback - requires LLM)
- IntentService: Legacy dashboard section disambiguation (unchanged)
"""

import yaml
import json
import difflib
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
from enum import Enum

import httpx
import structlog

logger = structlog.get_logger(__name__)


class Intent(str, Enum):
    """Query intent types for NLP processing."""
    EVOLUTION = "evolution"       # Show trend over time
    COMPARISON = "comparison"     # Compare banks
    RANKING = "ranking"           # Top/bottom banks
    POINT_VALUE = "point_value"   # Current value
    UNKNOWN = "unknown"


@dataclass
class ParsedIntent:
    """Result of intent classification."""
    intent: Intent
    confidence: float
    explanation: Optional[str] = None


class NlpIntentService:
    """
    Classifies user intent using Saptiva LLM.
    Requires LLM - no fallback. If LLM unavailable, returns UNKNOWN to trigger clarification.

    HU3 - NLP Query Interpretation
    """

    INTENT_PROMPT = """Eres un asistente que clasifica consultas bancarias.

Dada la siguiente consulta del usuario, determina la intención:

- "evolution": El usuario quiere ver cómo ha cambiado una métrica en el tiempo (tendencia, histórico, evolución)
- "comparison": El usuario quiere comparar entre bancos (vs, contra, comparar)
- "ranking": El usuario quiere ver un ranking (top, mejores, peores, ordenar)
- "point_value": El usuario quiere saber un valor específico actual (cuál es, cuánto, valor actual)
- "unknown": No está claro qué quiere el usuario

Contexto extraído:
- Métrica detectada: {metric}
- Bancos mencionados: {banks}
- Rango de fechas: {date_range}

Consulta: "{query}"

Responde SOLO con JSON válido:
{{"intent": "evolution|comparison|ranking|point_value|unknown", "confidence": 0.0-1.0, "explanation": "breve explicación"}}
"""

    @classmethod
    async def classify(
        cls,
        query: str,
        entities: Any,  # ExtractedEntities
        settings: Any = None  # Settings with saptiva config
    ) -> ParsedIntent:
        """
        Classify intent using HYBRID strategy: Rules-first, LLM-fallback.

        Strategy (SOLID - Open/Closed Principle):
        1. Try rule-based classification FIRST
        2. If rules are confident (>= 0.9), use them
        3. If rules uncertain (< 0.9), consult LLM for second opinion
        4. If LLM unavailable/fails, use rule result anyway

        This ensures:
        - Fast, deterministic classification for clear cases
        - LLM only for ambiguous cases (cost & latency optimization)
        - Graceful degradation if LLM fails

        Args:
            query: User query
            entities: ExtractedEntities from EntityService
            settings: Settings with Saptiva API config

        Returns:
            ParsedIntent with intent type and confidence
        """
        import os

        # Step 1: ALWAYS try rules first (fast, deterministic)
        rule_result = cls._classify_with_rules(query, entities)

        # Step 2: If rules are confident, trust them
        if rule_result.confidence >= 0.9:
            logger.debug(
                "nlp_intent.rules_confident",
                intent=rule_result.intent.value,
                confidence=rule_result.confidence,
                explanation=rule_result.explanation
            )
            return rule_result

        # Step 3: Rules uncertain -> consult LLM for second opinion
        saptiva_key = os.getenv("SAPTIVA_API_KEY", "")
        if not saptiva_key:
            logger.info(
                "nlp_intent.llm_not_configured",
                action="using_rule_result",
                rule_confidence=rule_result.confidence
            )
            return rule_result

        try:
            llm_result = await cls._classify_with_llm(query, entities, settings)

            # If LLM is more confident than rules, use LLM
            if llm_result.confidence > rule_result.confidence:
                logger.debug(
                    "nlp_intent.llm_override",
                    rule_intent=rule_result.intent.value,
                    rule_confidence=rule_result.confidence,
                    llm_intent=llm_result.intent.value,
                    llm_confidence=llm_result.confidence
                )
                return llm_result

            # Otherwise stick with rules
            return rule_result

        except Exception as e:
            logger.warning(
                "nlp_intent.llm_failed",
                error=str(e),
                action="using_rule_result"
            )
            return rule_result

    @classmethod
    async def _classify_with_llm(
        cls,
        query: str,
        entities: Any,
        settings: Any
    ) -> ParsedIntent:
        """Use Saptiva LLM for intent classification."""
        import os

        saptiva_key = os.getenv("SAPTIVA_API_KEY", "")
        saptiva_url = os.getenv("SAPTIVA_BASE_URL", "https://api.saptiva.com")

        # Build context for prompt
        date_range = "no especificado"
        if hasattr(entities, 'date_start') and hasattr(entities, 'date_end'):
            if entities.date_start and entities.date_end:
                date_range = f"{entities.date_start} a {entities.date_end}"
            elif entities.date_start:
                date_range = f"desde {entities.date_start}"

        metric_display = getattr(entities, 'metric_display', None) or "no detectada"
        banks = getattr(entities, 'banks', []) or []

        prompt = cls.INTENT_PROMPT.format(
            metric=metric_display,
            banks=", ".join(banks) if banks else "ninguno",
            date_range=date_range,
            query=query
        )

        # Call Saptiva API (ensure trailing slash to avoid 307 redirect)
        api_url = f"{saptiva_url.rstrip('/')}/v1/chat/completions/"
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.post(
                api_url,
                headers={
                    "Authorization": f"Bearer {saptiva_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "Saptiva Turbo",
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.1,  # Low temperature for consistent classification
                    "max_tokens": 150
                }
            )
            response.raise_for_status()

            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Parse JSON response (handle markdown code blocks)
            if "```" in content:
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]

            parsed = json.loads(content.strip())

            intent_str = parsed.get("intent", "unknown")
            try:
                intent = Intent(intent_str)
            except ValueError:
                intent = Intent.UNKNOWN

            return ParsedIntent(
                intent=intent,
                confidence=float(parsed.get("confidence", 0.5)),
                explanation=parsed.get("explanation")
            )

    @classmethod
    def _classify_with_rules(cls, query: str, entities: Any) -> ParsedIntent:
        """
        Rule-based intent classification (fallback when LLM unavailable).

        Rules (in priority order):
        1. Has "vs"/"contra"/"compara" → comparison (highest priority)
        2. Has "top"/"mejores"/"peores" → ranking
        3. Has date range (year/months) + metric → evolution (IMPORTANT)
        4. Has evolution keywords → evolution
        5. Default → point_value (with medium confidence)

        Args:
            query: User query
            entities: ExtractedEntities

        Returns:
            ParsedIntent with classified intent
        """
        query_lower = query.lower()

        # Rule 1: Comparison keywords (highest priority)
        comparison_keywords = ["vs", "contra", "compara", "comparar", "comparación", "comparacion", "versus"]
        if any(kw in query_lower for kw in comparison_keywords):
            return ParsedIntent(
                intent=Intent.COMPARISON,
                confidence=0.95,
                explanation="Detected comparison keywords (vs/contra/compara)"
            )

        # Rule 2: Ranking keywords
        ranking_keywords = ["top", "mejores", "peores", "ranking", "ordenar", "clasificación"]
        if any(kw in query_lower for kw in ranking_keywords):
            return ParsedIntent(
                intent=Intent.RANKING,
                confidence=0.95,
                explanation="Detected ranking keywords"
            )

        # Rule 3: Evolution indicators - Date range (CRITICAL)
        # If query has a date range (year, date range, months), it's asking for evolution
        has_date_range = False
        if hasattr(entities, 'date_start') and hasattr(entities, 'date_end'):
            if entities.date_start and entities.date_end:
                # Has both start and end dates -> evolution over time
                has_date_range = True
            elif entities.date_start:
                # Has start date only -> evolution from that point
                has_date_range = True

        if has_date_range:
            return ParsedIntent(
                intent=Intent.EVOLUTION,
                confidence=0.95,
                explanation="Detected date range - implies evolution over time"
            )

        # Rule 4: Evolution keywords
        evolution_keywords = ["evolución", "evolucion", "tendencia", "histórico", "historico", "cambio", "variación", "variacion"]
        has_evolution_keyword = any(kw in query_lower for kw in evolution_keywords)

        if has_evolution_keyword:
            return ParsedIntent(
                intent=Intent.EVOLUTION,
                confidence=0.9,
                explanation="Detected evolution keywords"
            )

        # Rule 5: Default to point_value with medium confidence
        # This allows clarification to trigger if confidence threshold is high
        return ParsedIntent(
            intent=Intent.POINT_VALUE,
            confidence=0.6,
            explanation="No strong indicators - defaulting to point value"
        )


# ==============================================================================
# LEGACY: DASHBOARD SECTION DISAMBIGUATION (unchanged for backward compatibility)
# ==============================================================================

@dataclass
class AmbiguityResult:
    is_ambiguous: bool
    options: List[str]
    resolved_id: Optional[str] = None
    missing_dimension: Optional[str] = None

class IntentService:
    _sections: Dict[str, Any] = {}
    _keyword_map: Dict[str, List[str]] = {}
    
    @classmethod
    def initialize(cls):
        if cls._sections:
            return

        config_path = Path(__file__).parent.parent / "config" / "sections.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            
        cls._sections = {s["id"]: s for s in data["sections"]}
        cls._build_index()

    # Explicit aliases for ambiguous terms (bypasses keyword intersection logic)
    _explicit_aliases: Dict[str, str] = {
        # Tasas - very specific mappings
        "tasa_mn": "tasa_mn_cuadro",
        "tasa mn": "tasa_mn_cuadro",
        "tasa pesos": "tasa_mn_cuadro",
        "tasa moneda nacional": "tasa_mn_cuadro",
        "tasa_me": "tasa_me_cuadro",
        "tasa me": "tasa_me_cuadro",
        "tasa dolares": "tasa_me_cuadro",
        "tasa moneda extranjera": "tasa_me_cuadro",
        # Direct metric names
        "icap": "icap_cuadro",
        "icap_total": "icap_cuadro",
        "capitalización": "icap_cuadro",
        "capitalizacion": "icap_cuadro",
        "tda": "tda_cuadro",
        "tda_cartera_total": "tda_cuadro",
        "deterioro": "tda_cuadro",
        "tasa deterioro": "tda_cuadro",
        # BA-P0-004: Common banking metrics (CNBV)
        "imor": "imor_cuadro",
        "icor": "icor_cuadro",
        "roe": "roe_cuadro",
        "roa": "roa_cuadro",
        "morosidad": "imor_cuadro",  # morosidad -> IMOR
        "índice de morosidad": "imor_cuadro",
        "indice de morosidad": "imor_cuadro",
    }

    @classmethod
    def _build_index(cls):
        """Construye un índice simple de palabras clave a IDs de sección."""
        for section_id, config in cls._sections.items():
            # Extraer palabras clave del título e ID
            title_words = config["title"].lower().split()
            id_words = section_id.replace("_", " ").lower().split()

            keywords = set(title_words + id_words)
            # Filtrar palabras comunes irrelevantes
            keywords.discard("cuadro")
            keywords.discard("grafica")
            keywords.discard("evolucion")

            for kw in keywords:
                if len(kw) < 3: continue
                if kw not in cls._keyword_map:
                    cls._keyword_map[kw] = []
                cls._keyword_map[kw].append(section_id)

    @classmethod
    def get_section_config(cls, section_id: str) -> Optional[Dict[str, Any]]:
        cls.initialize()
        return cls._sections.get(section_id)

    @classmethod
    def disambiguate(cls, query: str) -> AmbiguityResult:
        cls.initialize()
        query_lower = query.lower().strip()

        # 0. Check explicit aliases FIRST (highest priority)
        # BA-P0-004: Check both full query and individual words for aliases
        if query_lower in cls._explicit_aliases:
            return AmbiguityResult(is_ambiguous=False, options=[], resolved_id=cls._explicit_aliases[query_lower])

        # Also check if query contains any explicit alias as a word
        for alias, section_id in cls._explicit_aliases.items():
            if alias in query_lower.split():
                return AmbiguityResult(is_ambiguous=False, options=[], resolved_id=section_id)

        # 1. Búsqueda Exacta por ID
        if query_lower in cls._sections:
            return AmbiguityResult(is_ambiguous=False, options=[], resolved_id=query_lower)

        # 2. Búsqueda por palabras clave
        query_words = query_lower.split()
        candidates = set()
        
        # Estrategia: Intersección de candidatos. 
        # Si usuario dice "cartera comercial", buscamos IDs que tengan AMBAS.
        first_word = True
        for word in query_words:
            if len(word) < 3: continue
            
            # Buscar coincidencias directas o fuzzy
            word_candidates = set()
            
            # Match directo en mapa
            if word in cls._keyword_map:
                word_candidates.update(cls._keyword_map[word])
            
            # Fuzzy match en mapa keys
            matches = difflib.get_close_matches(word, cls._keyword_map.keys(), n=3, cutoff=0.8)
            for match in matches:
                word_candidates.update(cls._keyword_map[match])
            
            if not word_candidates:
                continue
                
            if first_word:
                candidates = word_candidates
                first_word = False
            else:
                candidates = candidates.intersection(word_candidates)

        if not candidates:
            # Fallback: devolver métricas populares
            return AmbiguityResult(
                is_ambiguous=True, 
                options=["Cartera Total", "IMOR", "ICOR", "Captación"],
                missing_dimension="tema desconocido"
            )

        # 3. Filtrar candidatos para preferir "cuadro" sobre "grafica" por defecto
        # (Ya que la UI de dashboards suele combinar ambos)
        preferred_candidates = [c for c in candidates if "_cuadro" in c]
        if not preferred_candidates:
            preferred_candidates = list(candidates)

        if len(preferred_candidates) == 1:
            return AmbiguityResult(is_ambiguous=False, options=[], resolved_id=preferred_candidates[0])

        # 4. Si hay múltiples, aplicar heurística de scoring
        if len(preferred_candidates) > 1:
            # Scoring: contar cuántas palabras del query están en el ID
            def score_candidate(cid):
                id_lower = cid.replace("_", " ").lower()
                score = 0
                for word in query_words:
                    if len(word) < 3:
                        continue
                    if word in id_lower:
                        score += 1
                # Bonus: si el ID es más corto (más genérico), ligero bonus
                score += (100 - len(cid)) / 1000.0
                return score

            # Ordenar por score descendente
            scored = sorted(preferred_candidates, key=score_candidate, reverse=True)
            best = scored[0]

            # Si el mejor tiene score significativamente mayor, elegirlo
            if len(scored) >= 2:
                best_score = score_candidate(scored[0])
                second_score = score_candidate(scored[1])
                if best_score > second_score:
                    return AmbiguityResult(is_ambiguous=False, options=[], resolved_id=best)

            # Si los scores son iguales, es realmente ambiguo
            if len(scored) >= 2 and score_candidate(scored[0]) == score_candidate(scored[1]):
                pass  # Caer a la sección de ambigüedad
            else:
                return AmbiguityResult(is_ambiguous=False, options=[], resolved_id=best)

        # 5. Si llegamos aquí, realmente es ambiguo
        options_readable = [cls._sections[cid]["title"] for cid in preferred_candidates]

        return AmbiguityResult(
            is_ambiguous=True,
            options=list(set(options_readable)),
            missing_dimension="especificidad"
        )
