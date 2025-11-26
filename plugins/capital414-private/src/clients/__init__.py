"""
HTTP clients for external services.

This module provides clients to communicate with:
- file-manager: Public plugin for file operations
"""

from .file_manager import FileManagerClient, get_file_manager_client

__all__ = ["FileManagerClient", "get_file_manager_client"]
