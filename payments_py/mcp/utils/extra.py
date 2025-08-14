"""
Helpers to build MCP-compatible `extra` objects from HTTP requests/headers.
"""

from typing import Any, Dict


def build_extra_from_http_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    """Build an MCP ``extra`` object from raw HTTP headers mapping.

    Args:
        headers: Dictionary of HTTP headers.

    Returns:
        Extra object compatible with MCP libraries.
    """
    return {"requestInfo": {"headers": headers or {}}}


def build_extra_from_http_request(req: Any) -> Dict[str, Any]:
    """Build an MCP ``extra`` object from a request-like object.

    Args:
        req: Object or dict that may carry a ``headers`` attribute or key.

    Returns:
        Extra object compatible with MCP libraries.
    """
    headers = getattr(req, "headers", None)
    if headers is None and isinstance(req, dict):
        headers = req.get("headers")
    return build_extra_from_http_headers(headers or {})


def build_extra_from_fastmcp_context(ctx: Any) -> Dict[str, Any]:
    """
    Create an MCP ``extra`` object from a FastMCP ``Context``.

    Parameters
    ----------
    ctx : Any
        FastMCP context instance passed to tool/resource/prompt functions.

    Returns
    -------
    dict
        Extra object including request headers if present.
    """
    try:
        if ctx and getattr(ctx, "request_context", None):
            # Prefer direct request attr; fallback to meta.request_context
            req = getattr(ctx.request_context, "request", None)
            if req is None and getattr(ctx.request_context, "meta", None) is not None:
                req = getattr(ctx.request_context.meta, "request_context", None)
            if req is None:
                req = getattr(ctx.request_context, "meta", None)
                req = getattr(req, "request", None) if req is not None else None
            if req is None:
                return build_extra_from_http_headers({})
            req_headers = getattr(req, "headers", {}) or {}
            # Starlette's Headers object is a Mapping; convert safely
            if hasattr(req_headers, "items"):
                headers = {str(k): str(v) for k, v in req_headers.items()}
            elif hasattr(req_headers, "raw"):
                headers = {k.decode(): v.decode() for k, v in (req_headers.raw or [])}
            elif isinstance(req_headers, dict):
                headers = {str(k): str(v) for k, v in req_headers.items()}
            else:
                headers = {}
            return build_extra_from_http_headers(headers)
    except Exception:
        pass
    return build_extra_from_http_headers({})
