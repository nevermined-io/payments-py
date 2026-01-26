"""
Type definitions for MCP HTTP server and OAuth 2.1 integration.

This module defines all types for the automatic OAuth endpoints and HTTP
server functionality, including OAuth 2.1 discovery, client registration,
and MCP-specific metadata.

Standards Implemented:
    - RFC 8414: OAuth 2.0 Authorization Server Metadata
    - RFC 9728: OAuth 2.0 Protected Resource Metadata
    - RFC 7591: OAuth 2.0 Dynamic Client Registration
    - OpenID Connect Discovery 1.0

Examples:
    >>> from payments_py.mcp.types import OAuthConfig, ServerInfoResponse
    >>> config: OAuthConfig = {
    ...     "baseUrl": "http://localhost:5001",
    ...     "agentId": "abc123",
    ...     "environment": "staging"
    ... }
"""

from typing import Any, Dict, List, Literal, Optional, Union
from typing_extensions import TypedDict

from ...environments import EnvironmentName

# =============================================================================
# OAUTH URLS AND SCOPES
# =============================================================================


class OAuthUrls(TypedDict):
    """OAuth URLs configuration for Nevermined authorization server.

    These URLs are used to build the OAuth discovery metadata and are
    environment-specific (staging, production, etc.).

    Attributes:
        issuer: The issuer identifier (e.g., https://nevermined.app).
        authorizationUri: OAuth authorization endpoint URL.
        tokenUri: OAuth token endpoint URL.
        jwksUri: JSON Web Key Set endpoint URL.
        userinfoUri: OpenID Connect userinfo endpoint URL.
    """

    issuer: str
    authorizationUri: str
    tokenUri: str
    jwksUri: str
    userinfoUri: str


# Default OAuth scopes supported by MCP integration
DEFAULT_OAUTH_SCOPES = [
    "openid",
    "profile",
    "credits",
    "mcp:read",
    "mcp:write",
    "mcp:tools",
]

OAuthScope = Literal[
    "openid",
    "profile",
    "credits",
    "mcp:read",
    "mcp:write",
    "mcp:tools",
]


# =============================================================================
# OAUTH CONFIGURATION
# =============================================================================


class OAuthConfig(TypedDict, total=False):
    """Configuration for OAuth endpoints and metadata.

    Attributes:
        baseUrl: Base URL of the MCP server (e.g., http://localhost:5001).
        agentId: Agent ID (client_id) for OAuth flows.
        environment: Nevermined environment to derive OAuth URLs.
        oauthUrls: Custom OAuth URLs (overrides environment defaults).
        scopes: Scopes supported by this server. Defaults to DEFAULT_OAUTH_SCOPES.
        serverName: Server name for MCP protocol.
        tools: List of tool names exposed by this server.
        resources: List of resource URIs exposed by this server.
        prompts: List of prompt names exposed by this server.
        protocolVersion: MCP protocol version.
    """

    baseUrl: str  # Required
    agentId: str  # Required
    environment: EnvironmentName  # Required
    oauthUrls: Optional[Dict[str, str]]
    scopes: Optional[List[str]]
    serverName: Optional[str]
    tools: Optional[List[str]]
    resources: Optional[List[str]]
    prompts: Optional[List[str]]
    protocolVersion: Optional[str]


class HttpRouterConfig(TypedDict, total=False):
    """Configuration for the HTTP router.

    Extends OAuthConfig with additional router-specific options.

    Attributes:
        baseUrl: Base URL of the MCP server (required).
        agentId: Agent ID for OAuth flows (required).
        environment: Nevermined environment (required).
        enableOAuthDiscovery: Enable OAuth discovery endpoints (/.well-known/*).
                             Defaults to True.
        enableClientRegistration: Enable dynamic client registration (/register).
                                 Defaults to True.
        enableHealthCheck: Enable health check endpoint (/health).
                          Defaults to True.
        enableServerInfo: Enable server info endpoint (/).
                         Defaults to True.
        corsOrigins: Custom CORS origins. Defaults to '*'.
    """

    baseUrl: str  # Required
    agentId: str  # Required
    environment: EnvironmentName  # Required
    oauthUrls: Optional[Dict[str, str]]
    scopes: Optional[List[str]]
    serverName: Optional[str]
    tools: Optional[List[str]]
    resources: Optional[List[str]]
    prompts: Optional[List[str]]
    protocolVersion: Optional[str]
    enableOAuthDiscovery: Optional[bool]
    enableClientRegistration: Optional[bool]
    enableHealthCheck: Optional[bool]
    enableServerInfo: Optional[bool]
    corsOrigins: Union[str, List[str], None]


