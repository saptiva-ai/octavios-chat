"""
Unit Tests for ResourceLifecycleManager

Tests:
- compute_file_hash: SHA256 hash computation
- check_duplicate_file: Duplicate detection logic
- get_resource_metrics: Metrics calculation
- schedule_cleanup_task: Queue management
- cleanup_expired_resources: Cleanup logic
"""

import pytest
import hashlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.resource_lifecycle_manager import (
    ResourceLifecycleManager,
    ResourceType,
    CleanupPriority,
    ResourceMetrics,
    CleanupTask,
)


class TestResourceLifecycleManager:
    """Unit tests for ResourceLifecycleManager."""

    @pytest.fixture
    def manager(self):
        """Create manager instance."""
        return ResourceLifecycleManager()

    @pytest.mark.asyncio
    async def test_compute_file_hash(self, manager):
        """Test SHA256 hash computation."""
        # Arrange
        file_content = b"Hello World"
        expected_hash = hashlib.sha256(file_content).hexdigest()

        # Act
        result_hash = await manager.compute_file_hash(file_content)

        # Assert
        assert result_hash == expected_hash
        assert len(result_hash) == 64  # SHA256 produces 64 hex chars

    @pytest.mark.asyncio
    async def test_compute_file_hash_empty_file(self, manager):
        """Test hash computation for empty file."""
        # Arrange
        file_content = b""
        expected_hash = hashlib.sha256(file_content).hexdigest()

        # Act
        result_hash = await manager.compute_file_hash(file_content)

        # Assert
        assert result_hash == expected_hash

    @pytest.mark.asyncio
    async def test_compute_file_hash_large_file(self, manager):
        """Test hash computation for large file."""
        # Arrange - 10 MB file
        file_content = b"x" * (10 * 1024 * 1024)
        expected_hash = hashlib.sha256(file_content).hexdigest()

        # Act
        result_hash = await manager.compute_file_hash(file_content)

        # Assert
        assert result_hash == expected_hash

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_check_duplicate_file_found(self, mock_document, manager):
        """Test duplicate detection when file exists."""
        # Arrange
        file_hash = "abc123def456"
        user_id = "user123"
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_document.find_one = AsyncMock(return_value=mock_doc)

        # Act
        result = await manager.check_duplicate_file(file_hash, user_id)

        # Assert
        assert result == "doc123"
        mock_document.find_one.assert_called_once_with({
            "metadata.file_hash": file_hash,
            "user_id": user_id
        })

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    async def test_check_duplicate_file_not_found(self, mock_document, manager):
        """Test duplicate detection when file doesn't exist."""
        # Arrange
        file_hash = "abc123def456"
        user_id = "user123"
        mock_document.find_one = AsyncMock(return_value=None)

        # Act
        result = await manager.check_duplicate_file(file_hash, user_id)

        # Assert
        assert result is None

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.get_redis_cache")
    async def test_get_redis_metrics(self, mock_get_cache, manager):
        """Test Redis metrics calculation."""
        # Arrange
        mock_cache = MagicMock()
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": 128 * 1024 * 1024  # 128 MB
        })
        mock_cache.client.dbsize = AsyncMock(return_value=5000)
        mock_get_cache.return_value = mock_cache

        # Act
        metrics = await manager._get_redis_metrics()

        # Assert
        assert isinstance(metrics, ResourceMetrics)
        assert metrics.resource_type == ResourceType.REDIS_CACHE
        assert metrics.total_items == 5000
        assert metrics.total_size_bytes == 128 * 1024 * 1024
        assert 0 <= metrics.usage_percentage <= 1
        assert isinstance(metrics.cleanup_priority, CleanupPriority)

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.get_redis_cache")
    async def test_get_redis_metrics_critical_usage(self, mock_get_cache, manager):
        """Test Redis metrics when usage is critical."""
        # Arrange - 95% usage
        mock_cache = MagicMock()
        mock_cache.client.info = AsyncMock(return_value={
            "used_memory": int(0.95 * manager.max_redis_memory_mb * 1024 * 1024)
        })
        mock_cache.client.dbsize = AsyncMock(return_value=10000)
        mock_get_cache.return_value = mock_cache

        # Act
        metrics = await manager._get_redis_metrics()

        # Assert
        assert metrics.cleanup_priority == CleanupPriority.CRITICAL
        assert metrics.usage_percentage >= manager.cleanup_threshold_critical

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.get_qdrant_service")
    async def test_get_qdrant_metrics(self, mock_get_service, manager):
        """Test Qdrant metrics calculation."""
        # Arrange
        mock_service = MagicMock()
        mock_collection_info = MagicMock()
        mock_collection_info.points_count = 1500
        mock_service.client.get_collection = MagicMock(return_value=mock_collection_info)
        mock_service.collection_name = "rag_documents"
        mock_get_service.return_value = mock_service

        # Act
        metrics = await manager._get_qdrant_metrics()

        # Assert
        assert isinstance(metrics, ResourceMetrics)
        assert metrics.resource_type == ResourceType.QDRANT_VECTORS
        assert metrics.total_items == 1500
        assert metrics.total_size_bytes == 1500 * 384 * 4  # 384-dim vectors
        assert isinstance(metrics.cleanup_priority, CleanupPriority)

    @pytest.mark.asyncio
    async def test_schedule_cleanup_task(self, manager):
        """Test scheduling cleanup task."""
        # Arrange
        assert len(manager.cleanup_queue) == 0

        # Act
        await manager.schedule_cleanup_task(
            resource_type=ResourceType.REDIS_CACHE,
            target_id="key123",
            priority=CleanupPriority.HIGH,
            reason="High memory usage"
        )

        # Assert
        assert len(manager.cleanup_queue) == 1
        task = manager.cleanup_queue[0]
        assert isinstance(task, CleanupTask)
        assert task.resource_type == ResourceType.REDIS_CACHE
        assert task.priority == CleanupPriority.HIGH
        assert task.reason == "High memory usage"

    @pytest.mark.asyncio
    async def test_schedule_cleanup_task_ordering(self, manager):
        """Test that cleanup queue is ordered by priority."""
        # Arrange & Act - Schedule tasks in reverse priority order
        await manager.schedule_cleanup_task(
            ResourceType.REDIS_CACHE, "1", CleanupPriority.LOW, "Low"
        )
        await manager.schedule_cleanup_task(
            ResourceType.QDRANT_VECTORS, "2", CleanupPriority.CRITICAL, "Critical"
        )
        await manager.schedule_cleanup_task(
            ResourceType.MINIO_FILES, "3", CleanupPriority.HIGH, "High"
        )

        # Assert - Queue should be ordered: CRITICAL, HIGH, LOW
        assert len(manager.cleanup_queue) == 3
        assert manager.cleanup_queue[0].priority == CleanupPriority.CRITICAL
        assert manager.cleanup_queue[1].priority == CleanupPriority.HIGH
        assert manager.cleanup_queue[2].priority == CleanupPriority.LOW

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.get_redis_cache")
    async def test_cleanup_redis_cache(self, mock_get_cache, manager):
        """Test Redis cache cleanup."""
        # Arrange
        mock_cache = MagicMock()

        # Simulate keys without TTL
        mock_cache.client.scan = AsyncMock(side_effect=[
            (0, [b"doc_segments:key1", b"doc_segments:key2"]),  # First scan
        ])
        mock_cache.client.ttl = AsyncMock(side_effect=[-1, -1])  # No TTL
        mock_cache.client.delete = AsyncMock()
        mock_get_cache.return_value = mock_cache

        # Act
        deleted_count = await manager._cleanup_redis_cache()

        # Assert
        assert deleted_count == 2
        assert mock_cache.client.delete.call_count == 2

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.get_qdrant_service")
    async def test_cleanup_qdrant_vectors(self, mock_get_service, manager):
        """Test Qdrant vectors cleanup."""
        # Arrange
        mock_service = MagicMock()
        mock_service.cleanup_old_sessions = MagicMock(return_value=150)
        mock_get_service.return_value = mock_service

        # Act
        deleted_count = await manager._cleanup_qdrant_vectors()

        # Assert
        assert deleted_count == 150
        mock_service.cleanup_old_sessions.assert_called_once_with(
            hours=manager.qdrant_ttl_hours
        )

    @pytest.mark.asyncio
    @patch("src.services.resource_lifecycle_manager.Document")
    @patch("src.services.resource_lifecycle_manager.ChatSession")
    @patch("src.services.resource_lifecycle_manager.get_file_storage")
    async def test_cleanup_minio_files(self, mock_get_storage, mock_chat_session, mock_document, manager):
        """Test MinIO files cleanup."""
        # Arrange
        cutoff_time = datetime.utcnow() - timedelta(days=manager.minio_ttl_days)

        # Create mock old document
        mock_doc = MagicMock()
        mock_doc.id = "doc123"
        mock_doc.minio_path = "uploads/doc123.pdf"
        mock_doc.filename = "test.pdf"
        mock_doc.created_at = cutoff_time - timedelta(days=1)
        mock_doc.delete = AsyncMock()

        mock_document.find.return_value.to_list = AsyncMock(return_value=[mock_doc])
        mock_chat_session.find.return_value.count = AsyncMock(return_value=0)  # No active sessions

        mock_storage = AsyncMock()
        mock_get_storage.return_value = mock_storage

        # Act
        deleted_count = await manager._cleanup_minio_files()

        # Assert
        assert deleted_count == 1
        mock_storage.delete_file.assert_called_once_with("uploads/doc123.pdf")
        mock_doc.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cleanup_queue(self, manager):
        """Test processing cleanup queue."""
        # Arrange
        manager._cleanup_redis_cache = AsyncMock(return_value=5)
        manager._cleanup_qdrant_vectors = AsyncMock(return_value=10)

        await manager.schedule_cleanup_task(
            ResourceType.REDIS_CACHE, "all", CleanupPriority.HIGH, "Test"
        )
        await manager.schedule_cleanup_task(
            ResourceType.QDRANT_VECTORS, "all", CleanupPriority.CRITICAL, "Test"
        )

        # Act
        await manager.process_cleanup_queue(max_tasks=2)

        # Assert
        assert len(manager.cleanup_queue) == 0
        manager._cleanup_redis_cache.assert_called_once()
        manager._cleanup_qdrant_vectors.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_cleanup_queue_max_tasks(self, manager):
        """Test that process_cleanup_queue respects max_tasks limit."""
        # Arrange
        manager._cleanup_redis_cache = AsyncMock(return_value=0)

        # Schedule 5 tasks
        for i in range(5):
            await manager.schedule_cleanup_task(
                ResourceType.REDIS_CACHE, f"task{i}", CleanupPriority.LOW, "Test"
            )

        # Act - Process only 3 tasks
        await manager.process_cleanup_queue(max_tasks=3)

        # Assert
        assert len(manager.cleanup_queue) == 2  # 5 - 3 = 2 remaining
        assert manager._cleanup_redis_cache.call_count == 3


