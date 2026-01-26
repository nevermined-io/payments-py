"""
MCP integration for Nevermined Payments (Python).

This module provides complete MCP integration with three distinct APIs:

1. **Decorator API** (recommended) - Wrapper around FastMCP with payments:
   - PaymentsMCP: Class that wraps FastMCP with credit redemption
   - @mcp.tool(credits=N): Register tools with automatic payment
   - @mcp.resource(uri, credits=N): Register resources with payment
   - @mcp.prompt(credits=N): Register prompts with payment

2. **Simplified API** - High-level server management:
   - payments.mcp.register_tool/resource/prompt(): Register handlers
   - payments.mcp.start(): Start complete MCP server with OAuth
   - payments.mcp.stop(): Stop server gracefully

3. **Advanced API** - Low-level control for custom implementations:
   - build_mcp_integration(): Factory function
   - MCPIntegration: Main integration class
   - build_extra_from_*(): Utilities for building MCP extra objects

Examples:
    Decorator API (recommended):
        >>> from payments_py import Payments
        >>> from payments_py.mcp import PaymentsMCP
        >>>
        >>> payments = Payments(nvm_api_key="...", environment="staging_sandbox")
        >>> mcp = PaymentsMCP(payments, name="my-server", agent_id="did:nv:...")
        >>>
        >>> @mcp.tool(credits=5)
        >>> def weather(city: str) -> str:
        ...     return f"Weather in {city}: 22°C"
        >>>
        >>> @mcp.resource("data://config", credits=2)
        >>> def get_config() -> str:
        ...     return '{"version": "1.0.0"}'
        >>>
        >>> mcp.run()

    Simplified API:
        >>> payments.mcp.register_tool("hello", {"description": "..."}, handler, {"credits": 1})
        >>> result = await payments.mcp.start({"port": 5001, "agentId": "...", "serverName": "..."})

    Advanced API:
        >>> payments.mcp.configure({"agentId": "...", "serverName": "..."})
        >>> protected = payments.mcp.with_paywall(handler, {"kind": "tool", "name": "hello"})
"""

# Core integration
from .index import MCPIntegration, build_mcp_integration  # noqa: F401

# Decorator-based API (wrapper around FastMCP)
from .payments_mcp import PaymentsMCP  # noqa: F401

# Utilities
from .utils.extra import (  # noqa: F401
    build_extra_from_fastmcp_context,
    build_extra_from_http_headers,
    build_extra_from_http_request,
)

# Types (re-export for convenience)
from .types import (  # noqa: F401
    AuthResult,
    CreditsOption,
    McpPromptConfig,
    McpRegistrationOptions,
    McpResourceConfig,
    McpServerConfig,
    McpServerResult,
    McpToolConfig,
    PaywallContext,
    PaywallOptions,
    PromptContext,
    PromptHandler,
    ResourceContext,
    ResourceHandler,
    ServerInfo,
    ToolContext,
    ToolHandler,
)

__all__ = [
    # Decorator API (recommended)
    "PaymentsMCP",
    # Core integration
    "build_mcp_integration",
    "MCPIntegration",
    # Utilities
    "build_extra_from_http_headers",
    "build_extra_from_http_request",
    "build_extra_from_fastmcp_context",
    # Types (commonly used)
    "McpServerConfig",
    "McpServerResult",
    "ServerInfo",
    "McpToolConfig",
    "McpResourceConfig",
    "McpPromptConfig",
    "McpRegistrationOptions",
    "ToolHandler",
    "ResourceHandler",
    "PromptHandler",
    "ToolContext",
    "ResourceContext",
    "PromptContext",
    "PaywallOptions",
    "PaywallContext",
    "CreditsOption",
    "AuthResult",
]
