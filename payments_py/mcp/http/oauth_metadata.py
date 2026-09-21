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
    >>> urls["issuer"]
    'https://api.sandbox.nevermined.dev'
"""

import logging
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
    operator states the tier through the ``oauthUrls`` option — the camelCase key
    ``McpServerConfig`` / ``HttpRouterConfig`` actually read —
    ``oauthUrls={"authorizationUri": "<webapp>/oauth/authorize?network=<tier>"}``,
    on ``payments.mcp.start()`` or ``create_oauth_router()``.

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


def _origin_of(url: str) -> Optional[str]:
    """The origin of ``url`` — scheme + lower-cased host + non-default port — or ``None``.

    ``None`` when ``urlsplit`` raises, when there is no scheme or host (a scheme-less
    ``api.sandbox.nevermined.app`` parses as a bare path; ``localhost:3001`` parses with
    ``localhost`` as the scheme and no host), or when ``.port`` raises on a non-numeric
    or out-of-range port. For the ASCII hosts Nevermined serves the result equals the
    web app's ``new URL(url).origin`` (userinfo dropped, default port dropped, IPv6
    re-bracketed); Python does no IDNA/percent canonicalisation, which never arises
    on those hosts.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = parts.hostname  # already lower-cased; IPv6 comes back without brackets
    if not scheme or not host:
        return None
    if ":" in host:
        host = f"[{host}]"
    if port is not None and port != {"http": 80, "https": 443}.get(scheme):
        host = f"{host}:{port}"
    return f"{scheme}://{host}"


def _canonical_nevermined_origin(backend_url: str) -> Optional[str]:
    """The canonical Nevermined API origin a backend host stands for, else ``None``.

    ``<slug>.api.live.nevermined.app`` (a branded per-org subdomain) and
    ``mcp.api.sandbox.nevermined.dev`` serve the same API as
    ``api.<tier>.nevermined.<tld>`` — and that canonical origin is what the two parties an
    issuer must agree with actually use: the API's own RFC 8414 document anchors
    ``issuer`` on ``API_HOST``, never the request host, and the web app returns RFC 9207
    ``iss`` from its fixed per-tier config. Publishing the branded origin would fail
    every RFC 9207 client's simple-string compare (payments-py#292 review). The suffix
    requirement is deliberate: this derives a HOST, and only a Nevermined host has a
    canonical form.
    """
    tier = resolve_oauth_tier("custom", backend_url)
    if tier is None:
        return None
    try:
        # A trailing-dot FQDN (``api.sandbox.nevermined.app.``) is the same host to DNS;
        # keep the suffix checks from missing it and republishing a one-byte-off issuer.
        hostname = (urlsplit(backend_url).hostname or "").rstrip(".")
    except ValueError:
        return None
    environment: Optional[EnvironmentName]
    if hostname.endswith(".nevermined.app"):
        environment = tier
    elif hostname.endswith(".nevermined.dev"):
        environment = "staging_live" if tier == "live" else "staging_sandbox"
    else:
        environment = None
    return _origin_of(Environments[environment].backend) if environment else None


# Warned once per DISTINCT value (a changed typo re-alerts), never when the operator has already
# set ``oauthUrls.issuer`` — the remedy the warning names — and not for a loopback host (a local
# stack, not a proxy for the real API).
_issuer_warned: set = set()


def _warn_issuer_once(key: str, message: str) -> None:
    if key in _issuer_warned:
        return
    _issuer_warned.add(key)
    logging.getLogger(__name__).warning(message)


def _is_loopback(origin: str) -> bool:
    try:
        host = urlsplit(origin).hostname
    except ValueError:
        return False
    return host in ("localhost", "127.0.0.1", "::1")


def _issuer_for(
    effective: EnvironmentName,
    published_backend: str,
    env_backend: str,
    issuer_overridden: bool = False,
) -> str:
    """The RFC 8414 issuer identifier of the authorization server a document describes.

    It is the ORIGIN of the Nevermined API the document points at — the value the API's
    own document publishes and the web app returns as RFC 9207 ``iss`` on every
    authorization response, which an RFC 9207 client compares with the discovered
    ``issuer`` by SIMPLE STRING comparison and rejects on any difference. So:

    - a NAMED environment is that identity — its canonical backend origin, whatever
      ``tokenUri`` override sits in front of it (a same-tier proxy is still the same
      authorization server; a cross-tier override is a misconfiguration);
    - ``custom`` follows the backend the document PUBLISHES (a ``tokenUri`` override,
      else its own): the canonical Nevermined origin when that host classifies, else
      the host's own origin, else — unparsable or scheme-less — the environment
      backend's origin, else the raw string minus its trailing slash, warned once. A
      metadata endpoint never raises.
    """
    if effective != "custom":
        return _origin_of(env_backend) or env_backend.rstrip("/")
    canonical = _canonical_nevermined_origin(published_backend)
    if canonical:
        return canonical
    own = _origin_of(published_backend) or _origin_of(env_backend)
    if own:
        # The right value for a genuinely foreign API — and the WRONG one for a proxy/CNAME
        # in front of the real Nevermined API (``https://gw.corp.com`` → the web app still
        # returns ``iss = https://api.sandbox.nevermined.app``, so every RFC 9207 client
        # rejects the code). The SDK cannot tell the two apart, so it says what it derived
        # and names the remedy (payments-py#292 review).
        if not issuer_overridden and not _is_loopback(own):
            _warn_issuer_once(
                own,
                f"[Nevermined] OAuth issuer derived from backend host "
                f"'{urlsplit(published_backend).netloc or published_backend}' as '{own}'. "
                "If that host is a proxy or gateway in front of a Nevermined API rather than "
                "the API itself, set oauthUrls.issuer (and oauthUrls.tokenUri) to that API's "
                "real origin — otherwise the issuer will not match the iss the authorization "
                "server returns.",
            )
        return own
    raw = published_backend.rstrip("/")
    if not issuer_overridden:
        _warn_issuer_once(
            raw,
            f"[Nevermined] Could not derive an OAuth issuer from backend '{published_backend}' "
            f"— publishing '{raw}'. Set oauthUrls.issuer (and oauthUrls.tokenUri) to the API "
            "origin of this deployment's tier.",
        )
    return raw


