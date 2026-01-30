"""
MCP integration entry-point for the Nevermined Payments Python SDK.

This module exposes a class-based API with two distinct APIs:

1. **Advanced API** (low-level control):
   - ``configure(options)``: Set shared configuration
   - ``with_paywall(handler, options)``: Decorate individual handlers
   - ``attach(server)``: Integrate with existing MCP servers
   - ``authenticate_meta(extra, method)``: Authenticate meta operations

2. **Simplified API** (high-level server management):
   - ``register_tool(name, config, handler, options)``: Register tools
   - ``register_resource(uri, config, handler, options)``: Register resources
   - ``register_prompt(name, config, handler, options)``: Register prompts
   - ``start(config)``: Start complete MCP server with OAuth
   - ``stop()``: Stop server gracefully

Examples:
    Advanced API:
        >>> payments.mcp.configure({"agentId": "...", "serverName": "..."})
        >>> protected = payments.mcp.with_paywall(handler, {"kind": "tool", "name": "hello"})

    Simplified API:
        >>> payments.mcp.register_tool("hello", {"description": "..."}, handler, {"credits": 1})
        >>> result = await payments.mcp.start({"port": 5001, "agentId": "...", "serverName": "..."})
        >>> await result["stop"]()
"""

from typing import Any, Awaitable, Callable, Dict, Optional, Protocol, Union

from .core.auth import PaywallAuthenticator
from .core.credits_context import CreditsContextProvider
from .core.paywall import PaywallDecorator
from .types import (
    McpPromptConfig,
    McpRegistrationOptions,
    McpResourceConfig,
    McpServerConfig,
    McpServerResult,
    McpToolConfig,
    PaywallOptions,
    PromptHandler,
    PromptOptions,
    ResourceHandler,
    ResourceOptions,
    ToolHandler,
    ToolOptions,
)


