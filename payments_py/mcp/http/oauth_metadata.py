"""
Pure functions to generate OAuth 2.1 metadata responses.

This module provides generators for OAuth discovery endpoints without any
framework dependencies, making them reusable across different HTTP servers.

Standards Implemented:
    - RFC 8414: OAuth 2.0 Authorization Server Metadata
    - RFC 9728: OAuth 2.0 Protected Resource Metadata
    - OpenID Connect Discovery 1.0

Examples:
    >>> from payments_py.mcp.http import get_oauth_urls
    >>> urls = get_oauth_urls("staging_sandbox")
    >>> print(urls["issuer"])
    'https://nevermined.dev'
"""

from typing import Dict, List, Optional

from ...environments import EnvironmentName, Environments
from ..types.http_types import (
    AuthorizationServerMetadata,
    McpProtectedResourceMetadata,
    OAuthConfig,
    OAuthUrls,
    OidcConfiguration,
    ProtectedResourceMetadata,
    ServerInfoResponse,
)

# =============================================================================
# OAUTH URLS
# =============================================================================


def _build_oauth_urls(frontend_url: str, backend_url: str) -> OAuthUrls:
    """Build OAuth URLs from frontend and backend URLs.

    - issuer and authorizationUri use the frontend (user-facing)
    - tokenUri, jwksUri, userinfoUri use the backend (API)

    Args:
        frontend_url: The frontend URL (e.g., https://nevermined.app).
        backend_url: The backend URL (e.g., https://api.sandbox.nevermined.app).

    Returns:
        OAuth URLs configuration dict.
    """
    # Remove trailing slashes
    frontend = frontend_url.rstrip("/")
    backend = backend_url.rstrip("/")

    return {
        "issuer": frontend,
        "authorizationUri": f"{frontend}/oauth/authorize",
        "tokenUri": f"{backend}/oauth/token",
        "jwksUri": f"{backend}/.well-known/jwks.json",
        "userinfoUri": f"{backend}/oauth/userinfo",
    }


def _get_oauth_urls_for_environment(environment: EnvironmentName) -> OAuthUrls:
    """Get OAuth URLs for an environment.

    Uses frontend and backend URLs from Environments configuration.

    Args:
        environment: The Nevermined environment name.

    Returns:
        OAuth URLs configuration dict.
    """
    env_config = Environments.get(environment, Environments["sandbox"])
    return _build_oauth_urls(env_config.frontend, env_config.backend)


def get_oauth_urls(
    environment: EnvironmentName, overrides: Optional[Dict[str, str]] = None
) -> OAuthUrls:
    """Get OAuth URLs for a given environment with optional overrides.

    Args:
        environment: The Nevermined environment name.
        overrides: Optional dict to override specific URLs.

    Returns:
        Complete OAuth URLs configuration.

    Examples:
        >>> urls = get_oauth_urls("staging_sandbox")
        >>> urls["issuer"]
        'https://nevermined.dev'

        >>> custom_urls = get_oauth_urls("sandbox", {"issuer": "https://custom.com"})
        >>> custom_urls["issuer"]
        'https://custom.com'
    """
    base_urls = _get_oauth_urls_for_environment(environment)
    if overrides:
        base_urls.update(overrides)  # type: ignore
    return base_urls


# =============================================================================
# DEFAULT SCOPES
# =============================================================================

# Default OAuth scopes supported by Nevermined MCP servers
_DEFAULT_SCOPES: List[str] = [
    "openid",
    "profile",
    "credits",
    "mcp:read",
    "mcp:write",
    "mcp:tools",
]


# =============================================================================
# METADATA BUILDERS
# =============================================================================


def build_protected_resource_metadata(config: OAuthConfig) -> ProtectedResourceMetadata:
    """Build Protected Resource Metadata (RFC 9728).

    This metadata tells OAuth clients about the protected resource.

    Args:
        config: OAuth configuration including baseUrl, agentId, and environment.

    Returns:
        Protected Resource Metadata response dict.

    Examples:
        >>> metadata = build_protected_resource_metadata({
        ...     "baseUrl": "http://localhost:5001",
        ...     "agentId": "agent_123",
        ...     "environment": "staging_sandbox"
        ... })
        >>> metadata["resource"]
        'http://localhost:5001'
    """
    scopes = config.get("scopes") or list(_DEFAULT_SCOPES)
    # Get OAuth URLs for validation (not used in this metadata directly)
    _ = get_oauth_urls(config["environment"], config.get("oauthUrls"))

    return {
        "resource": config["baseUrl"],
        "authorization_servers": [config["baseUrl"]],
        "scopes_supported": scopes,
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{config['baseUrl']}/",
    }


def build_mcp_protected_resource_metadata(
    config: OAuthConfig,
) -> McpProtectedResourceMetadata:
    """Build MCP-specific Protected Resource Metadata.

    Extends the base metadata with MCP capabilities information.

    Args:
        config: OAuth configuration including tools list and protocol version.

    Returns:
        MCP Protected Resource Metadata response dict.

    Examples:
        >>> metadata = build_mcp_protected_resource_metadata({
        ...     "baseUrl": "http://localhost:5001",
        ...     "agentId": "agent_123",
        ...     "environment": "staging_sandbox",
        ...     "tools": ["hello_world", "weather"]
        ... })
        >>> metadata["mcp_capabilities"]["tools"]
        ['hello_world', 'weather']
    """
    scopes = config.get("scopes") or list(_DEFAULT_SCOPES)
    # Get OAuth URLs for validation (not used in this metadata directly)
    _ = get_oauth_urls(config["environment"], config.get("oauthUrls"))

    return {
        "resource": f"{config['baseUrl']}/mcp",
        "authorization_servers": [config["baseUrl"]],
        "scopes_supported": scopes,
        "scopes_required": scopes,
        "bearer_methods_supported": ["header"],
        "resource_documentation": f"{config['baseUrl']}/",
        "mcp_capabilities": {
            "tools": config.get("tools") or [],
            "protocol_version": config.get("protocolVersion") or "2024-11-05",
        },
    }


