"""
Integration tests for audit_file tool.

Tests Document Audit compliance validation via MCP.
"""

import pytest
from unittest.mock import AsyncMock, Mock, patch, MagicMock
from pathlib import Path
from fastmcp import FastMCP

from src.mcp.server import audit_file
from src.models.document import Document, DocumentStatus


@pytest.fixture
def mock_document():
    """Create a mock document."""
    doc = Mock(spec=Document)
    doc.id = "doc_123"
    doc.user_id = "user_456"
    doc.filename = "test.pdf"
    doc.content_type = "application/pdf"
    doc.status = DocumentStatus.READY
    doc.minio_key = "/tmp/test.pdf"
    return doc


@pytest.fixture
def mock_validation_report():
    """Create a mock validation report."""
    report = Mock()
    report.job_id = "job_789"
    report.status = "done"
    report.findings = []
    report.summary = {
        "total_findings": 0,
        "policy_id": "auto",
        "policy_name": "Auto-detected Policy",
        "disclaimer_coverage": 1.0,
        "findings_by_severity": {"high": 0, "medium": 0, "low": 0},
    }
    report.attachments = []
    return report


@pytest.fixture
def mock_policy():
    """Create a mock policy."""
    policy = Mock()
    policy.id = "414-std"
    policy.name = "Standard 414 Policy"
    policy.client_name = "TestClient"

    def to_compliance_config():
        return {}

    policy.to_compliance_config = to_compliance_config
    return policy


