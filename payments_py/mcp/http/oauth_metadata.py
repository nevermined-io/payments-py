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

from typing import Dict, List, Literal, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from ...environments import EnvironmentName, Environments
from ..types.http_types import (
    AuthorizationServerMetadata,
    McpProtectedResourceMetadata,
    OAuthConfig,
    OAuthUrls,
    OidcConfiguration,
    ProtectedResourceMetadata,
    ServerInfoOAuth,
    ServerInfoResponse,
)

# =============================================================================
# OAUTH URLS
# =============================================================================

#: The query parameter that tells the Nevermined web app WHICH API tier an OAuth
#: ceremony belongs to, and its two values. Each tier (sandbox / live) is its own
#: authorization server, but ONE web app serves the consent screens for both and
#: boots on whatever tier the user's browser last chose — Live by default. A bare
#: ``https://nevermined.app/oauth/authorize`` therefore sent a sandbox MCP server's
#: users to the LIVE consent screen, where the connector is not registered
#: ("Connector not authorized"). The tier is stated on the URL instead; RFC 6749
#: §3.1 obliges clients to retain the query component when they add their own
#: parameters. Same name and values as the Nevermined API's own RFC 8414 document
#: and the embed widget (nvm-monorepo#3430 / #1787).
OAUTH_TIER_PARAM = "network"
OAUTH_TIERS = ("sandbox", "live")
OAuthTier = Literal["sandbox", "live"]


def resolve_oauth_tier(
    environment: EnvironmentName, backend_url: str
) -> Optional[OAuthTier]:
    """The API tier an environment belongs to.

    The four named environments map directly. ``custom`` is derived from the host
    of the backend it will publish as ``token_endpoint``: a Nevermined API host has
    an ``api`` label immediately followed by the tier label —
    ``api.sandbox.nevermined.app``, ``<slug>.api.live.nevermined.app`` (branded
    per-org subdomains), ``mcp.api.sandbox.nevermined.dev`` — so that label pair
    is what is matched, never a bare ``sandbox`` anywhere in the host. When the
    host cannot be classified (a ``localhost`` stack, a proxy/CNAME in front of the
    API) the tier is **omitted**, not guessed: the URL stays the bare one, and the
    operator sets ``oauth_urls={"authorizationUri": "...?network=<tier>"}`` to say
    which tier that deployment is.

    Args:
        environment: The Nevermined environment name.
        backend_url: The backend the document publishes (used for ``custom`` only).

    Returns:
        ``"sandbox"``, ``"live"``, or ``None`` when it cannot be determined.
    """
    if environment in ("sandbox", "staging_sandbox"):
        return "sandbox"
    if environment in ("live", "staging_live"):
        return "live"
    try:
        # ``hostname`` is lowercased and carries no port/credentials/path. Only an
        # unbalanced IPv6 literal (``http://[::1``) makes ``urlsplit`` raise.
        labels = (urlsplit(backend_url).hostname or "").split(".")
    except ValueError:
        return None
    if "api" in labels:
        tier_after_api = labels[labels.index("api") + 1 :][:1]
        if tier_after_api and tier_after_api[0] in OAUTH_TIERS:
            return tier_after_api[0]  # type: ignore[return-value]
    return None


def _with_tier_param(authorize_url: str, tier: Optional[OAuthTier]) -> str:
    """Append ``?network=<tier>`` through the URL machinery, never an f-string.

    Splitting and re-encoding the query keeps ONE query string (an existing query,
    port or fragment on the frontend round-trips; blank values are kept). A frontend
    that ``urlsplit`` refuses — an unbalanced IPv6 literal in ``NVM_FRONTEND_URL`` —
    falls back to plain concatenation, the same shape the bare URL always had for
    that misconfiguration, matching the TypeScript SDK.
    """
    if tier is None:
        return authorize_url
    try:
        parts = urlsplit(authorize_url)
    except ValueError:
        sep = "&" if "?" in authorize_url else "?"
        return f"{authorize_url}{sep}{OAUTH_TIER_PARAM}={tier}"
    query = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k != OAUTH_TIER_PARAM
    ]
    query.append((OAUTH_TIER_PARAM, tier))
    return urlunsplit(parts._replace(query=urlencode(query)))


