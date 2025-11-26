"""
HTTP client for the file-manager plugin.

This client allows the Capital414 auditor plugin to download files
from the public file-manager plugin, following Plugin-First Architecture.

Usage:
    client = await get_file_manager_client()

    # Download file to temporary location
    temp_path = await client.download_to_temp(minio_key)

    # Use temp_path for auditing
    result = await audit_document(temp_path)

    # Clean up
    temp_path.unlink()
"""

import os
import tempfile
from pathlib import Path
from typing import Optional

import httpx
import structlog

logger = structlog.get_logger(__name__)


class FileManagerClient:
    """
    HTTP client for the file-manager plugin.

    Provides methods to download and access files from the file-manager
    microservice.
    """

    def __init__(self, base_url: Optional[str] = None):
        """
        Initialize the file-manager client.

        Args:
            base_url: Base URL of file-manager service.
                      Defaults to FILE_MANAGER_URL env var or http://file-manager:8003
        """
        self.base_url = base_url or os.getenv(
            "FILE_MANAGER_URL", "http://file-manager:8003"
        )
        self._client: Optional[httpx.AsyncClient] = None

        logger.info("FileManagerClient initialized", base_url=self.base_url)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(120.0, connect=10.0),
            )
        return self._client

    async def download(self, file_path: str) -> bytes:
        """
        Download a file from the file-manager.

        Args:
            file_path: MinIO object path (user_id/session_id/file_id.ext)

        Returns:
            File content as bytes
        """
        client = await self._get_client()

        logger.debug("Downloading file from file-manager", file_path=file_path)

        response = await client.get(f"/download/{file_path}")
        response.raise_for_status()

        return response.content

    async def download_to_temp(self, file_path: str) -> Path:
        """
        Download a file to a temporary location.

        This is the primary method for auditors that need local file access.
        The caller is responsible for cleaning up the temporary file.

        Args:
            file_path: MinIO object path

        Returns:
            Path to temporary file (caller must delete after use)
        """
        content = await self.download(file_path)

        # Extract extension from path
        filename = file_path.split("/")[-1]
        suffix = Path(filename).suffix or ".pdf"

        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.info(
            "File downloaded to temp",
            file_path=file_path,
            temp_path=str(tmp_path),
            size=len(content),
        )

        return tmp_path

    async def get_metadata(self, file_path: str, include_text: bool = False) -> dict:
        """
        Get file metadata from the file-manager.

        Args:
            file_path: MinIO object path
            include_text: Whether to include extracted text

        Returns:
            Dict with file_id, filename, size, content_type, etc.
        """
        client = await self._get_client()

        params = {"include_text": str(include_text).lower()}
        response = await client.get(f"/metadata/{file_path}", params=params)
        response.raise_for_status()

        return response.json()

    async def get_extracted_text(self, file_path: str) -> str:
        """
        Get extracted text for a file.

        Useful for auditors that need text content without downloading
        the full file.

        Args:
            file_path: MinIO object path

        Returns:
            Extracted text content
        """
        metadata = await self.get_metadata(file_path, include_text=True)
        return metadata.get("extracted_text", "")

    async def health_check(self) -> dict:
        """Check file-manager health status."""
        client = await self._get_client()

        response = await client.get("/health")
        response.raise_for_status()

        return response.json()

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Singleton instance
_client: Optional[FileManagerClient] = None


async def get_file_manager_client() -> FileManagerClient:
    """
    Get the global FileManagerClient instance.

    Creates a new instance on first call.

    Returns:
        FileManagerClient instance
    """
    global _client
    if _client is None:
        _client = FileManagerClient()
    return _client


async def close_file_manager_client() -> None:
    """Close the global FileManagerClient."""
    global _client
    if _client:
        await _client.close()
        _client = None
