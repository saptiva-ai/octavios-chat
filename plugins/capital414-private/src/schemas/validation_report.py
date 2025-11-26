"""
ValidationReport model for COPILOTO_414 Plugin.

Simplified Pydantic model (no database dependencies) for report generation.
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from uuid import uuid4


class ValidationReport(BaseModel):
    """
    Validation report data structure for PDF/markdown generation.

    This is a Pydantic model (not a database model) designed for
    stateless report generation in the MCP plugin.
    """

    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str = Field(..., description="Document ID that was validated")
    user_id: str = Field(default="system", description="User who requested validation")

    # Validation metadata
    job_id: str = Field(default_factory=lambda: str(uuid4()), description="Unique validation job ID")
    status: str = Field(default="completed", description="completed | error")
    client_name: Optional[str] = Field(None, description="Client name used for validation")

    # Auditor configuration
    auditors_enabled: Dict[str, bool] = Field(
        default_factory=lambda: {
            "disclaimer": True,
            "format": True,
            "typography": True,
            "grammar": True,
            "logo": True,
            "color_palette": True,
            "entity_consistency": True,
            "semantic_consistency": True,
        },
        description="Which auditors were enabled for this validation"
    )

    # Results
    findings: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of Finding objects (serialized)"
    )

    summary: Dict[str, Any] = Field(
        default_factory=dict,
        description="Summary metrics (total_findings, coverage, findings_by_severity)"
    )

    # Optional attachments
    attachments: Optional[Dict[str, Any]] = Field(
        None,
        description="Optional attachments like overlay_pdf"
    )

    # Error tracking
    error: Optional[str] = Field(None, description="Error message if status=error")

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    validation_duration_ms: Optional[int] = Field(None, description="How long validation took")

    def get_findings_summary_for_prompt(self) -> str:
        """Format findings summary for LLM context injection."""
        if not self.findings:
            return "Este documento no tiene findings de validación 414."

        total = len(self.findings)
        by_severity = self.summary.get("findings_by_severity", {})

        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)
        medium_count = by_severity.get("medium", 0)

        parts = [f"Este documento tiene {total} finding{'s' if total > 1 else ''} de validación 414:"]

        if critical_count > 0:
            parts.append(f"{critical_count} crítico{'s' if critical_count > 1 else ''}")
        if high_count > 0:
            parts.append(f"{high_count} alto{'s' if high_count > 1 else ''}")
        if medium_count > 0:
            parts.append(f"{medium_count} medio{'s' if medium_count > 1 else ''}")

        critical_findings = [f for f in self.findings if f.get("severity") == "critical"]
        if critical_findings:
            issues = []
            for finding in critical_findings[:2]:
                issue = finding.get("issue", "")
                page = finding.get("location", {}).get("page")
                if page:
                    issues.append(f"{issue} (página {page})")
                else:
                    issues.append(issue)
            if issues:
                parts.append(f"Principales problemas: {', '.join(issues)}")

        return " - ".join(parts)
