"""
Utilities to work with request metadata and authorization headers.
"""

from typing import Any, Dict, Optional


def extract_auth_header(extra: Any) -> Optional[str]:
    """
    Extract the Authorization header from the MCP extra request info.
    Searches common locations used by different transports (HTTP, WS, stdio),
    but ONLY from headers-like containers.

    Args:
        extra: Extra object that may include headers in several nested shapes.

    Returns:
        The "Authorization" header value if present, otherwise ``None``.
    """
    candidate_headers = [
        (
            getattr(getattr(extra, "requestInfo", None), "headers", None)
            if hasattr(extra, "requestInfo")
            else (
                extra.get("requestInfo", {}).get("headers")
                if isinstance(extra, dict)
                else None
            )
        ),
        (
            getattr(getattr(extra, "request", None), "headers", None)
            if hasattr(extra, "request")
            else (
                extra.get("request", {}).get("headers")
                if isinstance(extra, dict)
                else None
            )
        ),
        (
            getattr(extra, "headers", None)
            if hasattr(extra, "headers")
            else (extra.get("headers") if isinstance(extra, dict) else None)
        ),
        (
            getattr(getattr(extra, "connection", None), "headers", None)
            if hasattr(extra, "connection")
            else (
                extra.get("connection", {}).get("headers")
                if isinstance(extra, dict)
                else None
            )
        ),
        (
            getattr(
                getattr(getattr(extra, "socket", None), "handshake", None),
                "headers",
                None,
            )
            if hasattr(extra, "socket")
            else (
                extra.get("socket", {}).get("handshake", {}).get("headers")
                if isinstance(extra, dict)
                else None
            )
        ),
    ]

    for headers in candidate_headers:
        if not headers:
            continue
        value = _get_header_case_insensitive(headers, "authorization")
        if value:
            return value
    return None


def _get_header_case_insensitive(headers: Dict[str, Any], name: str) -> Optional[str]:
    """Get header value by name, ignoring the case of the key.

    Args:
        headers: Mapping of header names to values.
        name: Target header name.

    Returns:
        Header value as a string if found, otherwise ``None``.
    """
    direct = (
        headers.get(name) or headers.get(name.lower()) or headers.get(name.capitalize())
    )
    value = direct
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    target = name.lower()
    for k, v in headers.items():
        if str(k).lower() == target:
            if isinstance(v, list) and v:
                return str(v[0])
            if isinstance(v, str):
                return v
    return None


def strip_bearer(header: str) -> str:
    """Remove a leading "Bearer " prefix from an authorization header value."""
    return header[7:].strip() if header.startswith("Bearer ") else header
