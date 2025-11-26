"""
Reports Package - PDF and Markdown report generation for COPILOTO_414.

Contains:
- report_generator: PDF report generation with ReportLab
- summary_formatter: Executive summary in Markdown format
"""

from .report_generator import generate_audit_report_pdf
from .summary_formatter import generate_executive_summary, format_executive_summary_as_markdown

__all__ = [
    "generate_audit_report_pdf",
    "generate_executive_summary",
    "format_executive_summary_as_markdown",
]