def _build_oauth_urls(
    frontend_url: str,
    backend_url: str,
    tier: Optional[OAuthTier],
    issuer: str,
) -> OAuthUrls:
    """Build OAuth URLs from frontend and backend URLs.

    - authorizationUri uses the frontend (the user-facing consent page) and carries
      the API tier (see :func:`resolve_oauth_tier`)
    - issuer, tokenUri, jwksUri, userinfoUri use the backend — the API is the
      authorization server

    ``issuer`` used to be the FRONTEND origin — identical for both tiers, since one
    web app serves both consent screens — while ``token_endpoint`` and the API's own
    RFC 8414 document named the backend. That was a tier-blind identifier, and once
    the web app started returning RFC 9207 ``iss`` = the API origin
    (nvm-monorepo#3532) it made every RFC 9207 client that discovered through this
    server's well-known reject its authorization responses (payments-py#291).

    Args:
        frontend_url: The frontend URL (e.g., https://nevermined.app).
        backend_url: The backend URL (e.g., https://api.sandbox.nevermined.app).
        tier: The API tier to stamp on the authorize URL, or ``None`` to omit it.
        issuer: The issuer identifier (see :func:`_issuer_for`).

    Returns:
        OAuth URLs configuration dict.
    """
    # Remove trailing slashes
    frontend = frontend_url.rstrip("/")
    backend = backend_url.rstrip("/")

    return {
        "issuer": issuer,
        "authorizationUri": _with_tier_param(f"{frontend}/oauth/authorize", tier),
        "tokenUri": f"{backend}/oauth/token",
        "jwksUri": f"{backend}/.well-known/jwks.json",
        "userinfoUri": f"{backend}/oauth/userinfo",
    }


def _get_oauth_urls_for_environment(
    environment: EnvironmentName,
    backend_for_tier: Optional[str] = None,
    issuer_overridden: bool = False,
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
    backend = backend_for_tier or env_config.backend
    return _build_oauth_urls(
        env_config.frontend,
        env_config.backend,
        resolve_oauth_tier(effective, backend),
        _issuer_for(effective, backend, env_config.backend, issuer_overridden),
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
        'https://api.sandbox.nevermined.dev'

        >>> custom_urls = get_oauth_urls("sandbox", {"issuer": "https://custom.com"})
        >>> custom_urls["issuer"]
        'https://custom.com'
    """
    # An overridden ``authorizationUri`` is published verbatim — the SDK cannot know
    # whether it is the Nevermined web app or a foreign AS, so an operator who
    # points it at the web app includes ``?network=`` themselves.
    # Only a NON-EMPTY string overrides. ``{"issuer": os.getenv("OAUTH_ISSUER")}`` with the
    # variable unset used to merge ``None`` over the computed value and publish
    # ``"issuer": null`` in a REQUIRED RFC 8414 field — for an hour, under
    # ``Cache-Control: public`` (payments-py#292 review). Same for ``""``.
    clean = {
        k: v for k, v in (overrides or {}).items() if isinstance(v, str) and v != ""
    }
    base_urls = _get_oauth_urls_for_environment(
        environment, clean.get("tokenUri"), "issuer" in clean
    )
    if clean:
        base_urls.update(clean)  # type: ignore
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


def _iss_parameter_support(
    environment: EnvironmentName, overrides: Optional[Dict[str, str]]
) -> Dict[str, bool]:
    """RFC 9207 §3 — ``authorization_response_iss_parameter_supported``, only where TRUE.

    An authorization server that returns ``iss`` on every authorization response
    advertises the flag; §2.4 then has a client REJECT any response lacking ``iss``.
    For the four named environments the consent page is the Nevermined web app,
    which has returned ``iss`` (= the canonical API origin these documents publish as
    ``issuer``) on every response since nvm-monorepo#3532 — the API's own document
    advertises the same flag. It is OMITTED for ``custom`` (the frontend may be an
    older or self-hosted web app that does not return ``iss``) and whenever
    ``oauthUrls.authorizationUri`` is overridden (the consent page is then an AS this
    SDK knows nothing about). Absent, never ``False``: a client that sees no
    advertisement skips the check rather than failing it. payments-py#295.
    """
    # Same effective-environment rule as ``_get_oauth_urls_for_environment``: an
    # unknown name serves the sandbox documents, so it advertises what sandbox does.
    effective = environment if environment in Environments else "sandbox"
    consent_overridden = bool((overrides or {}).get("authorizationUri"))
    if effective != "custom" and not consent_overridden:
        return {"authorization_response_iss_parameter_supported": True}
    return {}


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
        'https://api.sandbox.nevermined.dev'
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
        **_iss_parameter_support(config["environment"], config.get("oauthUrls")),
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
        **_iss_parameter_support(config["environment"], config.get("oauthUrls")),
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
