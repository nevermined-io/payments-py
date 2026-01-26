"""
FastAPI Router for OAuth 2.1 endpoints.

This module provides a pre-configured FastAPI router with all OAuth discovery
and registration endpoints that can be mounted on any FastAPI application.

Standards:
    - RFC 8414: OAuth 2.0 Authorization Server Metadata
    - RFC 9728: OAuth 2.0 Protected Resource Metadata
    - RFC 7591: OAuth 2.0 Dynamic Client Registration
    - OpenID Connect Discovery 1.0

Examples:
    >>> from fastapi import FastAPI
    >>> from payments_py.mcp.http import create_oauth_router
    >>> app = FastAPI()
    >>> router = create_oauth_router({
    ...     "payments": payments,
    ...     "baseUrl": "http://localhost:5001",
    ...     "agentId": "agent_123",
    ...     "environment": "staging_sandbox"
    ... })
    >>> app.include_router(router)
"""

from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse

from ..types.http_types import HttpRouterConfig
from .client_registration import (
    ClientRegistrationError,
    is_client_registration_request,
    process_client_registration,
)
from .oauth_metadata import (
    build_authorization_server_metadata,
    build_mcp_protected_resource_metadata,
    build_oidc_configuration,
    build_protected_resource_metadata,
    build_server_info_response,
)

# =============================================================================
# ROUTER OPTIONS
# =============================================================================


class OAuthRouterOptions(HttpRouterConfig):
    """Options for creating the OAuth router.

    Extends HttpRouterConfig with additional router-specific fields.

    Attributes:
        payments: Payments instance for authentication.
        version: Server version for info endpoint.
        description: Server description for info endpoint.
        onLog: Optional logging callback (no logs by default).
    """

    payments: Any  # Payments instance
    version: Optional[str]
    description: Optional[str]
    onLog: Optional[Callable[[str], None]]


# =============================================================================
# ROUTER CREATION
# =============================================================================


