"""Storage adapters for external persistence layers (MinIO/S3, filesystem)."""

from .minio_storage import MinioStorageAdapter

__all__ = ["MinioStorageAdapter"]