class HttpServerConfig(TypedDict, total=False):
    """Configuration for the managed HTTP server.

    Extends HttpRouterConfig with server-specific options.

    Attributes:
        port: Port to listen on (required).
        host: Host to bind to. Defaults to '0.0.0.0'.
    """

    baseUrl: str  # Required
    agentId: str  # Required
    environment: EnvironmentName  # Required
    port: int  # Required
    host: Optional[str]
    oauthUrls: Optional[Dict[str, str]]
    scopes: Optional[List[str]]
    serverName: Optional[str]
    tools: Optional[List[str]]
    resources: Optional[List[str]]
    prompts: Optional[List[str]]
    protocolVersion: Optional[str]
    enableOAuthDiscovery: Optional[bool]
    enableClientRegistration: Optional[bool]
    enableHealthCheck: Optional[bool]
    enableServerInfo: Optional[bool]
    corsOrigins: Union[str, List[str], None]


class HttpServerResult(TypedDict):
    """Result returned when starting the managed HTTP server.

    Attributes:
        server: The underlying HTTP server instance (uvicorn.Server).
        app: The FastAPI application instance.
        stop: Async function to stop the server gracefully.
        baseUrl: The base URL of the running server.
        port: The port the server is listening on.
    """

    server: Any  # uvicorn.Server
    app: Any  # fastapi.FastAPI
    stop: Any  # Callable[[], Awaitable[None]]
    baseUrl: str
    port: int


# =============================================================================
# OAUTH METADATA (RFC 8414, RFC 9728)
# =============================================================================


class ProtectedResourceMetadata(TypedDict, total=False):
    """OAuth Protected Resource Metadata (RFC 9728).

    This metadata describes the protected resource (MCP server) and its
    authorization requirements.

    Attributes:
        resource: The protected resource identifier.
        authorization_servers: List of authorization server issuer URLs.
        scopes_supported: List of scopes supported by this resource.
        bearer_methods_supported: Bearer token methods supported.
        resource_documentation: Optional URL to resource documentation.
    """

    resource: str
    authorization_servers: List[str]
    scopes_supported: List[str]
    bearer_methods_supported: List[str]
    resource_documentation: Optional[str]


class McpProtectedResourceMetadata(TypedDict, total=False):
    """MCP-specific Protected Resource Metadata.

    Extends ProtectedResourceMetadata with MCP-specific fields.

    Attributes:
        resource: The protected resource identifier.
        authorization_servers: List of authorization server issuer URLs.
        scopes_supported: List of scopes supported by this resource.
        bearer_methods_supported: Bearer token methods supported.
        resource_documentation: Optional URL to resource documentation.
        scopes_required: Scopes required to access this resource.
        mcp_capabilities: MCP-specific capabilities (tools, protocol version).
    """

    resource: str
    authorization_servers: List[str]
    scopes_supported: List[str]
    bearer_methods_supported: List[str]
    resource_documentation: Optional[str]
    scopes_required: Optional[List[str]]
    mcp_capabilities: Optional[Dict[str, Any]]


