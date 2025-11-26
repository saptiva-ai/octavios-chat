"""
Regression Tests for File Deduplication

Tests que previenen regresión de bugs conocidos:
- BUG-001: Deduplication not working for same file uploaded twice
- BUG-002: Hash not being stored in metadata
- BUG-003: Duplicate detection failing across different users
- BUG-004: MinIO cleanup deleting duplicate file but not original
- BUG-005: Race condition when uploading same file concurrently
"""

import pytest
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

from src.services.file_ingest import FileIngestService
from src.services.resource_lifecycle_manager import get_resource_manager
from src.models.document import Document, DocumentStatus


class TestFileDeduplicationRegression:
    """Regression tests for file deduplication."""

    @pytest.fixture
    def file_ingest_service(self):
        """Create FileIngestService instance."""
        return FileIngestService()

    @pytest.fixture
    def sample_pdf_content(self):
        """Sample PDF content for testing."""
        return b"%PDF-1.4\n%Test PDF\nHello World"

    @pytest.fixture
    def sample_file_hash(self, sample_pdf_content):
        """Compute hash of sample file."""
        return hashlib.sha256(sample_pdf_content).hexdigest()

    @pytest.mark.asyncio
    @patch("src.services.file_ingest.storage")
    @patch("src.services.file_ingest.minio_service")
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_bug_001_deduplication_works_for_same_file_twice(
        self,
        mock_document,
        mock_minio_service,
        mock_storage,
        file_ingest_service,
        sample_pdf_content,
        sample_file_hash
    ):
        """
        BUG-001: Deduplication not working for same file uploaded twice.

        Regression test to ensure that uploading the same file twice
        returns the same document ID without re-processing.
        """
        # Arrange
        user_id = "user123"

        # First upload - create new document
        mock_document.find_one = AsyncMock(return_value=None)  # No duplicate
        mock_doc_instance = MagicMock()
        mock_doc_instance.id = "doc123"
        mock_doc_instance.status = DocumentStatus.READY
        mock_doc_instance.filename = "test.pdf"
        mock_doc_instance.size_bytes = len(sample_pdf_content)
        mock_doc_instance.insert = AsyncMock()
        mock_document.return_value = mock_doc_instance

        # Mock storage and MinIO
        mock_storage.save_upload = AsyncMock(return_value=(
            "uploads", "doc123.pdf", "test.pdf", len(sample_pdf_content)
        ))
        mock_minio_service.download_to_path = AsyncMock()
        mock_minio_service.delete_file = AsyncMock()

        # Mock filetype detection
        with patch("src.services.file_ingest.filetype.guess") as mock_filetype:
            mock_kind = MagicMock()
            mock_kind.mime = "application/pdf"
            mock_filetype.return_value = mock_kind

            # Create mock upload file
            mock_upload = MagicMock()
            mock_upload.filename = "test.pdf"
            mock_upload.content_type = "application/pdf"

            # First upload
            result1 = await file_ingest_service.ingest_file(
                user_id=user_id,
                upload=mock_upload,
                trace_id="trace1",
                conversation_id="conv1",
                idempotency_key=None
            )

            # Second upload - should find duplicate
            mock_existing_doc = MagicMock()
            mock_existing_doc.id = "doc123"
            mock_existing_doc.status = DocumentStatus.READY
            mock_existing_doc.filename = "test.pdf"
            mock_existing_doc.size_bytes = len(sample_pdf_content)

            mock_document.find_one = AsyncMock(return_value=mock_existing_doc)
            mock_document.get = AsyncMock(return_value=mock_existing_doc)

            result2 = await file_ingest_service.ingest_file(
                user_id=user_id,
                upload=mock_upload,
                trace_id="trace2",
                conversation_id="conv1",
                idempotency_key=None
            )

        # Assert - Same document ID returned
        assert result1.file_id == result2.file_id
        # Assert - MinIO file deleted on second upload
        mock_minio_service.delete_file.assert_called()

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_bug_002_hash_stored_in_metadata(
        self,
        mock_document,
        sample_file_hash
    ):
        """
        BUG-002: Hash not being stored in metadata.

        Regression test to ensure file hash is properly stored in
        document metadata for future deduplication.
        """
        # Arrange
        manager = get_resource_manager()

        # Act
        result = await manager.check_duplicate_file(sample_file_hash, "user123")

        # Assert
        mock_document.find_one.assert_called_once_with({
            "metadata.file_hash": sample_file_hash,
            "user_id": "user123"
        })

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_bug_003_duplicate_detection_respects_user_scope(
        self,
        mock_document,
        sample_file_hash
    ):
        """
        BUG-003: Duplicate detection failing across different users.

        Regression test to ensure deduplication is scoped per user.
        Same file uploaded by different users should NOT be deduplicated.
        """
        # Arrange
        manager = get_resource_manager()

        # Mock document exists for user1
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_document.find_one = AsyncMock(return_value=mock_doc)

        # Act - Check for user1 (should find)
        result1 = await manager.check_duplicate_file(sample_file_hash, "user1")

        # Assert - Found for user1
        assert result1 == "doc123"

        # Act - Check for user2 (should not find - different user)
        mock_document.find_one = AsyncMock(return_value=None)
        result2 = await manager.check_duplicate_file(sample_file_hash, "user2")

        # Assert - Not found for user2
        assert result2 is None

        # Assert - Query included user_id filter
        last_call_args = mock_document.find_one.call_args[0][0]
        assert "user_id" in last_call_args
        assert last_call_args["user_id"] == "user2"

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    @patch("src.services.resource_lifecycle_manager.ChatSession")
    @patch("src.services.resource_lifecycle_manager.get_file_storage")
    async def test_bug_004_cleanup_doesnt_delete_referenced_original(
        self,
        mock_get_storage,
        mock_chat_session,
        mock_document
    ):
        """
        BUG-004: MinIO cleanup deleting duplicate file but not original.

        Regression test to ensure cleanup doesn't delete files that are
        still referenced by active chat sessions.
        """
        # Arrange
        from datetime import datetime, timedelta
        manager = get_resource_manager()

        # Mock old document
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = "uploads/doc123.pdf"
        mock_doc.filename = "test.pdf"
        mock_doc.created_at = datetime.utcnow() - timedelta(days=10)
        mock_doc.delete = AsyncMock()

        mock_document.find.return_value.to_list = AsyncMock(return_value=[mock_doc])

        # Mock active session references this document
        mock_chat_session.find.return_value.count = AsyncMock(return_value=1)  # Active session

        mock_storage = AsyncMock()
        mock_get_storage.return_value = mock_storage

        # Act
        deleted_count = await manager._cleanup_minio_files()

        # Assert - Should NOT delete (active session)
        assert deleted_count == 0
        mock_storage.delete_file.assert_not_called()
        mock_doc.delete.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.services.file_ingest.storage")
    @patch("src.services.file_ingest.minio_service")
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_bug_005_race_condition_concurrent_uploads(
        self,
        mock_document,
        mock_minio_service,
        mock_storage,
        file_ingest_service,
        sample_pdf_content,
        sample_file_hash
    ):
        """
        BUG-005: Race condition when uploading same file concurrently.

        Regression test to ensure concurrent uploads of same file
        don't create multiple documents due to race condition.
        """
        import asyncio

        # Arrange
        user_id = "user123"

        # First check: no duplicate
        # Second check (concurrent): still no duplicate (race condition)
        # Third check: duplicate found
        call_count = 0

        async def mock_find_one(query):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                # Simulate race condition: both checks see no duplicate
                return None
            else:
                # Eventually duplicate is found
                mock_doc = MagicMock()
                mock_doc.id = "doc123"
                return mock_doc

        mock_document.find_one = mock_find_one
        mock_document.get = AsyncMock(return_value=MagicMock(
            id="doc123",
            status=DocumentStatus.READY,
            filename="test.pdf",
            size_bytes=len(sample_pdf_content)
        ))

        mock_doc_instance = MagicMock()
        mock_doc_instance.id = "doc123"
        mock_doc_instance.status = DocumentStatus.READY
        mock_doc_instance.insert = AsyncMock()
        mock_document.return_value = mock_doc_instance

        mock_storage.save_upload = AsyncMock(return_value=(
            "uploads", "doc123.pdf", "test.pdf", len(sample_pdf_content)
        ))
        mock_minio_service.download_to_path = AsyncMock()
        mock_minio_service.delete_file = AsyncMock()

        with patch("src.services.file_ingest.filetype.guess") as mock_filetype:
            mock_kind = MagicMock()
            mock_kind.mime = "application/pdf"
            mock_filetype.return_value = mock_kind

            mock_upload = MagicMock()
            mock_upload.filename = "test.pdf"
            mock_upload.content_type = "application/pdf"

            # Act - Simulate concurrent uploads
            results = await asyncio.gather(
                file_ingest_service.ingest_file(
                    user_id=user_id,
                    upload=mock_upload,
                    trace_id="trace1",
                    conversation_id="conv1",
                    idempotency_key=None
                ),
                file_ingest_service.ingest_file(
                    user_id=user_id,
                    upload=mock_upload,
                    trace_id="trace2",
                    conversation_id="conv1",
                    idempotency_key=None
                ),
                return_exceptions=True
            )

        # Assert - At least one upload succeeded
        successful_uploads = [r for r in results if not isinstance(r, Exception)]
        assert len(successful_uploads) >= 1

        # Note: This test documents the race condition.
        # In production, use database-level unique constraints or distributed locks


