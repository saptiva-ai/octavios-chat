"""
Entity Consistency Auditor for COPILOTO_414.

Validates entity consistency across document:
- Client name variations (fuzzy matching)
- Currency symbol consistency
- Brand name standardization
- Key term consistency

Phase 4 of 5-phase plan (plan_summary.txt)
"""

from typing import List, Dict, Any, Tuple, Set
from uuid import uuid4
import structlog
from rapidfuzz import fuzz

from ...schemas.models import PageFragment
from ...schemas.audit_message import Finding, Location, Evidence

logger = structlog.get_logger(__name__)


def _best_match(token: str, canonical: List[str]) -> Tuple[int, str]:
    """
    Find best fuzzy match for token against canonical list.

    Args:
        token: Text to match
        canonical: List of canonical names

    Returns:
        (best_score, best_match_name) tuple
    """
    if not canonical:
        return 0, ""

    best_score = 0
    best_match = canonical[0]

    for candidate in canonical:
        score = fuzz.token_set_ratio(token, candidate)
        if score > best_score:
            best_score = score
            best_match = candidate

    return best_score, best_match


def extract_client_name_candidates(text: str, max_words: int = 5) -> List[str]:
    """
    Extract potential client name candidates from text.

    Uses heuristics:
    - Words starting with uppercase or digits
    - Consecutive titlecase words (2-5 words)
    - Common business suffixes (S.A., LLC, etc.)

    Args:
        text: Text to analyze
        max_words: Maximum words in candidate name

    Returns:
        List of candidate names
    """
    if not text or len(text) > 5000:
        return []

    words = text.split()
    candidates = []

    # Look for consecutive titlecase words or numbers
    i = 0
    while i < len(words):
        word_clean = words[i].strip(",.;:()")

        # Check if word starts with uppercase or digit (for "414 Capital")
        if word_clean and (word_clean[0].isupper() or word_clean[0].isdigit()):
            # Start of potential name
            candidate_words = []
            j = i

            while j < len(words) and j < i + max_words:
                word = words[j].strip(",.;:()")

                # Accept if:
                # - Starts with uppercase or digit
                # - Is a common connector word
                if word and (word[0].isupper() or word[0].isdigit() or word.lower() in ["de", "del", "la", "y", "e"]):
                    # Don't include trailing connectors
                    if word.lower() not in ["de", "del", "la", "y", "e"] or j + 1 < len(words):
                        candidate_words.append(word)
                        j += 1
                    else:
                        break
                else:
                    break

            # Filter out trailing connectors
            while candidate_words and candidate_words[-1].lower() in ["de", "del", "la", "y", "e"]:
                candidate_words.pop()

            if len(candidate_words) >= 2:  # At least 2 words for a company name
                candidate = " ".join(candidate_words)
                if len(candidate) >= 5:  # Minimum length
                    candidates.append(candidate)

            i = j if j > i else i + 1
        else:
            i += 1

    return candidates


def validate_client_names(
    fragments: List[PageFragment],
    canonical_names: List[str],
    tolerance: int = 90
) -> Tuple[List[Dict[str, Any]], Set[int]]:
    """
    Validate client name consistency across document.

    Args:
        fragments: Document fragments
        canonical_names: List of canonical client names
        tolerance: Minimum fuzzy match score (0-100)

    Returns:
        (violations, pages_with_client) tuple
            - violations: List of name mismatches
            - pages_with_client: Set of pages where canonical name appears
    """
    violations = []
    pages_with_client = set()
    variants_found = {}  # {variant: [pages]}

    for frag in fragments:
        text = (frag.text or "").strip()
        if not text:
            continue

        # Extract candidate names
        candidates = extract_client_name_candidates(text)

        for candidate in candidates:
            best_score, best_match = _best_match(candidate, canonical_names)

            # Check if it's a good match
            if best_score >= tolerance:
                pages_with_client.add(frag.page)
            elif 60 <= best_score < tolerance:
                # Potential variation that doesn't meet tolerance
                if candidate not in variants_found:
                    variants_found[candidate] = []
                variants_found[candidate].append(frag.page)

    # Create violations for variants
    for variant, pages in variants_found.items():
        best_score, best_match = _best_match(variant, canonical_names)

        violations.append({
            "variant": variant,
            "canonical": best_match,
            "score": best_score,
            "pages": sorted(list(set(pages))),
            "issue": f"Posible variación no autorizada del nombre del cliente: «{variant}» "
                     f"(similitud: {best_score}% con «{best_match}»)"
        })

    return violations, pages_with_client


