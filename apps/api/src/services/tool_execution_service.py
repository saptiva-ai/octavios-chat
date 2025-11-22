"""
Tool Execution Service.

This service handles the orchestration and execution of MCP tools
with built-in Redis caching and error handling.

It abstracts the complexity of:
- Tool discovery
- Cache key generation
- TTL management
- Error resilience
"""

import json
import hashlib
from typing import Dict, Any, Optional, List
import structlog

from ..core.redis_cache import get_redis_cache
from ..domain.chat_context import ChatContext
from ..mcp import get_mcp_adapter
from ..core.constants import (
    TOOL_NAME_AUDIT,
    TOOL_NAME_EXCEL,
    TOOL_NAME_RESEARCH,
    TOOL_NAME_EXTRACT
)

logger = structlog.get_logger(__name__)

# TTL configuration for each tool (in seconds)
TOOL_CACHE_TTL = {
    TOOL_NAME_AUDIT: 3600,       # 1 hour (findings don't change)
    TOOL_NAME_EXCEL: 1800,   # 30 min (data might update)
    TOOL_NAME_RESEARCH: 86400,   # 24 hours (research is expensive)
    TOOL_NAME_EXTRACT: 3600,  # 1 hour (text is stable)
}

class ToolExecutionService:
    """Service for executing MCP tools with caching strategies."""

    @staticmethod
    def _generate_cache_key(tool_name: str, doc_id: str, params: Dict = None) -> str:
        """
        Generate unique cache key for tool result.
        Format: mcp:tool:{tool_name}:{doc_id}:{params_hash}
        """
        if params:
            # Create deterministic hash of params
            params_str = json.dumps(params, sort_keys=True)
            params_hash = hashlib.md5(params_str.encode()).hexdigest()[:8]
            return f"mcp:tool:{tool_name}:{doc_id}:{params_hash}"
        return f"mcp:tool:{tool_name}:{doc_id}"

    @classmethod
    async def _execute_tool_with_cache(
        cls,
        tool_name: str,
        doc_id: str,
        user_id: str,
        payload: Dict[str, Any],
        cache_params: Dict[str, Any],
        tool_map: Dict[str, Any],
        mcp_adapter: Any,
        cache: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Generic method to execute a tool with Redis caching.
        
        Args:
            tool_name: Name of the tool to execute
            doc_id: ID of the document being processed
            user_id: ID of the user invoking the tool
            payload: Full payload to send to the tool
            cache_params: Parameters used to generate the cache key
            tool_map: Map of available tools
            mcp_adapter: Adapter to execute the tool
            cache: Redis cache instance
            
        Returns:
            The tool result dict or None if execution failed
        """
        try:
            # Generate cache key
            cache_key = cls._generate_cache_key(tool_name, doc_id, cache_params)

            # Try to get from cache first
            cached_result = None
            if cache:
                try:
                    cached_result = await cache.get(cache_key)
                    if cached_result:
                        logger.info(
                            f"{tool_name} result loaded from cache",
                            doc_id=doc_id,
                            cache_hit=True
                        )
                        return cached_result
                except Exception as e:
                    logger.warning(
                        "Failed to read from cache",
                        cache_key=cache_key,
                        error=str(e)
                    )

            # Execute tool
            logger.info(
                f"Invoking {tool_name} tool",
                doc_id=doc_id,
                user_id=user_id,
                cache_hit=False
            )

            tool_impl = tool_map[tool_name]
            result = await mcp_adapter._execute_tool_impl(
                tool_name=tool_name,
                tool_impl=tool_impl,
                payload=payload
            )

            # Store in cache
            if cache:
                try:
                    ttl = TOOL_CACHE_TTL.get(tool_name, 3600)
                    await cache.set(cache_key, result, expire=ttl)
                    logger.debug(
                        f"Cached {tool_name} result",
                        cache_key=cache_key,
                        ttl=ttl
                    )
                except Exception as e:
                    logger.warning(
                        f"Failed to cache {tool_name} result",
                        cache_key=cache_key,
                        error=str(e)
                    )
            
            return result

        except Exception as e:
            logger.warning(
                f"{tool_name} tool failed",
                doc_id=doc_id,
                error=str(e),
                exc_type=type(e).__name__
            )
            return None

    @classmethod
    async def invoke_relevant_tools(
        cls,
        context: ChatContext,
        user_id: str
    ) -> Dict:
        """
        Invoke relevant MCP tools based on context and return results.
        """
        results = {}

        # Get Redis cache
        try:
            cache = await get_redis_cache()
        except Exception as e:
            logger.warning(
                "Failed to get Redis cache for tool results",
                error=str(e),
                exc_type=type(e).__name__
            )
            cache = None

        # Skip if no tools enabled
        if not context.tools_enabled or not any(context.tools_enabled.values()):
            logger.debug("No tools enabled, skipping tool invocation")
            return results

        # Skip if no documents attached
        if not context.document_ids:
            logger.debug("No documents attached, skipping tool invocation")
            return results

        try:
            # Get MCP adapter for internal tool invocation
            mcp_adapter = get_mcp_adapter()
            tool_map = await mcp_adapter._get_tool_map()

            # 1. Audit File Tool
            if context.tools_enabled.get(TOOL_NAME_AUDIT, False) and TOOL_NAME_AUDIT in tool_map:
                for doc_id in context.document_ids:
                    audit_result = await cls._execute_tool_with_cache(
                        tool_name=TOOL_NAME_AUDIT,
                        doc_id=doc_id,
                        user_id=user_id,
                        payload={
                            "doc_id": doc_id,
                            "policy_id": "auto",
                            "user_id": user_id
                        },
                        cache_params={"policy_id": "auto"},
                        tool_map=tool_map,
                        mcp_adapter=mcp_adapter,
                        cache=cache
                    )
                    
                    if audit_result:
                        results[f"{TOOL_NAME_AUDIT}_{doc_id}"] = audit_result
                        logger.info(
                            f"{TOOL_NAME_AUDIT} tool succeeded",
                            doc_id=doc_id,
                            findings_count=len(audit_result.get("findings", []))
                        )

            # 2. Excel Analyzer Tool
            if context.tools_enabled.get(TOOL_NAME_EXCEL, False) and TOOL_NAME_EXCEL in tool_map:
                from ..models.document import Document
                
                for doc_id in context.document_ids:
                    # Check if document is an Excel file and verify ownership
                    try:
                        doc = await Document.get(doc_id)
                        if not doc or str(doc.user_id) != user_id:
                            continue

                        is_excel = doc.content_type in [
                            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            "application/vnd.ms-excel"
                        ]

                        if not is_excel:
                            continue

                        excel_result = await cls._execute_tool_with_cache(
                            tool_name=TOOL_NAME_EXCEL,
                            doc_id=doc_id,
                            user_id=user_id,
                            payload={
                                "doc_id": doc_id,
                                "operations": ["stats", "preview"],
                                "user_id": user_id
                            },
                            cache_params={"operations": ["stats", "preview"]},
                            tool_map=tool_map,
                            mcp_adapter=mcp_adapter,
                            cache=cache
                        )

                        if excel_result:
                            results[f"{TOOL_NAME_EXCEL}_{doc_id}"] = excel_result
                            logger.info(
                                f"{TOOL_NAME_EXCEL} tool succeeded",
                                doc_id=doc_id
                            )
                            
                    except Exception as e:
                        logger.warning(
                            f"Error checking document for {TOOL_NAME_EXCEL}",
                            doc_id=doc_id,
                            error=str(e)
                        )
                        continue

            logger.info(
                "Tool invocation completed",
                tools_executed=len(results),
                user_id=user_id
            )

        except Exception as e:
            logger.error(
                "Failed to invoke tools",
                error=str(e),
                exc_type=type(e).__name__,
                exc_info=True
            )
            # Return empty results on error

        return results
