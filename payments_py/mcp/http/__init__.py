"""
HTTP module for MCP OAuth 2.1 integration.

This module provides all the building blocks for adding OAuth 2.1 support
to MCP servers, from low-level metadata generators to high-level routers.

Components:
    - OAuth Metadata: Pure functions to generate OAuth discovery responses
    - Client Registration: OAuth 2.0 Dynamic Client Registration (RFC 7591)
    - OAuth Router: FastAPI router with all OAuth endpoints
    - Session Manager: Manages MCP SSE sessions
    - MCP Handlers: HTTP handlers for POST/GET/DELETE /mcp

Examples:
    >>> from payments_py.mcp.http import get_oauth_urls, create_oauth_router
    >>> urls = get_oauth_urls("staging_sandbox")
    >>> router = create_oauth_router({
    ...     "baseUrl": "http://localhost:5001",
    ...     "agentId": "agent_123",
    ...     "environment": "staging_sandbox"
    ... })
"""

# OAuth metadata generators
from .oauth_metadata import (
    build_authorization_server_metadata,
    build_mcp_protected_resource_metadata,
    build_oidc_configuration,
    build_protected_resource_metadata,
    build_server_info_response,
    get_oauth_urls,
)

# Client registration
from .client_registration import (
    ClientRegistrationError,
    is_client_registration_request,
    process_client_registration,
    validate_client_registration_request,
)

# OAuth router
from .oauth_router import (
    create_cors_middleware,
    create_http_logging_middleware,
    create_json_middleware,
    create_oauth_router,
    create_require_auth_middleware,
)

# Session management
from .session_manager import (
    RequestContext,
    SessionManager,
    SessionManagerConfig,
    create_session_manager,
)

# MCP handlers
from .mcp_handler import (
    create_delete_mcp_handler,
    create_get_mcp_handler,
    create_post_mcp_handler,
    get_current_request_context,
    mount_mcp_handlers,
    request_context_storage,
)

__all__ = [
    # OAuth metadata
    "get_oauth_urls",
    "build_protected_resource_metadata",
    "build_mcp_protected_resource_metadata",
    "build_authorization_server_metadata",
    "build_oidc_configuration",
    "build_server_info_response",
    # Client registration
    "is_client_registration_request",
    "validate_client_registration_request",
    "process_client_registration",
    "ClientRegistrationError",
    # OAuth router
    "create_oauth_router",
    "create_cors_middleware",
    "create_json_middleware",
    "create_require_auth_middleware",
    "create_http_logging_middleware",
    # Session management
    "SessionManager",
    "SessionManagerConfig",
    "RequestContext",
    "create_session_manager",
    # MCP handlers
    "create_post_mcp_handler",
    "create_get_mcp_handler",
    "create_delete_mcp_handler",
    "mount_mcp_handlers",
    "get_current_request_context",
    "request_context_storage",
]