class TestResourceMetrics:
    """Unit tests for ResourceMetrics dataclass."""

    def test_resource_metrics_creation(self):
        """Test creating ResourceMetrics instance."""
        # Act
        metrics = ResourceMetrics(
            resource_type=ResourceType.REDIS_CACHE,
            total_items=1000,
            total_size_bytes=50 * 1024 * 1024,
            oldest_item_age_hours=2.5,
            usage_percentage=0.45,
            cleanup_priority=CleanupPriority.MEDIUM
        )

        # Assert
        assert metrics.resource_type == ResourceType.REDIS_CACHE
        assert metrics.total_items == 1000
        assert metrics.total_size_bytes == 50 * 1024 * 1024
        assert metrics.oldest_item_age_hours == 2.5
        assert metrics.usage_percentage == 0.45
        assert metrics.cleanup_priority == CleanupPriority.MEDIUM


class TestCleanupTask:
    """Unit tests for CleanupTask dataclass."""

    def test_cleanup_task_creation(self):
        """Test creating CleanupTask instance."""
        # Arrange
        now = datetime.utcnow()

        # Act
        task = CleanupTask(
            priority=CleanupPriority.HIGH,
            resource_type=ResourceType.QDRANT_VECTORS,
            target_id="session123",
            created_at=now,
            reason="High resource usage: 80%"
        )

        # Assert
        assert task.priority == CleanupPriority.HIGH
        assert task.resource_type == ResourceType.QDRANT_VECTORS
        assert task.target_id == "session123"
        assert task.created_at == now
        assert task.reason == "High resource usage: 80%"