def create_oauth_router(options: Dict[str, Any]) -> APIRouter:
    """Create a FastAPI router with OAuth 2.1 discovery and registration endpoints.

    This router can be mounted on any FastAPI application to add OAuth support.

    Args:
        options: Router configuration options dict (OAuthRouterOptions).

    Returns:
        FastAPI APIRouter with OAuth endpoints mounted.

    Examples:
        >>> from fastapi import FastAPI
        >>> from payments_py import Payments
        >>>
        >>> app = FastAPI()
        >>> payments = Payments(nvm_api_key="...", environment="staging_sandbox")
        >>>
        >>> # Create and mount the OAuth router
        >>> oauth_router = create_oauth_router({
        ...     "payments": payments,
        ...     "baseUrl": "http://localhost:5001",
        ...     "agentId": "agent_123",
        ...     "environment": "staging_sandbox",
        ...     "serverName": "my-mcp-server",
        ...     "tools": ["hello_world"]
        ... })
        >>>
        >>> app.include_router(oauth_router)
    """
    router = APIRouter()

    # Extract options
    base_url = options["baseUrl"]
    agent_id = options["agentId"]
    environment = options["environment"]
    server_name = options.get("serverName", "mcp-server")
    tools = options.get("tools", [])
    resources = options.get("resources", [])
    prompts = options.get("prompts", [])
    scopes = options.get("scopes")
    oauth_urls = options.get("oauthUrls")
    protocol_version = options.get("protocolVersion")
    enable_oauth_discovery = options.get("enableOAuthDiscovery", True)
    enable_client_registration = options.get("enableClientRegistration", True)
    enable_health_check = options.get("enableHealthCheck", True)
    enable_server_info = options.get("enableServerInfo", True)
    version = options.get("version", "1.0.0")
    description = options.get("description")
    on_log = options.get("onLog")

    # Optional logging helper (no-op if onLog not provided)
    def log(message: str) -> None:
        if on_log:
            on_log(message)

    # Build config object for metadata generators
    config: Dict[str, Any] = {
        "baseUrl": base_url,
        "agentId": agent_id,
        "environment": environment,
        "serverName": server_name,
        "tools": tools,
        "resources": resources,
        "prompts": prompts,
        "scopes": scopes,
        "oauthUrls": oauth_urls,
        "protocolVersion": protocol_version,
    }

    # --- OAuth Discovery Endpoints ---

    if enable_oauth_discovery:

        @router.get("/.well-known/oauth-protected-resource")
        async def protected_resource_metadata() -> JSONResponse:
            """Protected Resource Metadata (RFC 9728)."""
            log("GET /.well-known/oauth-protected-resource")
            metadata = build_protected_resource_metadata(config)
            return JSONResponse(
                content=metadata,
                headers={"Cache-Control": "public, max-age=3600"},
            )

        @router.get("/.well-known/oauth-protected-resource/mcp")
        async def mcp_protected_resource_metadata() -> JSONResponse:
            """MCP-specific Protected Resource Metadata."""
            log("GET /.well-known/oauth-protected-resource/mcp")
            metadata = build_mcp_protected_resource_metadata(config)
            return JSONResponse(
                content=metadata,
                headers={"Cache-Control": "public, max-age=3600"},
            )

        @router.get("/.well-known/oauth-authorization-server")
        async def authorization_server_metadata() -> JSONResponse:
            """OAuth Authorization Server Metadata (RFC 8414)."""
            log("GET /.well-known/oauth-authorization-server")
            metadata = build_authorization_server_metadata(config)
            return JSONResponse(
                content=metadata,
                headers={"Cache-Control": "public, max-age=3600"},
            )

        @router.get("/.well-known/openid-configuration")
        async def oidc_configuration() -> JSONResponse:
            """OpenID Connect Discovery (for OIDC compatibility)."""
            log("GET /.well-known/openid-configuration")
            metadata = build_oidc_configuration(config)
            return JSONResponse(
                content=metadata,
                headers={"Cache-Control": "public, max-age=3600"},
            )

    # --- Dynamic Client Registration ---

    if enable_client_registration:

        @router.post("/register")
        async def client_registration(request: Request) -> JSONResponse:
            """OAuth Dynamic Client Registration (RFC 7591)."""
            log("POST /register")
            try:
                # Parse request body
                body = await request.json()

                # Check if this is an OAuth registration request
                if not is_client_registration_request(body):
                    log("Invalid registration request")
                    return JSONResponse(
                        status_code=400,
                        content={
                            "error": "invalid_request",
                            "error_description": "Request body is not a valid client registration request",
                        },
                    )

                # Process registration
                response = await process_client_registration(body, config)
                log(f"Client registered: {response['client_id']}")

                # Return successful registration (201 Created)
                return JSONResponse(status_code=201, content=response)

            except ClientRegistrationError as error:
                log(f"Registration error: {error}")
                return JSONResponse(
                    status_code=error.status_code, content=error.to_json()
                )
            except Exception as error:
                log(f"Unexpected error: {error}")
                return JSONResponse(
                    status_code=500,
                    content={
                        "error": "server_error",
                        "error_description": str(error)
                        or "Internal server error during client registration",
                    },
                )

    # --- Health Check ---

    if enable_health_check:

        @router.get("/health")
        async def health_check() -> JSONResponse:
            """Health check endpoint."""
            log("GET /health")
            return JSONResponse(
                content={
                    "status": "ok",
                    "service": server_name,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                }
            )

    # --- Server Info ---

    if enable_server_info:

        @router.get("/")
        async def server_info() -> JSONResponse:
            """Server info endpoint."""
            log("GET /")
            info = build_server_info_response(config, version, description)
            return JSONResponse(content=info)

    return router


# =============================================================================
# MIDDLEWARE UTILITIES
# =============================================================================


def create_cors_middleware(origins: Union[str, List[str]] = "*") -> Dict[str, Any]:
    """Create CORS middleware configuration for FastAPI.

    Args:
        origins: Allowed origins. Defaults to '*' (all origins).

    Returns:
        Dict with CORS configuration for CORSMiddleware.

    Examples:
        >>> cors_config = create_cors_middleware("*")
        >>> cors_config["allow_origins"]
        ['*']

        >>> cors_config = create_cors_middleware(["http://localhost:3000"])
        >>> cors_config["allow_origins"]
        ['http://localhost:3000']
    """
    allow_origins = [origins] if isinstance(origins, str) else origins

    return {
        "allow_origins": allow_origins,
        "allow_credentials": True,
        "allow_methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": [
            "Origin",
            "X-Requested-With",
            "Content-Type",
            "Accept",
            "Authorization",
            "mcp-session-id",
            "mcp-protocol-version",
        ],
        "expose_headers": ["mcp-session-id"],
    }


