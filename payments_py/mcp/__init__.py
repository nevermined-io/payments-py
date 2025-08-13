"""
MCP integration for Nevermined Payments (Python).

Exposes the factory ``build_mcp_integration`` and small helpers.
"""

from .index import build_mcp_integration, MCPIntegration  # noqa: F401
from .utils.extra import (  # noqa: F401
    build_extra_from_http_headers,
    build_extra_from_http_request,
    build_extra_from_fastmcp_context,
)

__all__ = [
    "build_mcp_integration",
    "build_extra_from_http_headers",
    "build_extra_from_http_request",
    "build_extra_from_fastmcp_context",
    "MCPIntegration",
]