def build_authorization_server_metadata(
    config: OAuthConfig,
) -> AuthorizationServerMetadata:
    """Build OAuth Authorization Server Metadata (RFC 8414).

    This metadata describes the OAuth authorization server configuration.

    Args:
        config: OAuth configuration.

    Returns:
        Authorization Server Metadata response dict.

    Examples:
        >>> metadata = build_authorization_server_metadata({
        ...     "baseUrl": "http://localhost:5001",
        ...     "agentId": "agent_123",
        ...     "environment": "staging_sandbox"
        ... })
        >>> metadata["issuer"]
        'https://nevermined.dev'
    """
    oauth_urls = get_oauth_urls(config["environment"], config.get("oauthUrls"))
    scopes = config.get("scopes") or list(_DEFAULT_SCOPES)

    return {
        "issuer": oauth_urls["issuer"],
        "authorization_endpoint": oauth_urls["authorizationUri"],
        "token_endpoint": oauth_urls["tokenUri"],
        "registration_endpoint": f"{config['baseUrl']}/register",
        "jwks_uri": oauth_urls["jwksUri"],
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "scopes_supported": scopes,
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "subject_types_supported": ["public"],
    }


def build_oidc_configuration(config: OAuthConfig) -> OidcConfiguration:
    """Build OpenID Connect Discovery Metadata.

    Provides OIDC-compatible configuration for clients that expect OpenID Connect.

    Args:
        config: OAuth configuration.

    Returns:
        OIDC Configuration response dict.

    Examples:
        >>> metadata = build_oidc_configuration({
        ...     "baseUrl": "http://localhost:5001",
        ...     "agentId": "agent_123",
        ...     "environment": "staging_sandbox"
        ... })
        >>> "openid" in metadata["scopes_supported"]
        True
    """
    oauth_urls = get_oauth_urls(config["environment"], config.get("oauthUrls"))
    scopes = config.get("scopes") or list(_DEFAULT_SCOPES)
    all_scopes = scopes if "openid" in scopes else ["openid"] + scopes

    return {
        "issuer": oauth_urls["issuer"],
        "authorization_endpoint": oauth_urls["authorizationUri"],
        "token_endpoint": oauth_urls["tokenUri"],
        "jwks_uri": oauth_urls["jwksUri"],
        "userinfo_endpoint": oauth_urls["userinfoUri"],
        "registration_endpoint": f"{config['baseUrl']}/register",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code", "refresh_token"],
        "code_challenge_methods_supported": ["S256"],
        "token_endpoint_auth_methods_supported": ["none", "client_secret_post"],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": ["RS256", "HS256"],
        "scopes_supported": all_scopes,
        "claims_supported": ["sub", "iss", "aud", "exp", "iat", "name", "email"],
    }


def build_server_info_response(
    config: OAuthConfig,
    version: Optional[str] = None,
    description: Optional[str] = None,
) -> ServerInfoResponse:
    """Build server info response for the root endpoint.

    Args:
        config: OAuth configuration.
        version: Server version. Defaults to '1.0.0'.
        description: Server description.

    Returns:
        Server info response dict.

    Examples:
        >>> info = build_server_info_response({
        ...     "baseUrl": "http://localhost:5001",
        ...     "agentId": "abc123",
        ...     "environment": "staging_sandbox",
        ...     "serverName": "my-mcp",
        ...     "tools": ["hello"]
        ... }, version="0.1.0")
        >>> info["name"]
        'my-mcp'
        >>> info["tools"]
        ['hello']
    """
    oauth_urls = get_oauth_urls(config["environment"], config.get("oauthUrls"))
    scopes = config.get("scopes") or list(_DEFAULT_SCOPES)

    return {
        "name": config.get("serverName") or "MCP Server",
        "version": version or "1.0.0",
        "description": description
        or "MCP server with Nevermined OAuth integration via Streamable HTTP",
        "endpoints": {
            "mcp": f"{config['baseUrl']}/mcp",
            "health": f"{config['baseUrl']}/health",
            "register": f"{config['baseUrl']}/register",
        },
        "oauth": {
            "authorization_server_metadata": f"{config['baseUrl']}/.well-known/oauth-authorization-server",
            "protected_resource_metadata": f"{config['baseUrl']}/.well-known/oauth-protected-resource",
            "openid_configuration": f"{config['baseUrl']}/.well-known/openid-configuration",
            "authorization_endpoint": oauth_urls["authorizationUri"],
            "token_endpoint": oauth_urls["tokenUri"],
            "jwks_uri": oauth_urls["jwksUri"],
            "registration_endpoint": f"{config['baseUrl']}/register",
            "client_id": config["agentId"],
            "scopes": scopes,
        },
        "tools": config.get("tools") or [],
        "resources": config.get("resources") or [],
        "prompts": config.get("prompts") or [],
    }
