"""
Context service for attachment handling.

Provides normalized session file lists and builds RAG-friendly context
using the shared extraction cache (doc:text:* keys).
"""

from __future__ import annotations

from typing import List, Dict, Any, Optional
import asyncio

import structlog

from .redis_client import get_extraction_cache, get_redis_client
from ..config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


def _normalize_ids(file_ids: Optional[List[str]]) -> List[str]:
    """Remove duplicates preserving order."""
    if not file_ids:
        return []
    seen = set()
    ordered: List[str] = []
    for fid in file_ids:
        if fid in seen:
            continue
        seen.add(fid)
        ordered.append(fid)
    return ordered


async def _store_session_files(session_id: str, file_ids: List[str]) -> None:
    """Persist session → file_ids mapping in Redis for reuse."""
    client = get_redis_client()
    if not client or not session_id:
        return
    try:
        key = f"session:files:{session_id}"
        ttl = settings.extraction_cache_ttl_seconds
        await client.setex(key, ttl, ",".join(file_ids))
    except Exception as exc:  # pragma: no cover - best-effort logging only
        logger.warning(
            "Failed to store session files",
            session_id=session_id,
            file_count=len(file_ids),
            error=str(exc),
        )


async def _load_session_files(session_id: Optional[str]) -> List[str]:
    """Load previously stored session file list from Redis."""
    if not session_id:
        return []
    client = get_redis_client()
    if not client:
        return []
    try:
        key = f"session:files:{session_id}"
        value = await client.get(key)
        if not value:
            return []
        return _normalize_ids(value.split(","))
    except Exception as exc:  # pragma: no cover - best-effort logging only
        logger.warning(
            "Failed to load session files",
            session_id=session_id,
            error=str(exc),
        )
        return []


async def prepare_context_payload(
    *,
    user_id: str,
    session_id: Optional[str],
    request_file_ids: List[str],
    previous_file_ids: List[str],
    max_docs: int = 3,
    max_chars_per_doc: int = 8000,
    max_total_chars: int = 16000,
) -> Dict[str, Any]:
    """
    Build attachment context from cached extractions.

    Returns combined context text, per-file metadata, warnings, and the
    final file_id list to be used by the caller.
    """
    normalized_request = _normalize_ids(request_file_ids)
    cached_session_files = previous_file_ids or await _load_session_files(session_id)

    # Current context: prefer explicit request, fallback to stored list
    current_file_ids = normalized_request or cached_session_files

    # Persist for future reuse
    if session_id and current_file_ids:
        await _store_session_files(session_id, current_file_ids)

    cache = get_extraction_cache()
    documents: List[Dict[str, Any]] = []
    warnings: List[str] = []

    total_chars = 0
    truncated_ids: List[str] = []
    omitted_ids: List[str] = []

    for fid in current_file_ids:
        if len(documents) >= max_docs:
            omitted_ids.append(fid)
            continue

        cached = await cache.get(fid)
        if not cached:
            warnings.append(f"missing_cache:{fid}")
            continue

        text = cached.get("text") or ""
        metadata = cached.get("metadata") or {}
        filename = metadata.get("filename") or fid
        content_type = metadata.get("content_type") or "application/octet-stream"
        pages = cached.get("pages")

        # Enforce per-doc and total budgets
        truncated = False
        if len(text) > max_chars_per_doc:
            text = text[:max_chars_per_doc]
            truncated = True
            truncated_ids.append(fid)

        if total_chars + len(text) > max_total_chars:
            allowed = max_total_chars - total_chars
            if allowed <= 0:
                omitted_ids.append(fid)
                continue
            text = text[:allowed]
            truncated = True
            truncated_ids.append(fid)

        total_chars += len(text)
        documents.append(
            {
                "file_id": fid,
                "filename": filename,
                "content_type": content_type,
                "pages": pages,
                "text": text,
                "truncated": truncated,
                "metadata": metadata,
            }
        )

    combined = "\n\n".join(
        f"[Archivo: {doc.get('filename')}]\\n{doc.get('text', '')}" for doc in documents
    )

    return {
        "current_file_ids": current_file_ids,
        "documents": documents,
        "warnings": warnings,
        "stats": {
            "used_docs": len(documents),
            "omitted_docs": omitted_ids,
            "truncated_docs": truncated_ids,
            "used_chars": total_chars,
        },
        "combined_text": combined,
        "user_id": user_id,
        "session_id": session_id,
    }
