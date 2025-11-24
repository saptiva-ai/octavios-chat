"""
Semantic Consistency Auditor for Document Audit.

Validates semantic consistency across document sections:
- Cross-section coherence (Resumen vs Conclusiones)
- Numeric consistency (key figures repeated across sections)
- Message alignment using embeddings + cosine similarity

Phase 5 of 5-phase plan (plan_summary.txt) - FINAL PHASE
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from uuid import uuid4
import structlog

from ..models.document import PageFragment
from ..schemas.audit_message import Finding, Location, Evidence

logger = structlog.get_logger(__name__)

# Regex to capture numeric patterns
NUM_CAPTURE = re.compile(r"\b(\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d{2,})?\b")


def extract_numbers_from_text(text: str) -> List[str]:
    """
    Extract all numeric values from text.

    Args:
        text: Text to analyze

    Returns:
        List of number strings (e.g., ["1,234.56", "99.5"])
    """
    matches = NUM_CAPTURE.findall(text)
    # Extract just the number part (first group)
    numbers = [m if isinstance(m, str) else m[0] for m in matches]
    return numbers


def normalize_number(num_str: str) -> str:
    """
    Normalize number string for comparison.

    Removes separators to compare numeric value.

    Args:
        num_str: Number string (e.g., "1,234.56")

    Returns:
        Normalized string (e.g., "123456")
    """
    # Remove common separators
    normalized = num_str.replace(",", "").replace(".", "")
    return normalized


def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """
    Calculate cosine similarity between two vectors.

    Args:
        vec_a: First vector
        vec_b: Second vector

    Returns:
        Cosine similarity (0.0 to 1.0)
    """
    if len(vec_a) != len(vec_b):
        raise ValueError("Vectors must have same dimension")

    if len(vec_a) == 0:
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    magnitude_a = sum(a ** 2 for a in vec_a) ** 0.5
    magnitude_b = sum(b ** 2 for b in vec_b) ** 0.5

    if magnitude_a == 0.0 or magnitude_b == 0.0:
        return 0.0

    return dot_product / (magnitude_a * magnitude_b)


async def _embed(text: str) -> List[float]:
    """
    Generate embedding vector for text.

    TODO: Integrate with Saptiva Embeddings API.
    Current implementation is a placeholder for testing.

    Args:
        text: Text to embed

    Returns:
        Embedding vector (768-dimensional)
    """
    # PLACEHOLDER: In production, call Saptiva Embeddings API
    # For now, return a simple hash-based mock vector
    import hashlib

    # Create deterministic but varied vector based on text
    hash_val = int(hashlib.md5(text.encode()).hexdigest(), 16)

    # Generate 768-dimensional vector from hash
    vector = []
    for i in range(768):
        # Use different parts of hash for variety
        val = ((hash_val >> (i % 128)) % 1000) / 1000.0
        vector.append(val)

    return vector


def extract_sections_from_fragments(
    fragments: List[PageFragment],
    section_titles: List[str],
    heading_threshold: int = 14
) -> Dict[str, str]:
    """
    Extract text by section based on headings.

    Args:
        fragments: Document fragments
        section_titles: List of section titles to look for (lowercase)
        heading_threshold: Minimum font size to consider as heading

    Returns:
        Dictionary {section_title: concatenated_text}
    """
    sections = {}
    current_section = None

    for frag in fragments:
        text = (frag.text or "").strip()
        if not text:
            continue

        # Check if this is a heading
        font_size = getattr(frag, "font_size", 0)
        is_heading = font_size and font_size >= heading_threshold and len(text) < 100

        if is_heading:
            # Check if matches any target section
            text_lower = text.lower()
            for title in section_titles:
                if title.lower() in text_lower:
                    current_section = title.lower()
                    if current_section not in sections:
                        sections[current_section] = []
                    break
        elif current_section:
            # Add text to current section
            sections[current_section].append(text)

    # Concatenate text for each section
    for key in sections:
        sections[key] = " ".join(sections[key])

    return sections


async def audit_semantic_consistency(
    fragments: List[PageFragment],
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit semantic consistency across document sections.

    Args:
        fragments: Document fragments with text
        config: Policy configuration (semantic_consistency section)

    Returns:
        (findings, summary) tuple
            - findings: List of Finding objects for inconsistencies
            - summary: Aggregated metrics
                - sections_found: List[str]
                - comparisons_made: int
                - similarities: Dict[str, float]
                - numeric_discrepancies: int

    Example:
        findings, summary = await audit_semantic_consistency(
            fragments=fragments,
            config={
                "semantic_consistency": {
                    "enabled": True,
                    "min_section_len": 200,
                    "section_titles": ["Resumen Ejecutivo", "Conclusiones"],
                    "similarity_threshold": 0.80,
                    "severity": "medium"
                }
            }
        )
    """
    findings: List[Finding] = []
    semantic_config = config.get("semantic_consistency", {})

    # Configuration
    section_titles = semantic_config.get("section_titles", [
        "Resumen Ejecutivo",
        "Metodología",
        "Resultados",
        "Conclusiones"
    ])
    similarity_threshold = semantic_config.get("similarity_threshold", 0.80)
    min_section_len = semantic_config.get("min_section_len", 200)
    severity = semantic_config.get("severity", "medium")

    logger.info(
        "Starting semantic consistency audit",
        section_titles=section_titles,
        similarity_threshold=similarity_threshold
    )

    # Extract sections
    sections = extract_sections_from_fragments(
        fragments=fragments,
        section_titles=section_titles
    )

    logger.info(
        "Sections extracted",
        sections_found=list(sections.keys()),
        section_lengths={k: len(v) for k, v in sections.items()}
    )

    # Filter sections by minimum length
    sections = {k: v for k, v in sections.items() if len(v) >= min_section_len}

    similarities = {}
    comparisons_made = 0

    # Compare Resumen Ejecutivo vs Conclusiones
    if "resumen ejecutivo" in sections and "conclusiones" in sections:
        resumen_text = sections["resumen ejecutivo"]
        conclusiones_text = sections["conclusiones"]

        # Generate embeddings
        resumen_vec = await _embed(resumen_text)
        conclusiones_vec = await _embed(conclusiones_text)

        # Calculate similarity
        similarity = cosine_similarity(resumen_vec, conclusiones_vec)
        similarities["resumen_vs_conclusiones"] = similarity
        comparisons_made += 1

        logger.info(
            "Compared Resumen vs Conclusiones",
            similarity=round(similarity, 3),
            threshold=similarity_threshold
        )

        if similarity < similarity_threshold:
            findings.append(
                Finding(
                    id=f"semantic-consistency-{uuid4().hex[:8]}",
                    category="semantic_consistency",
                    rule="semantic_consistency",
                    issue=f"Baja similitud entre Resumen Ejecutivo y Conclusiones (similitud coseno: {similarity:.2f})",
                    severity=severity,
                    location=Location(
                        page=1,
                        bbox=None,
                        fragment_id=None,
                        text_snippet=None
                    ),
                    suggestion="Alinear conclusiones con el resumen o justificar cambios en mensaje.",
                    evidence=[
                        Evidence(
                            kind="metric",
                            data={
                                "cosine_similarity": round(similarity, 3),
                                "threshold": similarity_threshold,
                                "resumen_length": len(resumen_text),
                                "conclusiones_length": len(conclusiones_text)
                            }
                        )
                    ]
                )
            )

        # Compare numeric consistency
        nums_resumen = set(extract_numbers_from_text(resumen_text))
        nums_conclusiones = set(extract_numbers_from_text(conclusiones_text))

        # Normalize for comparison
        nums_resumen_normalized = {normalize_number(n) for n in nums_resumen}
        nums_conclusiones_normalized = {normalize_number(n) for n in nums_conclusiones}

        # Find numbers in resumen missing from conclusiones
        missing_numbers = nums_resumen - nums_conclusiones

        # Also check normalized versions
        missing_normalized = nums_resumen_normalized - nums_conclusiones_normalized

        if len(missing_numbers) > 0 or len(missing_normalized) > 3:
            findings.append(
                Finding(
                    id=f"semantic-numeric-{uuid4().hex[:8]}",
                    category="semantic_consistency",
                    rule="numeric_reference_consistency",
                    issue=f"Cifras mencionadas en el resumen no aparecen en conclusiones: {list(missing_numbers)[:5]}",
                    severity=severity,
                    location=Location(
                        page=1,
                        bbox=None,
                        fragment_id=None,
                        text_snippet=None
                    ),
                    suggestion="Revisar que las cifras clave se reflejen consistentemente en conclusiones.",
                    evidence=[
                        Evidence(
                            kind="metric",
                            data={
                                "missing_in_conclusions": list(missing_numbers)[:10],
                                "numbers_in_resumen": list(nums_resumen)[:10],
                                "numbers_in_conclusiones": list(nums_conclusiones)[:10]
                            }
                        )
                    ]
                )
            )

    # Generate summary
    summary = {
        "sections_found": list(sections.keys()),
        "comparisons_made": comparisons_made,
        "similarities": similarities,
        "numeric_discrepancies": sum(1 for f in findings if f.rule == "numeric_reference_consistency"),
        "semantic_discrepancies": sum(1 for f in findings if f.rule == "semantic_consistency"),
    }

    logger.info(
        "Semantic consistency audit completed",
        findings=len(findings),
        comparisons=comparisons_made,
        sections_found=len(sections)
    )

    return findings, summary