class _AttachableServer(Protocol):
    def register_tool(
        self, name: str, config: Any, handler: Callable[..., Awaitable[Any]]
    ) -> None:
        """Register a tool handler on the server."""
        pass

    def register_resource(
        self,
        name: str,
        template: Any,
        config: Any,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a resource handler on the server."""
        pass

    def register_prompt(
        self, name: str, config: Any, handler: Callable[..., Awaitable[Any]]
    ) -> None:
        """Register a prompt handler on the server."""
        pass


class MCPIntegration:
    """Class-based MCP integration for Payments.

    Provides two APIs:

    1. **Advanced API** - Low-level control for custom server implementations:
       - configure(), with_paywall(), attach(), authenticate_meta()

    2. **Simplified API** - High-level server management (recommended):
       - register_tool(), register_resource(), register_prompt()
       - start(), stop()

    The Simplified API handles all server setup automatically including:
    - MCP Server creation from SDK
    - FastAPI app setup
    - OAuth 2.1 discovery endpoints
    - Session management
    - HTTP server lifecycle

    Examples:
        Advanced API:
            >>> payments.mcp.configure({"agentId": "...", "serverName": "..."})
            >>> protected = payments.mcp.with_paywall(handler, {"kind": "tool", "name": "hello"})

        Simplified API:
            >>> payments.mcp.register_tool("hello", {"description": "..."}, handler)
            >>> result = await payments.mcp.start({"port": 5001, ...})
    """

    def __init__(self, payments_service: Any) -> None:
        """Initialize the integration with a Payments service instance.

        Args:
            payments_service: The initialized Payments client.
        """
        self._payments = payments_service
        self._authenticator = PaywallAuthenticator(self._payments)
        self._credits_context = CreditsContextProvider()
        self._decorator = PaywallDecorator(
            self._payments, self._authenticator, self._credits_context
        )
        # Server manager for simplified API (lazy initialized)
        self._server_manager: Optional[Any] = None

    def configure(self, options: Dict[str, Any]) -> None:
        """Configure shared options such as ``agentId`` and ``serverName``.

        Args:
            options: Configuration dictionary with keys like ``agentId`` and ``serverName``
        """
        self._decorator.configure(options)

    def with_paywall(
        self,
        handler: Callable[..., Awaitable[Any]] | Callable[..., Any],
        options: Union[ToolOptions, PromptOptions, ResourceOptions, None] = None,
    ) -> Callable[..., Awaitable[Any]]:
        """Wrap a handler with the paywall protection.

        The handler can optionally receive a PaywallContext parameter containing
        authentication and credit information. Handlers without this parameter
        will continue to work for backward compatibility.

        Args:
            handler: The tool/resource/prompt handler to protect. Can optionally
                    accept a PaywallContext parameter as the last argument.
            options: The paywall options including kind, name and credits

        Returns:
            An awaitable handler with paywall applied
        """
        opts: PaywallOptions = options or {"kind": "tool", "name": "unnamed"}  # type: ignore[assignment]
        return self._decorator.protect(handler, opts)

    async def authenticate_meta(self, extra: Any, method: str) -> Dict[str, Any]:
        """Authenticate meta endpoints such as initialize/list.

        Args:
            extra: Extra request metadata containing headers
            method: The meta method name

        Returns:
            Authentication result dict
        """
        cfg: Dict[str, Any] = getattr(self._decorator, "config", {})  # type: ignore[assignment]
        agent_id = cfg.get("agentId", "")
        server_name = cfg.get("serverName", "mcp-server")
        return await self._authenticator.authenticate_meta(
            extra, {}, agent_id, server_name, method
        )

    def attach(self, server: _AttachableServer):
        """Attach helpers to a server and return registration methods.

        Args:
            server: An object exposing register_tool/register_resource/register_prompt

        Returns:
            An object with methods to register protected handlers on the server
        """

        integration = self

        class _Registrar:
            """Helper that registers protected handlers into the provided server."""

            def register_tool(
                self,
                name: str,
                config: Any,
                handler: Callable[..., Awaitable[Any]] | Callable[..., Any],
                options: Dict[str, Any] | None = None,
            ) -> None:
                """Register a tool handler protected by the paywall.

                The handler can optionally receive a PaywallContext parameter
                containing authentication and credit information.
                """
                protected = integration.with_paywall(
                    handler, {"kind": "tool", "name": name, **(options or {})}
                )
                server.register_tool(name, config, protected)

            def register_resource(
                self,
                name: str,
                template: Any,
                config: Any,
                handler: Callable[..., Awaitable[Any]] | Callable[..., Any],
                options: Dict[str, Any] | None = None,
            ) -> None:
                """Register a resource handler protected by the paywall.

                The handler can optionally receive a PaywallContext parameter
                containing authentication and credit information.
                """
                protected = integration.with_paywall(
                    handler, {"kind": "resource", "name": name, **(options or {})}
                )
                server.register_resource(name, template, config, protected)

            def register_prompt(
                self,
                name: str,
                config: Any,
                handler: Callable[..., Awaitable[Any]] | Callable[..., Any],
                options: Dict[str, Any] | None = None,
            ) -> None:
                """Register a prompt handler protected by the paywall.

                The handler can optionally receive a PaywallContext parameter
                containing authentication and credit information.
                """
                protected = integration.with_paywall(
                    handler, {"kind": "prompt", "name": name, **(options or {})}
                )
                server.register_prompt(name, config, protected)

        return _Registrar()

    # =========================================================================
    # SIMPLIFIED API - High-level server management
    # =========================================================================

    def _get_server_manager(self) -> Any:
        """Get or create the server manager for simplified API.

        Returns:
            McpServerManager instance.
        """
        if self._server_manager is None:
            from .core.server_manager import create_server_manager

            self._server_manager = create_server_manager(self._payments)
        return self._server_manager

    def register_tool(
        self,
        name: str,
        config: McpToolConfig,
        handler: ToolHandler,
        options: Optional[McpRegistrationOptions] = None,
    ) -> None:
        """Register a tool with the simplified API.

        Must be called before start(). The tool will be automatically
        protected with paywall when the server starts.

        Args:
            name: Tool name identifier.
            config: Tool configuration dict with description, inputSchema, etc.
            handler: Tool handler function (args, context?) -> result.
            options: Optional registration options (credits, onRedeemError).

        Raises:
            RuntimeError: If called after server has started.

        Examples:
            >>> payments.mcp.register_tool(
            ...     "hello_world",
            ...     {"description": "Says hello", "inputSchema": {...}},
            ...     async def handler(args, context=None):
            ...         return {"content": [{"type": "text", "text": f"Hello {args['name']}!"}]}
            ...     ,
            ...     {"credits": 1}
            ... )
        """
        self._get_server_manager().register_tool(name, config, handler, options)

    def register_resource(
        self,
        uri: str,
        config: McpResourceConfig,
        handler: ResourceHandler,
        options: Optional[McpRegistrationOptions] = None,
    ) -> None:
        """Register a resource with the simplified API.

        Must be called before start(). The resource will be automatically
        protected with paywall when the server starts.

        Args:
            uri: Resource URI pattern (e.g., "data://config").
            config: Resource configuration dict with name, mimeType, etc.
            handler: Resource handler function (uri, variables, context?) -> result.
            options: Optional registration options (credits, onRedeemError).

        Raises:
            RuntimeError: If called after server has started.

        Examples:
            >>> payments.mcp.register_resource(
            ...     "data://config",
            ...     {"name": "Configuration", "mimeType": "application/json"},
            ...     async def handler(uri, variables, context=None):
            ...         return {"contents": [{"uri": str(uri), "text": "..."}]}
            ...     ,
            ...     {"credits": 2}
            ... )
        """
        self._get_server_manager().register_resource(uri, config, handler, options)

    def register_prompt(
        self,
        name: str,
        config: McpPromptConfig,
        handler: PromptHandler,
        options: Optional[McpRegistrationOptions] = None,
    ) -> None:
        """Register a prompt with the simplified API.

        Must be called before start(). The prompt will be automatically
        protected with paywall when the server starts.

        Args:
            name: Prompt name identifier.
            config: Prompt configuration dict with name, description, etc.
            handler: Prompt handler function (args, context?) -> result.
            options: Optional registration options (credits, onRedeemError).

        Raises:
            RuntimeError: If called after server has started.

        Examples:
            >>> payments.mcp.register_prompt(
            ...     "greeting",
            ...     {"name": "Greeting", "description": "Greets user"},
            ...     async def handler(args, context=None):
            ...         return {"messages": [...]}
            ...     ,
            ...     {"credits": 1}
            ... )
        """
        self._get_server_manager().register_prompt(name, config, handler, options)

    async def start(self, config: McpServerConfig) -> McpServerResult:
        """Start the MCP server with the simplified API.

        This creates and starts everything needed for a complete MCP server:
        - MCP Server instance from the SDK
        - FastAPI application with all endpoints
        - OAuth 2.1 discovery endpoints (/.well-known/*)
        - Client registration endpoint (/register)
        - Health check and server info endpoints
        - MCP handlers (POST/GET/DELETE /mcp)
        - HTTP server (uvicorn)

        All previously registered tools, resources, and prompts will be
        automatically protected with paywall and mounted on the server.

        Args:
            config: Server configuration dict (McpServerConfig) with:
                - port: Port number (required)
                - agentId: Nevermined agent DID (required)
                - serverName: Human-readable server name (required)
                - baseUrl: Base URL (optional, defaults to http://localhost:{port})
                - version: Server version (optional, defaults to '1.0.0')
                - description: Server description (optional)
                - ... and other optional configuration

        Returns:
            McpServerResult dict with:
                - info: ServerInfo dict (baseUrl, port, tools, resources, prompts)
                - stop: Async function to stop the server gracefully

        Raises:
            RuntimeError: If server is not in IDLE state.
            ValueError: If required configuration is missing.

        Examples:
            >>> # Register handlers first
            >>> payments.mcp.register_tool("hello", {...}, handler)
            >>> payments.mcp.register_resource("data://config", {...}, handler)
            >>>
            >>> # Then start the server
            >>> result = await payments.mcp.start({
            ...     "port": 5001,
            ...     "agentId": "abc123",
            ...     "serverName": "my-mcp-server",
            ...     "version": "0.1.0",
            ...     "description": "My MCP server with Nevermined"
            ... })
            >>>
            >>> print(f"Server running at {result['info']['baseUrl']}")
            >>> print(f"Tools: {result['info']['tools']}")
            >>>
            >>> # Later: stop gracefully
            >>> await result["stop"]()
            >>> # or
            >>> await payments.mcp.stop()
        """
        return await self._get_server_manager().start(config)

    async def stop(self) -> None:
        """Stop the MCP server gracefully.

        This is a convenience method - you can also use the stop() function
        returned by start().

        Examples:
            >>> await payments.mcp.stop()
        """
        if self._server_manager:
            await self._server_manager.stop()


def build_mcp_integration(payments_service: Any) -> MCPIntegration:
    """Factory that builds the class-based MCP integration.

    Args:
        payments_service: The initialized Payments client

    Returns:
        MCPIntegration instance
    """
    return MCPIntegration(payments_service)
