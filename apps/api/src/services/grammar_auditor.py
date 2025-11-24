"""
Grammar auditor for Document Audit.

Runs LanguageTool on document pages to detect spelling and grammar issues.
"""

from __future__ import annotations

from typing import Dict, Any, List, Tuple
from uuid import uuid4

import structlog

from ..models.document import Document
from ..schemas.audit_message import Finding, Location, Evidence
from .languagetool_client import languagetool_client

logger = structlog.get_logger(__name__)


async def audit_grammar(
    document: Document,
    config: Dict[str, Any],
) -> Tuple[List[Finding], Dict[str, Any]]:
    """
    Audit document text using LanguageTool.

    Args:
        document: Document with extracted pages
        config: Compliance configuration (grammar section expected)

    Returns:
        Tuple of (findings, summary)
    """
    grammar_config = (config or {}).get("grammar", {}) or {}

    if not grammar_config.get("enabled", True):
        logger.info("Grammar audit disabled via configuration")
        return [], {
            "enabled": False,
            "pages_analyzed": 0,
            "total_issues": 0,
            "grammar_issues": 0,
            "spelling_issues": 0,
        }

    language = grammar_config.get("language", "es")
    severity_config = grammar_config.get("severity", {})

    # Handle both dict and string severity formats
    if isinstance(severity_config, dict):
        spelling_severity = severity_config.get("spelling", "low")
        grammar_severity = severity_config.get("grammar", "medium")
    else:
        # If severity is a string, use it for both
        default_severity = severity_config if isinstance(severity_config, str) else "low"
        spelling_severity = default_severity
        grammar_severity = default_severity
    max_issues_per_page = grammar_config.get("max_issues_per_page", 30)
    top_examples = grammar_config.get("top_examples", 5)
    disabled_rules = grammar_config.get("disabled_rules")

    findings: List[Finding] = []
    pages_with_issues: set[int] = set()
    example_highlights: List[Dict[str, Any]] = []

    total_spelling = 0
    total_grammar = 0
    pages_analyzed = 0

    for page_content in document.pages or []:
        text = (page_content.text_md or "").strip()
        if not text:
            continue

        pages_analyzed += 1
        page_number = page_content.page

        try:
            response = await languagetool_client.check_text(
                text,
                language=language,
                enabled_only=False,
            )

            # Apply additional rule filtering if configured
            if disabled_rules:
                filtered_matches = [
                    match
                    for match in response.get("matches", [])
                    if match.get("rule", {}).get("id") not in set(disabled_rules)
                ]
                response["matches"] = filtered_matches

            spelling, grammar = languagetool_client.parse_matches(response)

        except Exception as exc:
            logger.error(
                "Grammar auditor failed for page",
                error=str(exc),
                page=page_number,
                exc_info=True,
            )
            # Continue with next page (do not fail entire validation)
            continue

        if not spelling and not grammar:
            continue

        pages_with_issues.add(page_number)

        # Limit issues per page to avoid overwhelming output
        spelling = spelling[:max_issues_per_page]
        grammar = grammar[:max_issues_per_page]

        total_spelling += len(spelling)
        total_grammar += len(grammar)

        for entry in spelling:
            finding_id = f"spelling-{page_number}-{uuid4().hex[:6]}"
            snippet = (entry.get("span") or "").strip()
            suggestions = entry.get("suggestions", [])
            suggestion = suggestions[0] if suggestions else None

            findings.append(
                Finding(
                    id=finding_id,
                    category="linguistic",
                    rule=entry.get("rule", "spelling"),
                    issue=f"Posible error ortográfico: «{snippet}»",
                    severity=spelling_severity,
                    location=Location(
                        page=page_number,
                        bbox=None,
                        fragment_id=None,
                        text_snippet=snippet,
                    ),
                    suggestion=suggestion,
                    evidence=[
                        Evidence(
                            kind="text",
                            data={
                                "snippet": snippet,
                                "suggestions": entry.get("suggestions", []),
                                "rule": entry.get("rule"),
                            },
                        )
                    ],
                )
            )

            if len(example_highlights) < top_examples:
                example_highlights.append(
                    {
                        "type": "spelling",
                        "page": page_number,
                        "text": snippet,
                        "suggestion": suggestion,
                    }
                )

        for entry in grammar:
            finding_id = f"grammar-{page_number}-{uuid4().hex[:6]}"
            snippet = (entry.get("span") or "").strip()
            suggestions = entry.get("suggestions", [])
            suggestion = suggestions[0] if suggestions else None
            rule_id = entry.get("rule", "grammar")
            message = entry.get("explain") or "Revisar construcción gramatical."

            findings.append(
                Finding(
                    id=finding_id,
                    category="linguistic",
                    rule=rule_id,
                    issue=f"Posible error gramatical: {message}",
                    severity=grammar_severity,
                    location=Location(
                        page=page_number,
                        bbox=None,
                        fragment_id=None,
                        text_snippet=snippet,
                    ),
                    suggestion=suggestion,
                    evidence=[
                        Evidence(
                            kind="text",
                            data={
                                "snippet": snippet,
                                "suggestions": entry.get("suggestions", []),
                                "rule": rule_id,
                                "message": message,
                            },
                        )
                    ],
                )
            )

            if len(example_highlights) < top_examples:
                example_highlights.append(
                    {
                        "type": "grammar",
                        "page": page_number,
                        "text": snippet,
                        "suggestion": suggestion,
                        "rule": rule_id,
                    }
                )

    summary = {
        "enabled": True,
        "language": language,
        "pages_analyzed": pages_analyzed,
        "pages_with_issues": sorted(pages_with_issues),
        "total_issues": total_spelling + total_grammar,
        "spelling_issues": total_spelling,
        "grammar_issues": total_grammar,
        "examples": example_highlights,
    }

    logger.info(
        "Grammar audit completed",
        pages_analyzed=pages_analyzed,
        total_issues=summary["total_issues"],
        spelling=total_spelling,
        grammar=total_grammar,
    )

    return findings, summary