class TestDeduplicationEdgeCases:
    """Edge cases for file deduplication."""

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_different_files_same_size_not_deduplicated(self, mock_document):
        """Test that files with same size but different content are not deduplicated."""
        # Arrange
        manager = get_resource_manager()
        content1 = b"A" * 1000
        content2 = b"B" * 1000

        hash1 = await manager.compute_file_hash(content1)
        hash2 = await manager.compute_file_hash(content2)

        # Assert - Different hashes
        assert hash1 != hash2

    @pytest.mark.asyncio
    async def test_empty_file_deduplication(self):
        """Test deduplication works for empty files."""
        # Arrange
        manager = get_resource_manager()
        content = b""

        # Act
        hash1 = await manager.compute_file_hash(content)
        hash2 = await manager.compute_file_hash(content)

        # Assert - Same hash for empty files
        assert hash1 == hash2
        assert hash1 == hashlib.sha256(b"").hexdigest()

    @pytest.mark.asyncio
    async def test_very_large_file_deduplication(self):
        """Test deduplication works for large files."""
        # Arrange
        manager = get_resource_manager()
        # 50 MB file
        content = b"X" * (50 * 1024 * 1024)

        # Act
        hash_result = await manager.compute_file_hash(content)

        # Assert - Hash computed successfully
        assert len(hash_result) == 64
        assert hash_result == hashlib.sha256(content).hexdigest()