class AuthorizationServerMetadata(TypedDict, total=False):
    """OAuth Authorization Server Metadata (RFC 8414).

    This metadata describes the OAuth 2.1 authorization server capabilities.

    Attributes:
        issuer: The authorization server's issuer identifier.
        authorization_endpoint: OAuth authorization endpoint URL.
        token_endpoint: OAuth token endpoint URL.
        registration_endpoint: Dynamic client registration endpoint URL.
        jwks_uri: JSON Web Key Set endpoint URL.
        response_types_supported: Response types supported.
        grant_types_supported: Grant types supported.
        code_challenge_methods_supported: PKCE methods supported.
        scopes_supported: Scopes supported by the authorization server.
        token_endpoint_auth_methods_supported: Token endpoint auth methods.
        subject_types_supported: Subject identifier types supported.
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: Optional[str]
    jwks_uri: str
    response_types_supported: List[str]
    grant_types_supported: List[str]
    code_challenge_methods_supported: List[str]
    scopes_supported: List[str]
    token_endpoint_auth_methods_supported: List[str]
    subject_types_supported: List[str]


class OidcConfiguration(TypedDict, total=False):
    """OpenID Connect Discovery Metadata.

    Extends AuthorizationServerMetadata with OIDC-specific fields.

    Attributes:
        issuer: The authorization server's issuer identifier.
        authorization_endpoint: OAuth authorization endpoint URL.
        token_endpoint: OAuth token endpoint URL.
        registration_endpoint: Dynamic client registration endpoint URL.
        jwks_uri: JSON Web Key Set endpoint URL.
        response_types_supported: Response types supported.
        grant_types_supported: Grant types supported.
        code_challenge_methods_supported: PKCE methods supported.
        scopes_supported: Scopes supported.
        token_endpoint_auth_methods_supported: Token endpoint auth methods.
        subject_types_supported: Subject identifier types supported.
        userinfo_endpoint: OIDC userinfo endpoint URL.
        id_token_signing_alg_values_supported: ID token signing algorithms.
        claims_supported: Claims supported in ID tokens.
    """

    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    registration_endpoint: Optional[str]
    jwks_uri: str
    response_types_supported: List[str]
    grant_types_supported: List[str]
    code_challenge_methods_supported: List[str]
    scopes_supported: List[str]
    token_endpoint_auth_methods_supported: List[str]
    subject_types_supported: List[str]
    userinfo_endpoint: Optional[str]
    id_token_signing_alg_values_supported: Optional[List[str]]
    claims_supported: Optional[List[str]]


# =============================================================================
# CLIENT REGISTRATION (RFC 7591)
# =============================================================================


class ClientRegistrationRequest(TypedDict, total=False):
    """OAuth Dynamic Client Registration request (RFC 7591).

    Attributes:
        redirect_uris: List of redirect URIs (required).
        client_name: Human-readable client name.
        client_uri: URL of the client's homepage.
        logo_uri: URL of the client's logo.
        scope: Space-separated list of requested scopes.
        grant_types: List of grant types the client will use.
        response_types: List of response types the client will use.
        token_endpoint_auth_method: Auth method for token endpoint.
        contacts: List of contact email addresses.
    """

    redirect_uris: List[str]  # Required
    client_name: Optional[str]
    client_uri: Optional[str]
    logo_uri: Optional[str]
    scope: Optional[str]
    grant_types: Optional[List[str]]
    response_types: Optional[List[str]]
    token_endpoint_auth_method: Optional[str]
    contacts: Optional[List[str]]


class ClientRegistrationResponse(TypedDict, total=False):
    """OAuth Dynamic Client Registration response (RFC 7591).

    Attributes:
        client_id: The registered client identifier.
        client_id_issued_at: Timestamp when client_id was issued.
        client_name: Human-readable client name.
        redirect_uris: List of registered redirect URIs.
        scope: Space-separated list of granted scopes.
        grant_types: List of grant types the client can use.
        response_types: List of response types the client can use.
        token_endpoint_auth_method: Auth method for token endpoint.
        client_secret: Client secret (if applicable).
        client_secret_expires_at: Timestamp when client_secret expires.
        client_uri: URL of the client's homepage.
        logo_uri: URL of the client's logo.
        contacts: List of contact email addresses.
    """

    client_id: str
    client_id_issued_at: int
    client_name: Optional[str]
    redirect_uris: List[str]
    scope: Optional[str]
    grant_types: Optional[List[str]]
    response_types: Optional[List[str]]
    token_endpoint_auth_method: Optional[str]
    client_secret: Optional[str]
    client_secret_expires_at: Optional[int]
    client_uri: Optional[str]
    logo_uri: Optional[str]
    contacts: Optional[List[str]]


# =============================================================================
# SERVER INFO
# =============================================================================


class ServerInfoEndpoints(TypedDict, total=False):
    """Endpoints information for server info response.

    Attributes:
        mcp: MCP endpoint URL.
        health: Health check endpoint URL.
        register: Client registration endpoint URL.
    """

    mcp: str
    health: Optional[str]
    register: Optional[str]


class ServerInfoOAuth(TypedDict, total=False):
    """OAuth information for server info response.

    Attributes:
        authorization_server_metadata: OAuth AS metadata endpoint URL.
        protected_resource_metadata: Protected resource metadata endpoint URL.
        openid_configuration: OIDC configuration endpoint URL.
        authorization_endpoint: OAuth authorization endpoint URL.
        token_endpoint: OAuth token endpoint URL.
        jwks_uri: JWKS endpoint URL.
        registration_endpoint: Client registration endpoint URL.
        client_id: The agent's client_id.
        scopes: List of supported scopes.
    """

    authorization_server_metadata: str
    protected_resource_metadata: str
    openid_configuration: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    registration_endpoint: Optional[str]
    client_id: str
    scopes: List[str]


class ServerInfoResponse(TypedDict, total=False):
    """Server info response for the root endpoint.

    Attributes:
        name: Server name.
        version: Server version.
        description: Server description.
        endpoints: Available endpoints (mcp, health, register).
        oauth: OAuth configuration information.
        tools: List of registered tool names.
        resources: List of registered resource URIs.
        prompts: List of registered prompt names.
    """

    name: str
    version: str
    description: Optional[str]
    endpoints: ServerInfoEndpoints
    oauth: Optional[ServerInfoOAuth]
    tools: Optional[List[str]]
    resources: Optional[List[str]]
    prompts: Optional[List[str]]