class TestAuditFileTool:
    """Test suite for audit_file tool."""

    @pytest.mark.asyncio
    async def test_audit_file_success(
        self, mock_document, mock_validation_report, mock_policy
    ):
        """Test successful document audit."""
        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
             patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
             patch("src.mcp.server.get_minio_storage") as mock_minio, \
             patch("src.mcp.server.validate_document", new=AsyncMock(return_value=mock_validation_report)):

            # Mock minio storage
            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), False)
            mock_minio.return_value = mock_storage

            # Call tool
            result = await audit_file(
                doc_id="doc_123",
                policy_id="auto",
                enable_disclaimer=True,
                enable_format=True,
                enable_logo=True,
            )

            # Assertions
            assert result["job_id"] == "job_789"
            assert result["status"] == "done"
            assert result["findings"] == []
            assert result["summary"]["total_findings"] == 0
            assert result["summary"]["policy_id"] == "auto"

    @pytest.mark.asyncio
    async def test_audit_file_document_not_found(self):
        """Test audit with non-existent document."""
        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=None)):
            with pytest.raises(ValueError, match="Document not found"):
                await audit_file(
                    doc_id="nonexistent",
                    policy_id="auto",
                )

    @pytest.mark.asyncio
    async def test_audit_file_permission_denied(self, mock_document):
        """Test audit with wrong user."""
        mock_document.user_id = "other_user"

        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)):
            with pytest.raises(PermissionError, match="not authorized"):
                await audit_file(
                    doc_id="doc_123",
                    policy_id="auto",
                    user_id="current_user",  # Different from mock_document.user_id
                )

    @pytest.mark.asyncio
    async def test_audit_file_with_findings(
        self, mock_document, mock_policy
    ):
        """Test audit that returns findings."""
        # Mock report with findings
        report = Mock()
        report.job_id = "job_789"
        report.status = "done"
        report.findings = [
            Mock(
                model_dump=lambda: {
                    "id": "finding_1",
                    "category": "compliance",
                    "rule": "disclaimer_coverage",
                    "issue": "Missing disclaimer on page 5",
                    "severity": "high",
                    "location": {"page": 5},
                    "suggestion": "Add disclaimer to footer",
                }
            )
        ]
        report.summary = {
            "total_findings": 1,
            "policy_id": "414-std",
            "findings_by_severity": {"high": 1, "medium": 0, "low": 0},
        }
        report.attachments = []

        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
             patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
             patch("src.mcp.server.get_minio_storage") as mock_minio, \
             patch("src.mcp.server.validate_document", new=AsyncMock(return_value=report)):

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), False)
            mock_minio.return_value = mock_storage

            result = await audit_file(
                doc_id="doc_123",
                policy_id="414-std",
            )

            assert result["summary"]["total_findings"] == 1
            assert len(result["findings"]) == 1
            assert result["findings"][0]["severity"] == "high"
            assert "disclaimer" in result["findings"][0]["issue"].lower()

    @pytest.mark.asyncio
    async def test_audit_file_cleans_up_temp_file(
        self, mock_document, mock_validation_report, mock_policy
    ):
        """Test that temporary files are cleaned up."""
        temp_path = Path("/tmp/test_temp.pdf")

        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
             patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
             patch("src.mcp.server.get_minio_storage") as mock_minio, \
             patch("src.mcp.server.validate_document", new=AsyncMock(return_value=mock_validation_report)):

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (temp_path, True)  # is_temp=True
            mock_minio.return_value = mock_storage

            # Mock path.exists() and path.unlink()
            with patch.object(Path, "exists", return_value=True) as mock_exists, \
                 patch.object(Path, "unlink") as mock_unlink:

                await audit_file(doc_id="doc_123", policy_id="auto")

                # Verify cleanup was called
                mock_unlink.assert_called_once()

    @pytest.mark.asyncio
    async def test_audit_file_with_context_logging(
        self, mock_document, mock_validation_report, mock_policy
    ):
        """Test that context logging is used when available."""
        from fastmcp import Context

        mock_ctx = AsyncMock(spec=Context)

        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
             patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
             patch("src.mcp.server.get_minio_storage") as mock_minio, \
             patch("src.mcp.server.validate_document", new=AsyncMock(return_value=mock_validation_report)):

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), False)
            mock_minio.return_value = mock_storage

            await audit_file(
                doc_id="doc_123",
                policy_id="auto",
                ctx=mock_ctx,
            )

            # Verify context methods were called
            assert mock_ctx.info.called
            assert mock_ctx.report_progress.called

    @pytest.mark.asyncio
    async def test_audit_file_with_all_auditors_disabled(
        self, mock_document, mock_validation_report, mock_policy
    ):
        """Test audit with all auditors disabled."""
        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
             patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
             patch("src.mcp.server.get_minio_storage") as mock_minio, \
             patch("src.mcp.server.validate_document", new=AsyncMock(return_value=mock_validation_report)) as mock_validate:

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), False)
            mock_minio.return_value = mock_storage

            await audit_file(
                doc_id="doc_123",
                policy_id="auto",
                enable_disclaimer=False,
                enable_format=False,
                enable_logo=False,
            )

            # Verify validate_document was called with all disabled
            call_kwargs = mock_validate.call_args.kwargs
            assert call_kwargs["enable_disclaimer"] is False
            assert call_kwargs["enable_format"] is False
            assert call_kwargs["enable_logo"] is False

    @pytest.mark.asyncio
    async def test_audit_file_with_different_policies(
        self, mock_document, mock_validation_report
    ):
        """Test audit with different policy IDs."""
        policies = ["auto", "414-std", "414-strict", "banamex", "afore-xxi"]

        for policy_id in policies:
            mock_policy = Mock()
            mock_policy.id = policy_id
            mock_policy.name = f"Policy {policy_id}"
            mock_policy.client_name = "TestClient"
            mock_policy.to_compliance_config = lambda: {}

            with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
                 patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
                 patch("src.mcp.server.get_minio_storage") as mock_minio, \
                 patch("src.mcp.server.validate_document", new=AsyncMock(return_value=mock_validation_report)):

                mock_storage = Mock()
                mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), False)
                mock_minio.return_value = mock_storage

                result = await audit_file(
                    doc_id="doc_123",
                    policy_id=policy_id,
                )

                assert result["status"] == "done"


class TestAuditFileIntegration:
    """Integration tests with real FastMCP context."""

    @pytest.mark.asyncio
    async def test_audit_file_via_mcp_server(
        self, mock_document, mock_validation_report, mock_policy
    ):
        """Test audit_file through FastMCP server."""
        from src.mcp.server import mcp

        with patch("src.mcp.server.Document.get", new=AsyncMock(return_value=mock_document)), \
             patch("src.mcp.server.resolve_policy", new=AsyncMock(return_value=mock_policy)), \
             patch("src.mcp.server.get_minio_storage") as mock_minio, \
             patch("src.mcp.server.validate_document", new=AsyncMock(return_value=mock_validation_report)):

            mock_storage = Mock()
            mock_storage.materialize_document.return_value = (Path("/tmp/test.pdf"), False)
            mock_minio.return_value = mock_storage

            # Get tool function from MCP server
            tool_func = mcp._tools.get("audit_file")
            assert tool_func is not None

            # Invoke tool
            result = await tool_func(
                doc_id="doc_123",
                policy_id="auto",
            )

            assert result["job_id"] == "job_789"
            assert result["status"] == "done"
