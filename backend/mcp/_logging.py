"""structlog shim for environments where dependency is unavailable."""

from __future__ import annotations

import logging
from typing import Any

try:  # pragma: no cover - exercised when structlog is installed
    import structlog  # type: ignore

    def get_logger(name: str | None = None) -> Any:
        return structlog.get_logger(name)

except ImportError:  # pragma: no cover - used in lightweight test envs

    def get_logger(name: str | None = None) -> logging.Logger:
        return logging.getLogger(name or "backend.mcp")
