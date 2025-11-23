"""
Utility helpers to normalize audit findings into a presentation-agnostic payload.
"""

from typing import Any, Dict, List, Optional

from ..schemas.audit import AuditReportResponse, AuditStats, AuditFinding

# Whitelist of technical terms to ignore for low-severity noise
TECHNICAL_WHITELIST = {
    "genai",
    "deployment",
    "stack",
    "on-prem",
    "on prem",
    "frida",
    "k8s",
    "billing",
    "endpoint",
    "audit",
}


def _should_filter_low_noise(message: str, severity: str) -> bool:
    """
    Return True if the finding should be filtered out as low-severity technical jargon.
    """
    if severity != "low":
        return False
    msg_lower = message.lower()
    return any(term in msg_lower for term in TECHNICAL_WHITELIST)


def build_audit_report_response(
    *,
    doc_name: str,
    findings: List[Dict[str, Any]],
    summary: Optional[Any] = None,
    actions: Optional[List[str]] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditReportResponse:
    """
    Normalize raw findings into AuditReportResponse with filtering and grouping.
    """
    filtered: List[AuditFinding] = []
    for f in findings or []:
        severity = str(f.get("severity", "")).lower() or "low"
        message = (
            f.get("message")
            or f.get("issue")
            or f.get("description")
            or ""
        )

        if _should_filter_low_noise(message, severity):
            continue

        category = f.get("category") or "uncategorized"
        normalized = AuditFinding(
            id=f.get("id"),
            category=category,
            severity=severity,
            message=message,
            page=(f.get("location") or {}).get("page") if isinstance(f.get("location"), dict) else f.get("page"),
            suggestion=f.get("suggestion"),
            rule=f.get("rule"),
            raw=f or {},
        )
        filtered.append(normalized)

    # Stats
    stats_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    categories: Dict[str, List[AuditFinding]] = {}

    for finding in filtered:
        sev = finding.severity.lower()
        if sev not in stats_counts:
            sev = "low"
        stats_counts[sev] += 1
        categories.setdefault(finding.category, []).append(finding)

    total = sum(stats_counts.values())
    stats = AuditStats(
        critical=stats_counts["critical"],
        high=stats_counts["high"],
        medium=stats_counts["medium"],
        low=stats_counts["low"],
        total=total,
    )

    # Build response
    resp = AuditReportResponse(
        doc_name=doc_name,
        stats=stats,
        categories=categories,
        actions=actions or [],
        metadata=metadata or {},
    )

    # Preserve summary in metadata if provided
    if summary is not None:
        resp.metadata["summary"] = summary

    return resp

