"""
Server manager for simplified MCP API.

This module orchestrates the complete MCP server lifecycle, including:
- McpServer creation from the MCP SDK
- FastAPI app setup and configuration
- OAuth router mounting
- Session management
- MCP handler mounting
- HTTP server start/stop

Examples:
    >>> from payments_py import Payments
    >>> from payments_py.mcp.core import create_server_manager
    >>>
    >>> payments = Payments(nvm_api_key="...", environment="staging_sandbox")
    >>> manager = create_server_manager(payments)
    >>>
    >>> # Register handlers
    >>> manager.register_tool("hello", {...}, handler)
    >>>
    >>> # Start server
    >>> result = await manager.start({
    ...     "port": 5001,
    ...     "agentId": "abc123",
    ...     "serverName": "my-server"
    ... })
    >>>
    >>> # Stop server
    >>> await manager.stop()
"""

import asyncio
from enum import Enum
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ..http.mcp_handler import mount_mcp_handlers
from ..http.oauth_router import create_cors_middleware, create_oauth_router
from ..http.session_manager import SessionManager, create_session_manager
from ..types.server_types import (
    McpPromptConfig,
    McpRegistrationOptions,
    McpResourceConfig,
    McpServerConfig,
    McpServerResult,
    McpToolConfig,
    PromptHandler,
    PromptRegistration,
    ResourceHandler,
    ResourceRegistration,
    ServerInfo,
    ToolHandler,
    ToolRegistration,
)

# =============================================================================
# SERVER STATE
# =============================================================================


class ServerState(str, Enum):
    """Server state enumeration.

    Attributes:
        IDLE: Server is not running and can be started.
        STARTING: Server is in the process of starting.
        RUNNING: Server is running and handling requests.
        STOPPING: Server is in the process of stopping.
    """

    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


# =============================================================================
# SDK LAZY LOADING
# =============================================================================


_McpServerClass: Optional[Any] = None


async def _get_mcp_server_class() -> Any:
    """Lazily load McpServer (called Server in Python) from the MCP SDK.

    Returns:
        Server class from mcp.server module.

    Raises:
        ImportError: If mcp SDK is not installed.
    """
    global _McpServerClass

    if _McpServerClass is None:
        try:
            from mcp.server import Server

            _McpServerClass = Server
        except ImportError as error:
            raise ImportError(
                "Failed to load mcp SDK. Make sure it is installed: "
                "pip install mcp or pip install modelcontextprotocol"
            ) from error

    return _McpServerClass


# =============================================================================
# SERVER MANAGER
# =============================================================================


