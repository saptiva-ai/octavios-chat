"""
Audit Message Schemas for COPILOTO_414.

Defines the structure of audit results and findings.
"""

from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field


Category = Literal[
    "compliance", "format", "typography", "logo",
    "color_palette", "entity_consistency", "semantic_consistency", "linguistic"
]
Severity = Literal["low", "medium", "high", "critical"]


class Location(BaseModel):
    """Location of a finding within the document."""

    page: int = Field(..., description="Page number (1-indexed)")
    bbox: Optional[List[float]] = Field(None, description="Bounding box [x0, y0, x1, y1]")
    fragment_id: Optional[str] = Field(None, description="Fragment ID from extracted page fragments")
    text_snippet: Optional[str] = Field(None, description="Excerpt of text related to the finding")


class Evidence(BaseModel):
    """Supporting evidence for a finding."""

    kind: Literal["text", "image", "metric", "rule"] = Field(..., description="Evidence type")
    data: Dict[str, Any] = Field(default_factory=dict, description="Flexible evidence payload")


class Finding(BaseModel):
    """Validation finding surfaced by COPILOTO_414 auditors."""

    id: str = Field(..., description="Unique finding identifier")
    category: Category = Field(..., description="Finding category")
    rule: str = Field(..., description="Rule or check that triggered the finding")
    issue: str = Field(..., description="Human-readable description of the issue")
    severity: Severity = Field(..., description="Finding severity")
    location: Optional[Location] = Field(None, description="Location metadata")
    suggestion: Optional[str] = Field(None, description="Suggested remediation for the issue")
    evidence: List[Evidence] = Field(default_factory=list, description="Supporting evidence entries")


class AuditAction(BaseModel):
    """Actions available from audit message card."""

    action: Literal["view_full", "re_audit", "export_pdf", "ignore"] = Field(
        ..., description="Action identifier"
    )
    label: str = Field(..., description="Button label for UI")
    icon: Optional[str] = Field(None, description="Icon name (optional)")
    enabled: bool = Field(default=True, description="Whether action is available")


class AuditSummary(BaseModel):
    """Executive summary of audit findings."""

    total_findings: int = Field(..., description="Total number of findings")
    findings_by_severity: Dict[Severity, int] = Field(..., description="Counts by severity level")
    findings_by_category: Dict[Category, int] = Field(..., description="Counts by category")
    disclaimer_coverage: Optional[float] = Field(None, ge=0.0, le=1.0, description="Disclaimer coverage")
    logo_detected: Optional[bool] = Field(None, description="Whether logo was found")
    total_pages: int = Field(..., description="Total pages in document")
    fonts_used: List[str] = Field(default_factory=list, description="Top fonts detected")
    colors_detected: List[str] = Field(default_factory=list, description="Dominant colors detected")
    grammar_issues: int = Field(default=0, description="Total grammar issues detected")
    spelling_issues: int = Field(default=0, description="Total spelling issues detected")
    pages_with_grammar_issues: List[int] = Field(default_factory=list, description="Pages with grammar issues")
    image_overview: Optional[Dict[str, Any]] = Field(default=None, description="Summary of image proportions")
    policy_id: str = Field(..., description="Policy ID used for validation")
    policy_name: str = Field(..., description="Human-readable policy name")
    validation_duration_ms: int = Field(..., description="Validation duration in milliseconds")


class AuditMessagePayload(BaseModel):
    """Complete payload for audit result."""

    validation_report_id: str = Field(..., description="Validation report ID")
    job_id: str = Field(..., description="Unique validation job ID")
    status: Literal["completed", "error"] = Field(..., description="Validation status")
    document_id: str = Field(..., description="Document that was audited")
    filename: str = Field(..., description="Original filename for display")
    summary: AuditSummary = Field(..., description="Audit summary metrics")
    sample_findings: List[Finding] = Field(default_factory=list, description="Preview of top findings")
    actions: List[AuditAction] = Field(default_factory=list, description="Available actions")
    error_message: Optional[str] = Field(None, description="Error message if validation failed")


class AuditContextSummary(BaseModel):
    """Lightweight summary for LLM context injection."""

    document_filename: str
    total_findings: int
    critical_count: int
    high_count: int
    medium_count: int
    critical_issues: List[str] = Field(default_factory=list, max_length=2)

    def to_prompt_text(self) -> str:
        """Format as concise text for prompt injection."""
        parts = [f"[Validación 414: {self.document_filename}]"]

        findings_desc = []
        if self.critical_count > 0:
            findings_desc.append(f"{self.critical_count} crítico{'s' if self.critical_count > 1 else ''}")
        if self.high_count > 0:
            findings_desc.append(f"{self.high_count} alto{'s' if self.high_count > 1 else ''}")
        if self.medium_count > 0:
            findings_desc.append(f"{self.medium_count} medio{'s' if self.medium_count > 1 else ''}")

        parts.append(f"- {self.total_findings} hallazgos: {', '.join(findings_desc)}")

        for issue in self.critical_issues:
            parts.append(f"- {issue}")

        return "\n".join(parts)


class ValidationReportResponse(BaseModel):
    """Response schema for validation coordinator."""

    job_id: str = Field(..., description="Unique validation job ID")
    status: str = Field(..., description="completed | error")
    findings: List[Finding] = Field(default_factory=list, description="All validation findings")
    summary: Dict[str, Any] = Field(default_factory=dict, description="Summary metrics")
    attachments: Dict[str, Any] = Field(default_factory=dict, description="Optional attachments")
    fragments_count: int = Field(default=0, description="Number of fragments analyzed")
