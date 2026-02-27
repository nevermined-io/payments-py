"""
PaymentsMCP - Decorator-based MCP server with Nevermined payments and OAuth.

This module provides a decorator-based API similar to FastMCP but with integrated:
- OAuth 2.1 authentication
- Credit redemption for monetizing tools, resources, and prompts
- Full Nevermined payments integration

Example:
    >>> from payments_py import Payments
    >>> from payments_py.mcp import PaymentsMCP
    >>>
    >>> payments = Payments(nvm_api_key="...", environment="staging_sandbox")
    >>> mcp = PaymentsMCP(payments, name="my-server", agent_id="did:nv:...")
    >>>
    >>> @mcp.tool(credits=5)
    >>> def weather(city: str) -> str:
    ...     return f"Weather in {city}: 22°C"
    >>>
    >>> @mcp.resource("data://config", credits=2)
    >>> def get_config() -> str:
    ...     return '{"version": "1.0.0"}'
    >>>
    >>> @mcp.prompt(credits=1)
    >>> def greeting(name: str) -> list:
    ...     return [{"role": "user", "content": f"Hello {name}!"}]
    >>>
    >>> # Run the server with OAuth
    >>> await mcp.start(port=3002)
"""

import asyncio
import functools
import inspect
import json
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union, get_type_hints

from .core.server_manager import McpServerManager, create_server_manager
from .types import CreditsOption

# Type for any function
F = TypeVar("F", bound=Callable[..., Any])


def _extract_input_schema(fn: Callable) -> Dict[str, Any]:
    """Extract JSON Schema from function type hints.

    Args:
        fn: Function to extract schema from.

    Returns:
        JSON Schema dict for the function parameters.
    """
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    sig = inspect.signature(fn)

    for param_name, param in sig.parameters.items():
        # Skip self, cls, and special parameters
        if param_name in ("self", "cls", "context", "ctx", "extra", "paywall_context"):
            continue

        # Determine type
        param_type = hints.get(param_name, param.annotation)
        json_type = "string"  # default

        if param_type != inspect.Parameter.empty:
            if param_type == int:
                json_type = "integer"
            elif param_type == float:
                json_type = "number"
            elif param_type == bool:
                json_type = "boolean"
            elif param_type == list or (
                hasattr(param_type, "__origin__") and param_type.__origin__ == list
            ):
                json_type = "array"
            elif param_type == dict or (
                hasattr(param_type, "__origin__") and param_type.__origin__ == dict
            ):
                json_type = "object"

        prop: Dict[str, Any] = {"type": json_type}

        # Add description from docstring if available
        if fn.__doc__:
            # Simple extraction - look for ":param name:" pattern
            import re

            match = re.search(
                rf":param\s+{param_name}:\s*(.+?)(?=:param|:return|$)",
                fn.__doc__,
                re.DOTALL,
            )
            if match:
                prop["description"] = match.group(1).strip()

        schema["properties"][param_name] = prop

        # Add to required if no default
        if param.default == inspect.Parameter.empty:
            schema["required"].append(param_name)

    return schema