def validate_currencies(
    fragments: List[PageFragment],
    canonical_currencies: List[str],
    canonical_symbols: List[str]
) -> List[Dict[str, Any]]:
    """
    Validate currency consistency.

    Args:
        fragments: Document fragments
        canonical_currencies: List of allowed currency codes (e.g., ["MXN", "USD"])
        canonical_symbols: List of allowed currency symbols (e.g., ["$", "US$"])

    Returns:
        List of currency violations
    """
    violations = []
    # Placeholder for currency validation logic
    # This would require more sophisticated parsing
    # For now, we'll keep it simple

    return violations


async def audit_entity_consistency(
    fragments: List[PageFragment],
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit entity consistency across document.

    Args:
        fragments: Document fragments with text
        config: Policy configuration (entity_consistency section)

    Returns:
        (findings, summary) tuple
            - findings: List of Finding objects for inconsistencies
            - summary: Aggregated metrics
                - pages_with_client: List[int]
                - variants_found: int
                - client_name_compliance_rate: float

    Example:
        findings, summary = await audit_entity_consistency(
            fragments=fragments,
            config={
                "entity_consistency": {
                    "enabled": True,
                    "entities": {
                        "client_names": {
                            "canonical": ["414 Capital", "Banamex"],
                            "tolerance": 90
                        }
                    },
                    "severity_name_mismatch": "high"
                }
            }
        )
    """
    findings: List[Finding] = []
    entity_config = config.get("entity_consistency", {})

    # Configuration
    client_names_config = entity_config.get("entities", {}).get("client_names", {})
    canonical_names = client_names_config.get("canonical", [])
    tolerance = client_names_config.get("tolerance", 90)
    severity_name = entity_config.get("severity_name_mismatch", "high")

    logger.info(
        "Starting entity consistency audit",
        canonical_names=canonical_names,
        tolerance=tolerance
    )

    # Validate client names
    violations, pages_with_client = validate_client_names(
        fragments=fragments,
        canonical_names=canonical_names,
        tolerance=tolerance
    )

    # Create findings for each violation
    for violation in violations:
        findings.append(
            Finding(
                id=f"entity-consistency-{uuid4().hex[:8]}",
                category="entity_consistency",
                rule="client_name_consistency",
                issue=violation["issue"],
                severity=severity_name,
                location=Location(
                    page=violation["pages"][0] if violation["pages"] else 1,
                    bbox=None,
                    fragment_id=None,
                    text_snippet=None
                ),
                suggestion=f"Usar la forma canónica: «{violation['canonical']}»",
                evidence=[
                    Evidence(
                        kind="metric",
                        data={
                            "variant_found": violation["variant"],
                            "canonical_name": violation["canonical"],
                            "similarity_score": violation["score"],
                            "pages": violation["pages"],
                            "threshold": tolerance
                        }
                    )
                ]
            )
        )

    # Generate summary
    summary = {
        "pages_with_client": sorted(list(pages_with_client)),
        "variants_found": len(violations),
        "canonical_names": canonical_names,
        "tolerance_threshold": tolerance,
        "client_name_compliance_rate": 1.0 - (len(violations) / max(len(fragments), 1))
    }

    logger.info(
        "Entity consistency audit completed",
        findings=len(findings),
        variants_found=len(violations),
        pages_with_client=len(pages_with_client)
    )

    return findings, summary