def _build_oauth_urls(
    frontend_url: str, backend_url: str, tier: Optional[OAuthTier]
) -> OAuthUrls:
    """Build OAuth URLs from frontend and backend URLs.

    - issuer and authorizationUri use the frontend (user-facing); authorizationUri
      carries the API tier (see :func:`resolve_oauth_tier`)
    - tokenUri, jwksUri, userinfoUri use the backend (API)

    Args:
        frontend_url: The frontend URL (e.g., https://nevermined.app).
        backend_url: The backend URL (e.g., https://api.sandbox.nevermined.app).
        tier: The API tier to stamp on the authorize URL, or ``None`` to omit it.

    Returns:
        OAuth URLs configuration dict.
    """
    # Remove trailing slashes
    frontend = frontend_url.rstrip("/")
    backend = backend_url.rstrip("/")

    return {
        "issuer": frontend,
        "authorizationUri": _with_tier_param(f"{frontend}/oauth/authorize", tier),
        "tokenUri": f"{backend}/oauth/token",
        "jwksUri": f"{backend}/.well-known/jwks.json",
        "userinfoUri": f"{backend}/oauth/userinfo",
    }


def _get_oauth_urls_for_environment(
    environment: EnvironmentName, backend_for_tier: Optional[str] = None
) -> OAuthUrls:
    """Get OAuth URLs for an environment.

    Uses frontend and backend URLs from Environments configuration. An unknown
    environment name falls back to ``sandbox`` as it always did; the fallback is
    now internally consistent (a sandbox ``token_endpoint`` AND a sandbox-tagged
    authorize URL).

    Args:
        environment: The Nevermined environment name.
        backend_for_tier: The backend the document will actually publish as
            ``token_endpoint`` — the environment's, or a ``tokenUri`` override.
            Under ``custom`` the tier follows THAT, so a server whose ``tokenUri``
            is overridden to ``api.sandbox.…`` never publishes a sandbox token
            endpoint next to a tier-blind authorize URL.

    Returns:
        OAuth URLs configuration dict.
    """
    effective: EnvironmentName = (
        environment if environment in Environments else "sandbox"
    )
    env_config = Environments[effective]
    return _build_oauth_urls(
        env_config.frontend,
        env_config.backend,
        resolve_oauth_tier(effective, backend_for_tier or env_config.backend),
    )


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
    # An overridden ``authorizationUri`` is published verbatim — the SDK cannot know
    # whether it is the Nevermined web app or a foreign AS, so an operator who
    # points it at the web app includes ``?network=`` themselves.
    base_urls = _get_oauth_urls_for_environment(
        environment, (overrides or {}).get("tokenUri")
    )
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

    enable_oauth_discovery = config.get("enableOAuthDiscovery", True)
    enable_client_registration = config.get("enableClientRegistration", True)
    enable_health_check = config.get("enableHealthCheck", True)

    endpoints: Dict[str, str] = {"mcp": f"{config['baseUrl']}/mcp"}
    if enable_health_check:
        endpoints["health"] = f"{config['baseUrl']}/health"
    if enable_client_registration:
        endpoints["register"] = f"{config['baseUrl']}/register"

    oauth_info: ServerInfoOAuth = {
        "authorization_endpoint": oauth_urls["authorizationUri"],
        "token_endpoint": oauth_urls["tokenUri"],
        "jwks_uri": oauth_urls["jwksUri"],
        "scopes": scopes,
    }
    # agentId is optional under the plan-centric model; omit client_id when absent.
    agent_id = config.get("agentId")
    if agent_id:
        oauth_info["client_id"] = agent_id
    if enable_oauth_discovery:
        oauth_info.update(
            {
                "authorization_server_metadata": f"{config['baseUrl']}/.well-known/oauth-authorization-server",
                "protected_resource_metadata": f"{config['baseUrl']}/.well-known/oauth-protected-resource",
                "openid_configuration": f"{config['baseUrl']}/.well-known/openid-configuration",
            }
        )
    if enable_client_registration:
        oauth_info["registration_endpoint"] = f"{config['baseUrl']}/register"

    return {
        "name": config.get("serverName") or "MCP Server",
        "version": version or "1.0.0",
        "description": description
        or "MCP server with Nevermined OAuth integration via Streamable HTTP",
        "endpoints": endpoints,
        "oauth": oauth_info,
        "tools": config.get("tools") or [],
        "resources": config.get("resources") or [],
        "prompts": config.get("prompts") or [],
    }