class McpServerManager:
    """Manages the complete MCP server lifecycle.

    This class orchestrates all components needed for a working MCP server:
    - MCP Server instance from the SDK
    - FastAPI application
    - OAuth router with discovery endpoints
    - Session manager for SSE transports
    - MCP handlers (POST/GET/DELETE /mcp)
    - HTTP server (uvicorn)

    The manager follows this lifecycle:
    1. IDLE: Handlers can be registered
    2. STARTING: Server is being created and started
    3. RUNNING: Server is active and handling requests
    4. STOPPING: Server is shutting down
    5. IDLE: Server has stopped and can be restarted

    Attributes:
        _state: Current server state.
        _payments: Payments service instance.
        _tools: Dict of registered tool handlers.
        _resources: Dict of registered resource handlers.
        _prompts: Dict of registered prompt handlers.
        _mcp_server: MCP Server instance from SDK.
        _fastapi_app: FastAPI application instance.
        _http_server: HTTP server instance (uvicorn).
        _session_manager: Session manager instance.
        _config: Server configuration.
        _log: Optional logging function.

    Examples:
        >>> manager = McpServerManager(payments)
        >>> manager.register_tool("hello", config, handler)
        >>> result = await manager.start({"port": 5001, ...})
        >>> await manager.stop()
    """

    def __init__(self, payments: Any) -> None:
        """Initialize the server manager.

        Args:
            payments: Payments service instance.
        """
        self._state = ServerState.IDLE
        self._payments = payments
        self._tools: Dict[str, ToolRegistration] = {}
        self._resources: Dict[str, ResourceRegistration] = {}
        self._prompts: Dict[str, PromptRegistration] = {}
        self._mcp_server: Optional[Any] = None
        self._fastapi_app: Optional[FastAPI] = None
        self._http_server: Optional[Any] = None
        self._session_manager: Optional[SessionManager] = None
        self._config: Optional[McpServerConfig] = None
        self._log: Optional[Callable[[str], None]] = None
        self._server_task: Optional[asyncio.Task] = None

    def get_state(self) -> ServerState:
        """Get current server state.

        Returns:
            Current ServerState value.

        Examples:
            >>> manager.get_state()
            <ServerState.IDLE: 'idle'>
        """
        return self._state

    def register_tool(
        self,
        name: str,
        config: McpToolConfig,
        handler: ToolHandler,
        options: Optional[McpRegistrationOptions] = None,
    ) -> None:
        """Register a tool.

        Must be called before start().

        Args:
            name: Tool name identifier.
            config: Tool configuration dict.
            handler: Tool handler function.
            options: Optional registration options (credits, onRedeemError).

        Raises:
            RuntimeError: If called after server has started.

        Examples:
            >>> manager.register_tool(
            ...     "hello_world",
            ...     {"description": "Says hello", "inputSchema": {...}},
            ...     async_handler_function,
            ...     {"credits": 1}
            ... )
        """
        if self._state != ServerState.IDLE:
            raise RuntimeError("Cannot register tools after server has started")

        opts: McpRegistrationOptions = options or {}
        self._tools[name] = {
            "name": name,
            "config": config,
            "handler": handler,
            "options": {
                "credits": opts.get("credits"),
                "onRedeemError": opts.get("onRedeemError", "ignore"),
            },
        }

        if self._log:
            self._log(f"Registered tool: {name}")

    def register_resource(
        self,
        uri: str,
        config: McpResourceConfig,
        handler: ResourceHandler,
        options: Optional[McpRegistrationOptions] = None,
    ) -> None:
        """Register a resource.

        Must be called before start().

        Args:
            uri: Resource URI pattern.
            config: Resource configuration dict.
            handler: Resource handler function.
            options: Optional registration options (credits, onRedeemError).

        Raises:
            RuntimeError: If called after server has started.

        Examples:
            >>> manager.register_resource(
            ...     "data://config",
            ...     {"name": "Config", "mimeType": "application/json"},
            ...     async_handler_function
            ... )
        """
        if self._state != ServerState.IDLE:
            raise RuntimeError("Cannot register resources after server has started")

        opts: McpRegistrationOptions = options or {}
        self._resources[uri] = {
            "uri": uri,
            "config": config,
            "handler": handler,
            "options": {
                "credits": opts.get("credits"),
                "onRedeemError": opts.get("onRedeemError", "ignore"),
            },
        }

        if self._log:
            self._log(f"Registered resource: {uri}")

    def register_prompt(
        self,
        name: str,
        config: McpPromptConfig,
        handler: PromptHandler,
        options: Optional[McpRegistrationOptions] = None,
    ) -> None:
        """Register a prompt.

        Must be called before start().

        Args:
            name: Prompt name identifier.
            config: Prompt configuration dict.
            handler: Prompt handler function.
            options: Optional registration options (credits, onRedeemError).

        Raises:
            RuntimeError: If called after server has started.

        Examples:
            >>> manager.register_prompt(
            ...     "greet",
            ...     {"name": "Greeting", "description": "Greets user"},
            ...     async_handler_function
            ... )
        """
        if self._state != ServerState.IDLE:
            raise RuntimeError("Cannot register prompts after server has started")

        opts: McpRegistrationOptions = options or {}
        self._prompts[name] = {
            "name": name,
            "config": config,
            "handler": handler,
            "options": {
                "credits": opts.get("credits"),
                "onRedeemError": opts.get("onRedeemError", "ignore"),
            },
        }

        if self._log:
            self._log(f"Registered prompt: {name}")

    async def start(self, config: McpServerConfig) -> McpServerResult:
        """Start the MCP server.

        This creates and starts everything needed for a complete MCP server:
        1. Validates configuration
        2. Creates MCP Server instance from SDK
        3. Registers handlers with paywall protection
        4. Creates FastAPI application
        5. Mounts OAuth router with discovery endpoints
        6. Creates session manager
        7. Mounts MCP handlers (POST/GET/DELETE /mcp)
        8. Starts HTTP server with uvicorn

        Args:
            config: Server configuration dict (McpServerConfig).

        Returns:
            McpServerResult dict with info and stop function.

        Raises:
            RuntimeError: If server is not in IDLE state.
            ValueError: If required configuration is missing.

        Examples:
            >>> result = await manager.start({
            ...     "port": 5001,
            ...     "agentId": "abc123",
            ...     "serverName": "my-server",
            ...     "version": "1.0.0"
            ... })
            >>> print(result["info"]["baseUrl"])
            'http://localhost:5001'
            >>> await result["stop"]()
        """
        if self._state != ServerState.IDLE:
            raise RuntimeError(f"Cannot start server in state: {self._state}")

        self._state = ServerState.STARTING
        self._config = config
        self._log = config.get("onLog")

        try:
            # Validate configuration
            if not config.get("agentId"):
                raise ValueError("agentId is required")
            if not config.get("port"):
                raise ValueError("port is required")

            base_url = config.get("baseUrl") or f"http://localhost:{config['port']}"

            # Get MCP Server class from SDK
            ServerClass = await _get_mcp_server_class()

            # Create MCP server instance
            self._mcp_server = ServerClass(
                name=config["serverName"], version=config.get("version", "1.0.0")
            )

            # Register all handlers with paywall protection
            await self._register_handlers_with_paywall()

            # Create FastAPI application
            self._fastapi_app = FastAPI(
                title=config["serverName"],
                version=config.get("version", "1.0.0"),
                description=config.get("description"),
            )

            # Apply CORS middleware
            cors_config = create_cors_middleware(config.get("corsOrigins", "*"))
            self._fastapi_app.add_middleware(CORSMiddleware, **cors_config)

            # Create OAuth router
            environment = config.get("environment") or getattr(
                self._payments, "_environment_name", "staging_sandbox"
            )

            oauth_router = create_oauth_router(
                {
                    "payments": self._payments,
                    "baseUrl": base_url,
                    "agentId": config["agentId"],
                    "environment": environment,
                    "serverName": config["serverName"],
                    "tools": list(self._tools.keys()),
                    "resources": list(self._resources.keys()),
                    "prompts": list(self._prompts.keys()),
                    "enableOAuthDiscovery": config.get("enableOAuthDiscovery", True),
                    "enableClientRegistration": config.get(
                        "enableClientRegistration", True
                    ),
                    "enableHealthCheck": config.get("enableHealthCheck", True),
                    "enableServerInfo": config.get("enableServerInfo", True),
                    "version": config.get("version", "1.0.0"),
                    "description": config.get("description"),
                    "onLog": self._log,
                }
            )

            # Mount OAuth router
            self._fastapi_app.include_router(oauth_router)

            # Create session manager
            self._session_manager = create_session_manager({"log": self._log})
            self._session_manager.set_mcp_server(self._mcp_server)

            # Mount MCP handlers
            mount_mcp_handlers(
                self._fastapi_app,
                self._session_manager,
                require_auth=True,
                log=self._log,
            )

            # Start HTTP server with uvicorn
            import uvicorn

            uvicorn_config = uvicorn.Config(
                app=self._fastapi_app,
                host=config.get("host", "0.0.0.0"),
                port=config["port"],
                log_level="info",  # Enable uvicorn logs for debugging
            )
            server = uvicorn.Server(uvicorn_config)

            # Start server in background task
            self._server_task = asyncio.create_task(server.serve())
            self._http_server = server

            # Wait for server to be ready
            while not server.started:
                await asyncio.sleep(0.01)

            self._state = ServerState.RUNNING

            # Build server info
            info: ServerInfo = {
                "baseUrl": base_url,
                "port": config["port"],
                "tools": list(self._tools.keys()),
                "resources": list(self._resources.keys()),
                "prompts": list(self._prompts.keys()),
            }

            # Log startup message
            self._log_startup_message(info, config)

            # Call onStart callback
            on_start = config.get("onStart")
            if on_start:
                on_start(info)

            # Return result
            return {"info": info, "stop": self.stop}

        except Exception as error:
            self._state = ServerState.IDLE
            raise error

    async def stop(self) -> None:
        """Stop the server gracefully.

        This method:
        1. Destroys all active sessions
        2. Closes the HTTP server
        3. Resets all internal state
        4. Returns server to IDLE state

        Examples:
            >>> await manager.stop()
        """
        if self._state != ServerState.RUNNING:
            return

        self._state = ServerState.STOPPING

        # Destroy all sessions
        if self._session_manager:
            self._session_manager.destroy_all_sessions()

        # Stop HTTP server
        if self._http_server:
            self._http_server.should_exit = True
            if self._server_task:
                try:
                    await asyncio.wait_for(self._server_task, timeout=5.0)
                except asyncio.TimeoutError:
                    if self._log:
                        self._log("Server stop timed out, forcing shutdown")
                    self._server_task.cancel()

        # Reset state
        self._mcp_server = None
        self._fastapi_app = None
        self._http_server = None
        self._session_manager = None
        self._server_task = None
        self._state = ServerState.IDLE

        if self._log:
            self._log("Server stopped")

    async def _register_handlers_with_paywall(self) -> None:
        """Register all tools, resources, and prompts with paywall protection.

        This method uses the Python MCP SDK's decorator-based API to register
        handlers. The SDK uses decorators like @server.call_tool(), @server.list_tools(),
        @server.read_resource(), etc.

        Raises:
            RuntimeError: If server config is not set.
        """
        if not self._config:
            raise RuntimeError("Server config not set")

        config = self._config

        # Configure MCP integration
        self._payments.mcp.configure(
            {"agentId": config["agentId"], "serverName": config["serverName"]}
        )

        # Get the with_paywall function
        with_paywall = self._payments.mcp.with_paywall

        # Store references to tools, resources, prompts for the handlers
        tools = self._tools
        resources = self._resources
        prompts = self._prompts

        # Import MCP types for type annotations
        from mcp.types import Tool, Resource, Prompt, TextContent, CallToolResult

        # Register list_tools handler
        @self._mcp_server.list_tools()
        async def list_tools_handler() -> list[Tool]:
            """List all registered tools."""
            result = []
            for name, registration in tools.items():
                tool_config = registration["config"]
                result.append(
                    Tool(
                        name=name,
                        description=tool_config.get("description", ""),
                        inputSchema=tool_config.get("inputSchema", {"type": "object"}),
                    )
                )
            return result

        # Register call_tool handler
        @self._mcp_server.call_tool()
        async def call_tool_handler(name: str, arguments: dict) -> CallToolResult:
            """Execute a tool with paywall protection."""
            if name not in tools:
                raise ValueError(f"Unknown tool: {name}")

            registration = tools[name]
            tool_handler = registration["handler"]
            options = registration["options"]
            credits_option = options.get("credits")

            # Create a wrapper that calls the tool handler with paywall
            async def execute_tool(
                args: Any, extra: Any = None, paywall_context: Any = None
            ) -> Any:
                result = tool_handler(args, extra, paywall_context)
                if hasattr(result, "__await__"):
                    result = await result
                return result

            # Wrap with paywall
            protected_handler = with_paywall(
                execute_tool,
                {
                    "name": name,
                    "kind": "tool",
                    "credits": credits_option,
                    "onRedeemError": options.get("onRedeemError"),
                    "planId": options.get("planId"),
                },
            )

            # Get request context for extra (headers, etc.)
            extra = self._get_request_extra()

            # Execute the protected handler
            result = await protected_handler(arguments, extra)

            # Convert result to MCP format with metadata
            # Extract metadata from paywall result (txHash, creditsRedeemed, etc.)
            metadata = None
            if isinstance(result, dict) and "_meta" in result:
                metadata = result.get("_meta")

            # Build content list
            if isinstance(result, dict) and "content" in result:
                content = result["content"]
            elif isinstance(result, list):
                content = result
            else:
                content = [TextContent(type="text", text=str(result))]

            # Return CallToolResult with metadata in _meta field
            return CallToolResult(
                content=content,
                _meta=metadata,
                isError=(
                    result.get("isError", False) if isinstance(result, dict) else False
                ),
            )

        # Register list_resources handler
        @self._mcp_server.list_resources()
        async def list_resources_handler() -> list[Resource]:
            """List all registered resources."""
            result = []
            for uri, registration in resources.items():
                resource_config = registration["config"]
                result.append(
                    Resource(
                        uri=uri,
                        name=resource_config.get("name", uri),
                        description=resource_config.get("description"),
                        mimeType=resource_config.get("mimeType"),
                    )
                )
            return result

        # Register read_resource handler
        @self._mcp_server.read_resource()
        async def read_resource_handler(uri: str) -> str:
            """Read a resource with paywall protection."""
            # Find matching resource (exact match or template match)
            matched_uri = None
            matched_registration = None
            for registered_uri, registration in resources.items():
                if registered_uri == uri:
                    matched_uri = registered_uri
                    matched_registration = registration
                    break

            if not matched_registration:
                raise ValueError(f"Unknown resource: {uri}")

            resource_handler = matched_registration["handler"]
            options = matched_registration["options"]
            credits_option = options.get("credits")

            # Create a wrapper that calls the resource handler with paywall
            async def execute_resource(
                uri_obj: Any, variables: dict, extra: Any = None
            ) -> Any:
                result = resource_handler(uri_obj, variables, extra)
                if hasattr(result, "__await__"):
                    result = await result
                return result

            # Wrap with paywall
            protected_handler = with_paywall(
                execute_resource,
                {
                    "name": matched_uri,
                    "kind": "resource",
                    "credits": credits_option,
                    "onRedeemError": options.get("onRedeemError"),
                    "planId": options.get("planId"),
                },
            )

            # Get request context for extra (headers, etc.)
            extra = self._get_request_extra()

            # Execute the protected handler
            result = await protected_handler(uri, {}, extra)

            # Convert result to string content
            if isinstance(result, dict) and "contents" in result:
                contents = result["contents"]
                if contents and len(contents) > 0:
                    return contents[0].get("text", str(result))
            return str(result)

        # Register list_prompts handler
        @self._mcp_server.list_prompts()
        async def list_prompts_handler() -> list[Prompt]:
            """List all registered prompts."""
            result = []
            for name, registration in prompts.items():
                prompt_config = registration["config"]
                result.append(
                    Prompt(
                        name=name,
                        description=prompt_config.get("description"),
                        arguments=prompt_config.get("arguments", []),
                    )
                )
            return result

        # Register get_prompt handler
        @self._mcp_server.get_prompt()
        async def get_prompt_handler(name: str, arguments: dict | None = None) -> Any:
            """Get a prompt with paywall protection."""
            if name not in prompts:
                raise ValueError(f"Unknown prompt: {name}")

            registration = prompts[name]
            prompt_handler = registration["handler"]
            options = registration["options"]
            credits_option = options.get("credits")

            # Create a wrapper that calls the prompt handler with paywall
            async def execute_prompt(args: Any, extra: Any = None) -> Any:
                result = prompt_handler(args, extra)
                if hasattr(result, "__await__"):
                    result = await result
                return result

            # Wrap with paywall
            protected_handler = with_paywall(
                execute_prompt,
                {
                    "name": name,
                    "kind": "prompt",
                    "credits": credits_option,
                    "onRedeemError": options.get("onRedeemError"),
                    "planId": options.get("planId"),
                },
            )

            # Get request context for extra (headers, etc.)
            extra = self._get_request_extra()

            # Execute the protected handler
            result = await protected_handler(arguments or {}, extra)

            # Return the result as-is (should be in MCP prompt format)
            return result

    def _get_request_extra(self) -> Dict[str, Any]:
        """Get request context/extra from the current request.

        This extracts headers and other context from the current HTTP request
        to pass to paywall handlers.

        Returns:
            Dict containing request info including headers.
        """
        # Try to get headers from session manager's current request context
        if self._session_manager:
            ctx = self._session_manager.get_current_request_context()
            if ctx:
                return {"requestInfo": {"headers": ctx.get("headers", {})}}

        return {}

    def _log_startup_message(self, info: ServerInfo, config: McpServerConfig) -> None:
        """Log startup message (only if onLog callback provided).

        Args:
            info: Server information.
            config: Server configuration.
        """
        if not self._log:
            return

        tools_list = ", ".join(info["tools"]) if info["tools"] else "none"
        resources_list = ", ".join(info["resources"]) if info["resources"] else "none"
        prompts_list = ", ".join(info["prompts"]) if info["prompts"] else "none"

        self._log(f"""MCP Server Started!
  MCP Endpoint: {info['baseUrl']}/mcp
  Health Check: {info['baseUrl']}/health
  Server Info:  {info['baseUrl']}/
  OAuth Discovery: {info['baseUrl']}/.well-known/oauth-authorization-server
  Tools: {tools_list}
  Resources: {resources_list}
  Prompts: {prompts_list}
  Agent ID: {config['agentId']}""")


# =============================================================================
# FACTORY FUNCTION
# =============================================================================


def create_server_manager(payments: Any) -> McpServerManager:
    """Create a new server manager.

    Args:
        payments: Payments service instance.

    Returns:
        New McpServerManager instance.

    Examples:
        >>> from payments_py import Payments
        >>> payments = Payments(nvm_api_key="...", environment="staging_sandbox")
        >>> manager = create_server_manager(payments)
    """
    return McpServerManager(payments)
