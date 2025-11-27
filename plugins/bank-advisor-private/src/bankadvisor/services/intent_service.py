import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import difflib

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