class PaymentsMCP:
    """MCP server with integrated Nevermined payments and OAuth.

    This class provides a decorator-based API similar to FastMCP but uses
    McpServerManager internally, which includes:
    - OAuth 2.1 authentication endpoints
    - Client registration
    - Credit redemption (paywall)
    - Session management
    - Full MCP protocol support

    Attributes:
        payments: The Payments instance for authentication and credit redemption.
        name: Server name.
        agent_id: Nevermined agent DID.

    Example:
        >>> payments = Payments(nvm_api_key="...", environment="staging_sandbox")
        >>> mcp = PaymentsMCP(payments, name="calculator", agent_id="did:nv:...")
        >>>
        >>> @mcp.tool(credits=1)
        >>> def add(a: int, b: int) -> int:
        ...     return a + b
        >>>
        >>> # Dynamic credits based on result
        >>> @mcp.tool(credits=lambda args, result: len(result) // 100)
        >>> def generate_text(prompt: str) -> str:
        ...     return "Generated text..."
        >>>
        >>> await mcp.start(port=3002)
    """

    def __init__(
        self,
        payments: Any,
        name: str = "payments-mcp-server",
        agent_id: Optional[str] = None,
        version: str = "1.0.0",
        description: Optional[str] = None,
    ) -> None:
        """Initialize PaymentsMCP.

        Args:
            payments: Initialized Payments instance.
            name: Server name (default: "payments-mcp-server").
            agent_id: Nevermined agent DID for authentication.
            version: Server version (default: "1.0.0").
            description: Server description.
        """
        self.payments = payments
        self.name = name
        self.agent_id = agent_id
        self.version = version
        self.description = description

        # Use McpServerManager for OAuth and paywall support
        self._manager: McpServerManager = create_server_manager(payments)

        # Track registered handlers for introspection
        self._registered_tools: Dict[str, Dict[str, Any]] = {}
        self._registered_resources: Dict[str, Dict[str, Any]] = {}
        self._registered_prompts: Dict[str, Dict[str, Any]] = {}

    def tool(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        credits: Optional[CreditsOption] = None,
        on_redeem_error: str = "ignore",
    ) -> Callable[[F], F]:
        """Decorator to register a tool with optional credit redemption.

        The decorated function's type hints are used to generate the input schema.
        OAuth authentication and credit redemption are handled automatically.

        Args:
            name: Optional name for the tool (defaults to function name).
            description: Optional description of what the tool does.
            credits: Credits to redeem per call. Can be:
                - None: No credits charged (free tool)
                - int: Fixed number of credits
                - Callable[[args, result], int]: Dynamic credits based on args/result
            on_redeem_error: What to do if credit redemption fails.
                - "ignore": Silently ignore (default)
                - "propagate": Raise an error

        Returns:
            Decorator function.

        Example:
            >>> @mcp.tool(credits=5)
            >>> def weather(city: str) -> str:
            ...     '''Get weather for a city.
            ...
            ...     :param city: City name
            ...     '''
            ...     return f"Weather in {city}: 22°C"
        """
        if callable(name):
            raise TypeError(
                "The @tool decorator was used incorrectly. "
                "Did you forget to call it? Use @tool() instead of @tool"
            )

        def decorator(fn: F) -> F:
            tool_name = name or fn.__name__
            tool_description = description or fn.__doc__ or ""

            # Extract input schema from type hints
            input_schema = _extract_input_schema(fn)

            # Check if the user function accepts a paywall_context parameter
            _fn_params = inspect.signature(fn).parameters
            _accepts_paywall_ctx = "paywall_context" in _fn_params

            # Create handler that adapts function signature to MCP format
            @functools.wraps(fn)
            async def handler(
                args: Dict[str, Any], context: Any = None, paywall_context: Any = None
            ) -> Any:
                # Call the original function with unpacked args,
                # forwarding paywall_context if the function accepts it
                call_args = dict(args)
                if _accepts_paywall_ctx and paywall_context is not None:
                    call_args["paywall_context"] = paywall_context
                if asyncio.iscoroutinefunction(fn):
                    result = await fn(**call_args)
                else:
                    result = fn(**call_args)

                # Convert result to MCP format
                if isinstance(result, dict) and "content" in result:
                    return result
                elif isinstance(result, str):
                    return {"content": [{"type": "text", "text": result}]}
                else:
                    return {"content": [{"type": "text", "text": json.dumps(result)}]}

            # Build tool config
            tool_config = {
                "description": (
                    tool_description.split("\n")[0].strip() if tool_description else ""
                ),
                "inputSchema": input_schema,
            }

            # Build options
            options = {}
            if credits is not None:
                options["credits"] = credits
            if on_redeem_error != "ignore":
                options["onRedeemError"] = on_redeem_error

            # Register with server manager
            self._manager.register_tool(
                tool_name,
                tool_config,
                handler,
                options if options else None,
            )

            # Track for introspection
            self._registered_tools[tool_name] = {
                "name": tool_name,
                "description": tool_description,
                "credits": credits,
                "fn": fn,
            }

            return fn

        return decorator

    def resource(
        self,
        uri: str,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None,
        mime_type: Optional[str] = None,
        credits: Optional[CreditsOption] = None,
        on_redeem_error: str = "ignore",
    ) -> Callable[[F], F]:
        """Decorator to register a resource with optional credit redemption.

        Args:
            uri: URI for the resource (e.g., "data://config" or "data://{id}").
            name: Optional name for the resource.
            description: Optional description of the resource.
            mime_type: Optional MIME type for the resource.
            credits: Credits to redeem per read.
            on_redeem_error: What to do if credit redemption fails.

        Returns:
            Decorator function.

        Example:
            >>> @mcp.resource("data://config", credits=2)
            >>> def get_config() -> str:
            ...     return '{"version": "1.0.0"}'
        """
        if callable(uri):
            raise TypeError(
                "The @resource decorator was used incorrectly. "
                "Did you forget to call it? Use @resource('uri') instead of @resource"
            )

        def decorator(fn: F) -> F:
            resource_name = name or fn.__name__
            resource_description = description or fn.__doc__ or ""

            # Create handler that adapts function signature to MCP format
            @functools.wraps(fn)
            async def handler(
                uri_obj: Any, variables: Dict[str, str], context: Any = None
            ) -> Any:
                # Get function parameters
                sig = inspect.signature(fn)
                params = list(sig.parameters.keys())

                # Call the original function
                if asyncio.iscoroutinefunction(fn):
                    if params and params[0] not in ("self", "cls"):
                        # Function expects parameters (template resource)
                        result = await fn(**variables)
                    else:
                        result = await fn()
                else:
                    if params and params[0] not in ("self", "cls"):
                        result = fn(**variables)
                    else:
                        result = fn()

                # Convert result to MCP format
                if isinstance(result, dict) and "contents" in result:
                    return result
                elif isinstance(result, str):
                    return {
                        "contents": [
                            {
                                "uri": str(uri_obj) if uri_obj else uri,
                                "mimeType": mime_type or "text/plain",
                                "text": result,
                            }
                        ]
                    }
                else:
                    return {
                        "contents": [
                            {
                                "uri": str(uri_obj) if uri_obj else uri,
                                "mimeType": mime_type or "application/json",
                                "text": json.dumps(result),
                            }
                        ]
                    }

            # Build resource config
            resource_config = {
                "name": resource_name,
                "description": (
                    resource_description.split("\n")[0].strip()
                    if resource_description
                    else ""
                ),
                "mimeType": mime_type or "text/plain",
            }

            # Build options
            options = {}
            if credits is not None:
                options["credits"] = credits
            if on_redeem_error != "ignore":
                options["onRedeemError"] = on_redeem_error

            # Register with server manager
            self._manager.register_resource(
                uri,
                resource_config,
                handler,
                options if options else None,
            )

            # Track for introspection
            self._registered_resources[uri] = {
                "uri": uri,
                "name": resource_name,
                "description": resource_description,
                "credits": credits,
                "fn": fn,
            }

            return fn

        return decorator

    def prompt(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        credits: Optional[CreditsOption] = None,
        on_redeem_error: str = "ignore",
    ) -> Callable[[F], F]:
        """Decorator to register a prompt with optional credit redemption.

        Args:
            name: Optional name for the prompt (defaults to function name).
            description: Optional description of what the prompt does.
            credits: Credits to redeem per use.
            on_redeem_error: What to do if credit redemption fails.

        Returns:
            Decorator function.

        Example:
            >>> @mcp.prompt(credits=1)
            >>> def greeting(name: str) -> list:
            ...     return [{"role": "user", "content": f"Hello {name}!"}]
        """
        if callable(name):
            raise TypeError(
                "The @prompt decorator was used incorrectly. "
                "Did you forget to call it? Use @prompt() instead of @prompt"
            )

        def decorator(fn: F) -> F:
            prompt_name = name or fn.__name__
            prompt_description = description or fn.__doc__ or ""

            # Extract arguments from function signature
            sig = inspect.signature(fn)
            arguments = []
            for param_name, param in sig.parameters.items():
                if param_name in ("self", "cls", "context", "ctx"):
                    continue
                arg_info: Dict[str, Any] = {"name": param_name}
                if param.default != inspect.Parameter.empty:
                    arg_info["required"] = False
                else:
                    arg_info["required"] = True
                arguments.append(arg_info)

            # Create handler that adapts function signature to MCP format
            @functools.wraps(fn)
            async def handler(args: Dict[str, Any], context: Any = None) -> Any:
                # Call the original function with unpacked args
                if asyncio.iscoroutinefunction(fn):
                    result = await fn(**args)
                else:
                    result = fn(**args)

                # Convert result to MCP format
                if isinstance(result, dict) and "messages" in result:
                    return result
                elif isinstance(result, list):
                    return {"messages": result}
                else:
                    return {
                        "messages": [
                            {
                                "role": "user",
                                "content": {"type": "text", "text": str(result)},
                            }
                        ]
                    }

            # Build prompt config
            prompt_config = {
                "name": prompt_name,
                "description": (
                    prompt_description.split("\n")[0].strip()
                    if prompt_description
                    else ""
                ),
                "arguments": arguments,
            }

            # Build options
            options = {}
            if credits is not None:
                options["credits"] = credits
            if on_redeem_error != "ignore":
                options["onRedeemError"] = on_redeem_error

            # Register with server manager
            self._manager.register_prompt(
                prompt_name,
                prompt_config,
                handler,
                options if options else None,
            )

            # Track for introspection
            self._registered_prompts[prompt_name] = {
                "name": prompt_name,
                "description": prompt_description,
                "credits": credits,
                "fn": fn,
            }

            return fn

        return decorator

    async def start(
        self,
        port: int,
        host: str = "0.0.0.0",
        base_url: Optional[str] = None,
        on_log: Optional[Callable[[str], None]] = None,
    ) -> Dict[str, Any]:
        """Start the MCP server with OAuth and paywall.

        This starts a complete MCP server with:
        - OAuth 2.1 discovery endpoints (/.well-known/*)
        - Client registration (/register)
        - Health check (/health)
        - Server info (/)
        - MCP handlers (POST/GET/DELETE /mcp)
        - Credit redemption for protected handlers

        Args:
            port: Port to listen on.
            host: Host to bind to (default: "0.0.0.0").
            base_url: Base URL for the server (default: http://localhost:{port}).
            on_log: Optional callback for logging.

        Returns:
            Dict with:
                - info: Server info (baseUrl, port, tools, resources, prompts)
                - stop: Async function to stop the server

        Example:
            >>> result = await mcp.start(port=3002)
            >>> print(f"Server running at {result['info']['baseUrl']}")
            >>> # Later...
            >>> await result["stop"]()
        """
        if not self.agent_id:
            raise ValueError("agent_id is required. Set it in the constructor.")

        config = {
            "port": port,
            "host": host,
            "agentId": self.agent_id,
            "serverName": self.name,
            "version": self.version,
            "description": self.description,
            "baseUrl": base_url,
            "onLog": on_log or (lambda msg: print(f"[MCP] {msg}")),
        }

        return await self._manager.start(config)

    async def stop(self) -> None:
        """Stop the MCP server gracefully.

        Example:
            >>> await mcp.stop()
        """
        await self._manager.stop()

    # =========================================================================
    # Introspection methods
    # =========================================================================

    def list_tools(self) -> List[str]:
        """List all registered tool names.

        Returns:
            List of tool names.
        """
        return list(self._registered_tools.keys())

    def list_resources(self) -> List[str]:
        """List all registered resource URIs.

        Returns:
            List of resource URIs.
        """
        return list(self._registered_resources.keys())

    def list_prompts(self) -> List[str]:
        """List all registered prompt names.

        Returns:
            List of prompt names.
        """
        return list(self._registered_prompts.keys())

    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered tool.

        Args:
            name: Tool name.

        Returns:
            Tool info dict or None if not found.
        """
        return self._registered_tools.get(name)

    def get_resource_info(self, uri: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered resource.

        Args:
            uri: Resource URI.

        Returns:
            Resource info dict or None if not found.
        """
        return self._registered_resources.get(uri)

    def get_prompt_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get information about a registered prompt.

        Args:
            name: Prompt name.

        Returns:
            Prompt info dict or None if not found.
        """
        return self._registered_prompts.get(name)
