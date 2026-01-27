"""
OAuth Dynamic Client Registration handler (RFC 7591).

This module handles client registration requests for MCP OAuth flows,
implementing the OAuth 2.0 Dynamic Client Registration Protocol.

Standards:
    - RFC 7591: OAuth 2.0 Dynamic Client Registration Protocol

Examples:
    >>> from payments_py.mcp.http import process_client_registration
    >>> response = await process_client_registration(
    ...     {"redirect_uris": ["http://localhost:3000/callback"]},
    ...     {"agentId": "agent_123", "baseUrl": "http://localhost:5001", "environment": "staging_sandbox"}
    ... )
    >>> response["client_id"]
    'agent_123'
"""

import secrets
import time
from typing import Any, Dict, List
from urllib.parse import urlparse

from ..types.http_types import (
    ClientRegistrationRequest,
    ClientRegistrationResponse,
    OAuthConfig,
)

# Default scopes for client registration
_DEFAULT_SCOPES: List[str] = [
    "openid",
    "profile",
    "credits",
    "mcp:read",
    "mcp:write",
    "mcp:tools",
]


# =============================================================================
# EXCEPTIONS
# =============================================================================


class ClientRegistrationError(Exception):
    """Validation error for client registration.

    Attributes:
        error_code: OAuth error code (e.g., 'invalid_request').
        message: Human-readable error message.
        status_code: HTTP status code. Defaults to 400.
    """

    def __init__(self, error_code: str, message: str, status_code: int = 400) -> None:
        """Initialize client registration error.

        Args:
            error_code: OAuth error code.
            message: Human-readable error message.
            status_code: HTTP status code. Defaults to 400.
        """
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code

    def to_json(self) -> Dict[str, str]:
        """Get the error response body.

        Returns:
            Dict with 'error' and 'error_description' keys.
        """
        return {"error": self.error_code, "error_description": str(self)}


# =============================================================================
# VALIDATION
# =============================================================================


def is_client_registration_request(body: Any) -> bool:
    """Check if a request body is an OAuth Dynamic Client Registration request.

    Args:
        body: The request body to check.

    Returns:
        True if the body looks like a client registration request.

    Examples:
        >>> is_client_registration_request({"redirect_uris": ["http://..."]})
        True
        >>> is_client_registration_request({})
        False
    """
    if not body or not isinstance(body, dict):
        return False

    return bool(
        body.get("redirect_uris")
        or body.get("grant_types")
        or body.get("token_endpoint_auth_method")
        or body.get("response_types")
        or body.get("client_name")
    )


def validate_client_registration_request(request: Dict[str, Any]) -> None:
    """Validate a client registration request.

    Args:
        request: The client registration request dict.

    Raises:
        ClientRegistrationError: If validation fails.

    Examples:
        >>> validate_client_registration_request({"redirect_uris": ["http://localhost"]})
        # No exception raised

        >>> validate_client_registration_request({})
        Traceback (most recent call last):
        ...
        ClientRegistrationError: redirect_uris is required and must be a non-empty array
    """
    # redirect_uris is required and must be a non-empty array
    redirect_uris = request.get("redirect_uris")
    if (
        not redirect_uris
        or not isinstance(redirect_uris, list)
        or len(redirect_uris) == 0
    ):
        raise ClientRegistrationError(
            "invalid_request",
            "redirect_uris is required and must be a non-empty array",
        )

    # Validate each redirect_uri is a valid URL
    for uri in redirect_uris:
        try:
            parsed = urlparse(uri)
            if not parsed.scheme or not parsed.netloc:
                raise ValueError("Invalid URL format")
        except (ValueError, AttributeError):
            raise ClientRegistrationError(
                "invalid_redirect_uri", f"Invalid redirect_uri: {uri}"
            )

    # Validate grant_types if provided
    valid_grant_types = ["authorization_code", "refresh_token", "client_credentials"]
    grant_types = request.get("grant_types")
    if grant_types:
        if not isinstance(grant_types, list):
            raise ClientRegistrationError(
                "invalid_client_metadata", "grant_types must be an array"
            )
        for grant_type in grant_types:
            if grant_type not in valid_grant_types:
                raise ClientRegistrationError(
                    "invalid_client_metadata", f"Unsupported grant_type: {grant_type}"
                )

    # Validate response_types if provided
    valid_response_types = ["code", "token"]
    response_types = request.get("response_types")
    if response_types:
        if not isinstance(response_types, list):
            raise ClientRegistrationError(
                "invalid_client_metadata", "response_types must be an array"
            )
        for response_type in response_types:
            if response_type not in valid_response_types:
                raise ClientRegistrationError(
                    "invalid_client_metadata",
                    f"Unsupported response_type: {response_type}",
                )

    # Validate token_endpoint_auth_method if provided
    valid_auth_methods = ["none", "client_secret_basic", "client_secret_post"]
    auth_method = request.get("token_endpoint_auth_method")
    if auth_method and auth_method not in valid_auth_methods:
        raise ClientRegistrationError(
            "invalid_client_metadata",
            f"Unsupported token_endpoint_auth_method: {auth_method}",
        )


