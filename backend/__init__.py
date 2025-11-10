"""Backend shared utilities package."""

from importlib import metadata as _metadata


def version() -> str:
    """Return package version if installed, else development placeholder."""
    try:
        return _metadata.version("octavios-backend")
    except _metadata.PackageNotFoundError:  # pragma: no cover - dev mode
        return "0.0.0-dev"


__all__ = ["version"]