def create_json_middleware():
    """Create a JSON parsing middleware for FastAPI.

    Note:
        FastAPI handles JSON parsing automatically, so this is a no-op
        placeholder for API compatibility with TypeScript.

    Returns:
        None (FastAPI handles JSON parsing by default).
    """
    # FastAPI handles JSON parsing automatically
    # This is a placeholder for API compatibility
    return None


def create_require_auth_middleware() -> Callable:
    """Create a middleware that requires a Bearer token in the Authorization header.

    Returns HTTP 401 if the token is missing or malformed.

    This is a lightweight check that only verifies presence of a token.
    Full validation (is the token valid? does the user have access?) is handled
    by with_paywall() when a tool is actually called.

    Returns:
        FastAPI dependency function for token requirement.

    Examples:
        >>> from fastapi import Depends
        >>> require_auth = create_require_auth_middleware()
        >>>
        >>> @app.post("/mcp")
        >>> async def mcp_handler(request: Request, _=Depends(require_auth)):
        ...     # Handler implementation
        ...     pass
    """

    async def require_auth_dependency(request: Request) -> None:
        """FastAPI dependency that checks for Bearer token.

        Args:
            request: FastAPI request object.

        Raises:
            HTTPException: If authorization is missing or invalid.
        """
        from fastapi import HTTPException

        auth_header = request.headers.get("authorization")

        if not auth_header:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "unauthorized",
                    "error_description": "Authorization header required",
                },
            )

        if not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "unauthorized",
                    "error_description": "Bearer token required",
                },
            )

        token = auth_header[7:].strip()
        if not token:
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "unauthorized",
                    "error_description": "Bearer token cannot be empty",
                },
            )

        # Token present and well-formed, continue
        # Full validation happens in with_paywall() when tools are called

    return require_auth_dependency


def create_http_logging_middleware(
    on_log: Optional[Callable[[str], None]] = None,
) -> Callable:
    """Create a middleware that logs all HTTP requests.

    Logs method, URL, IP address, and relevant headers.

    Args:
        on_log: Optional logging callback. If not provided, does nothing.

    Returns:
        FastAPI middleware function.

    Examples:
        >>> from fastapi import FastAPI
        >>> app = FastAPI()
        >>> log_middleware = create_http_logging_middleware(print)
        >>> app.middleware("http")(log_middleware)
    """

    async def http_logging_middleware(
        request: Request, call_next: Callable
    ) -> Response:
        """FastAPI middleware for HTTP request logging.

        Args:
            request: FastAPI request object.
            call_next: Next middleware/handler in the chain.

        Returns:
            Response from the next middleware/handler.
        """
        if not on_log:
            return await call_next(request)

        method = request.method
        url = str(request.url)
        ip = request.client.host if request.client else "unknown"
        timestamp = datetime.utcnow().isoformat() + "Z"

        # Extract relevant headers
        auth_header = request.headers.get("authorization")
        session_id = request.headers.get("mcp-session-id")
        protocol_version = request.headers.get("mcp-protocol-version")
        user_agent = request.headers.get("user-agent")

        # Build log message
        log_parts = [f"[{timestamp}]", method, url, f"IP: {ip}"]

        if auth_header:
            token_preview = (
                f"Bearer {auth_header[7:20]}..."
                if auth_header.startswith("Bearer ")
                else "Bearer [present]"
            )
            log_parts.append(f"Auth: {token_preview}")

        if session_id:
            log_parts.append(f"Session: {session_id}")

        if protocol_version:
            log_parts.append(f"MCP-Version: {protocol_version}")

        if user_agent:
            log_parts.append(f"User-Agent: {user_agent}")

        on_log(f"HTTP Request: {' | '.join(log_parts)}")

        response = await call_next(request)
        return response

    return http_logging_middleware
