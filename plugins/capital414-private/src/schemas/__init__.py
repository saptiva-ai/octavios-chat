"""
Schemas Package - Data Transfer Objects for COPILOTO_414.

Contains Pydantic models for:
- Audit findings and reports
- Page fragments and document models
- Message payloads
"""

from .audit_message import (
    Finding,
    Location,
    Evidence,
    AuditSummary,
    AuditMessagePayload,
    AuditAction,
    AuditContextSummary,
    ValidationReportResponse,
)
from .audit import AuditReportResponse, AuditFinding, AuditStats
from .models import PageFragment, PageContent

__all__ = [
    # Audit Message
    "Finding",
    "Location",
    "Evidence",
    "AuditSummary",
    "AuditMessagePayload",
    "AuditAction",
    "AuditContextSummary",
    "ValidationReportResponse",
    # Audit Report
    "AuditReportResponse",
    "AuditFinding",
    "AuditStats",
    # Models
    "PageFragment",
    "PageContent",
]