# =============================================================================
# CLIENT SECRET GENERATION
# =============================================================================


def _generate_client_secret() -> str:
    """Generate a cryptographically secure client secret.

    Returns:
        A URL-safe base64-encoded random string (32 bytes).

    Examples:
        >>> secret = _generate_client_secret()
        >>> len(secret) > 0
        True
    """
    # Generate 32 random bytes and encode as URL-safe base64
    return secrets.token_urlsafe(32)


# =============================================================================
# CLIENT REGISTRATION PROCESSOR
# =============================================================================


async def process_client_registration(
    request: ClientRegistrationRequest, config: OAuthConfig
) -> ClientRegistrationResponse:
    """Process a client registration request and generate a response.

    This function validates the request and generates appropriate client
    credentials according to RFC 7591.

    Args:
        request: The validated client registration request dict.
        config: OAuth configuration including agentId, baseUrl, and scopes.

    Returns:
        Client registration response dict.

    Raises:
        ClientRegistrationError: If validation fails.

    Examples:
        >>> response = await process_client_registration(
        ...     {
        ...         "redirect_uris": ["http://localhost:3000/callback"],
        ...         "client_name": "My App"
        ...     },
        ...     {
        ...         "agentId": "agent_123",
        ...         "baseUrl": "http://localhost:5001",
        ...         "environment": "staging_sandbox"
        ...     }
        ... )
        >>> response["client_id"]
        'agent_123'
    """
    # Validate the request
    validate_client_registration_request(request)

    # Use agentId as client_id (consistent for this MCP server)
    client_id = config["agentId"]
    issued_at = int(time.time())

    # Determine auth method and if secret is needed
    auth_method = request.get("token_endpoint_auth_method") or "none"
    needs_secret = auth_method in ["client_secret_basic", "client_secret_post"]

    # Build base response
    scopes = config.get("scopes") or _DEFAULT_SCOPES
    response: ClientRegistrationResponse = {
        "client_id": client_id,
        "client_id_issued_at": issued_at,
        "client_name": request.get("client_name") or "MCP Client",
        "redirect_uris": request["redirect_uris"],
        "scope": request.get("scope") or " ".join(scopes),
        "grant_types": request.get("grant_types") or ["authorization_code"],
        "response_types": request.get("response_types") or ["code"],
        "token_endpoint_auth_method": auth_method,
    }

    # Generate client_secret if needed
    if needs_secret:
        response["client_secret"] = _generate_client_secret()
        response["client_secret_expires_at"] = 0  # 0 means never expires

    # Add optional fields if provided
    if request.get("client_uri"):
        response["client_uri"] = request["client_uri"]
    if request.get("logo_uri"):
        response["logo_uri"] = request["logo_uri"]
    if request.get("contacts"):
        response["contacts"] = request["contacts"]

    return response
