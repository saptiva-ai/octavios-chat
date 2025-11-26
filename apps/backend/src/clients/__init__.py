"""
HTTP clients for external services and plugins.

This module provides clients to communicate with:
- file-manager: Public plugin for file operations
- capital414-auditor: Private plugin for document auditing
"""

from .file_manager import FileManagerClient, get_file_manager_client

__all__ = ["FileManagerClient", "get_file_manager_client"]
