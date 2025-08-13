"""
Helpers to build logical URLs for MCP tools, resources and prompts.
"""

from typing import Any, Dict
from urllib.parse import urlencode


def build_logical_tool_url(server_name: str, tool_name: str, args: Any) -> str:
    """Build a logical MCP URL for a tool call.

    Args:
        server_name: Logical MCP server name.
        tool_name: Tool identifier.
        args: Arguments dictionary to be encoded in the query string.

    Returns:
        Logical URL string.
    """
    query = ""
    try:
        obj = args if isinstance(args, dict) else {}
        params = {}
        for k, v in obj.items():
            params[str(k)] = v if isinstance(v, str) else json_dumps_safe(v)
        s = urlencode(params)
        query = f"?{s}" if s else ""
    except Exception:
        pass
    return f"mcp://{server_name}/tools/{tool_name}{query}"


def build_logical_resource_url(
    server_name: str, resource_name: str, variables: Dict[str, Any]
) -> str:
    """Build a logical MCP URL for a resource retrieval.

    Args:
        server_name: Logical MCP server name.
        resource_name: Resource identifier.
        variables: Variables dictionary to be encoded in the query string.

    Returns:
        Logical URL string.
    """
    query = ""
    try:
        params = {}
        for k, v in (variables or {}).items():
            params[str(k)] = v[0] if isinstance(v, list) and v else str(v)
        s = urlencode(params)
        query = f"?{s}" if s else ""
    except Exception:
        pass
    return f"mcp://{server_name}/resources/{resource_name}{query}"


def build_logical_meta_url(server_name: str, method: str) -> str:
    """Build a logical MCP URL for a meta endpoint.

    Args:
        server_name: Logical MCP server name.
        method: Meta operation name.

    Returns:
        Logical URL string.
    """
    safe = method if isinstance(method, str) else "unknown"
    return f"mcp://{server_name}/meta/{safe}"


def build_logical_url(options: Dict[str, Any]) -> str:
    """Build a logical MCP URL from generic options.

    Args:
        options: Dictionary with keys kind, serverName, name and argsOrVars.

    Returns:
        Logical URL string.
    """
    kind = options.get("kind")
    server_name = options.get("serverName")
    name = options.get("name")
    args_or_vars = options.get("argsOrVars")
    if kind == "resource":
        return build_logical_resource_url(server_name, name, args_or_vars or {})
    return build_logical_tool_url(server_name, name, args_or_vars)


def json_dumps_safe(value: Any) -> str:
    """Serialize a Python value to JSON without raising exceptions.

    Falls back to ``str(value)`` when standard JSON serialization fails.

    Args:
        value: Any Python value.

    Returns:
        JSON string or stringified value.
    """
    try:
        import json

        return json.dumps(value, separators=(",", ":"))
    except Exception:
        return str(value)
