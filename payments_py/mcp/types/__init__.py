"""
Type definitions for MCP module.

This module exports all type definitions for the MCP integration,
organized into three categories:

1. Paywall Types: Authentication, credits, and paywall configuration
2. Server Types: Simplified API for server management
3. HTTP Types: OAuth 2.1 and HTTP server configuration

Examples:
    >>> from payments_py.mcp.types import McpServerConfig, ToolHandler
    >>> from payments_py.mcp.types import OAuthConfig, ServerInfoResponse
    >>> from payments_py.mcp.types import PaywallOptions, CreditsOption
"""

# Paywall types (Advanced API)
from .paywall_types import (
    AuthResult,
    BasePaywallOptions,
    CreditsOption,
    PaywallContext,
    PaywallOptions,
    PromptOptions,
    ResourceOptions,
    ToolOptions,
)

# Server types (Simplified API)
from .server_types import (
    McpPromptConfig,
    McpRegistrationOptions,
    McpResourceConfig,
    McpServerConfig,
    McpServerResult,
    McpToolConfig,
    PromptContext,
    PromptHandler,
    PromptRegistration,
    ResourceContext,
    ResourceHandler,
    ResourceRegistration,
    ServerInfo,
    ToolContext,
    ToolHandler,
    ToolRegistration,
)

# HTTP/OAuth types
from .http_types import (
    DEFAULT_OAUTH_SCOPES,
    AuthorizationServerMetadata,
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    HttpRouterConfig,
    HttpServerConfig,
    HttpServerResult,
    McpProtectedResourceMetadata,
    OAuthConfig,
    OAuthScope,
    OAuthUrls,
    OidcConfiguration,
    ProtectedResourceMetadata,
    ServerInfoResponse,
)

__all__ = [
    # Paywall types
    "AuthResult",
    "BasePaywallOptions",
    "CreditsOption",
    "PaywallContext",
    "PaywallOptions",
    "PromptOptions",
    "ResourceOptions",
    "ToolOptions",
    # Server types
    "McpToolConfig",
    "McpResourceConfig",
    "McpPromptConfig",
    "McpRegistrationOptions",
    "ToolHandler",
    "ResourceHandler",
    "PromptHandler",
    "McpServerConfig",
    "McpServerResult",
    "ServerInfo",
    "ToolContext",
    "ResourceContext",
    "PromptContext",
    "ToolRegistration",
    "ResourceRegistration",
    "PromptRegistration",
    # HTTP/OAuth types
    "OAuthUrls",
    "OAuthScope",
    "OAuthConfig",
    "HttpRouterConfig",
    "HttpServerConfig",
    "HttpServerResult",
    "ProtectedResourceMetadata",
    "McpProtectedResourceMetadata",
    "AuthorizationServerMetadata",
    "OidcConfiguration",
    "ClientRegistrationRequest",
    "ClientRegistrationResponse",
    "ServerInfoResponse",
    "DEFAULT_OAUTH_SCOPES",
]
