"""
MCP integration entry-point for the Nevermined Payments Python SDK.

This module exposes a class-based API (no dict-like compatibility):

- ``MCPIntegration``: Main integration surface with methods
  - ``configure(options)``: Set shared configuration such as agentId/serverName
  - ``with_paywall(handler, options)``: Decorate a handler with paywall
  - ``attach(server)``: Returns an object with ``registerTool``, ``registerResource``, ``registerPrompt``
  - ``authenticate_meta(extra, method)``: Authenticate meta operations like initialize/list

- ``build_mcp_integration(payments_service)``: Factory returning an ``MCPIntegration`` instance.
"""

from typing import Any, Awaitable, Callable, Dict, Protocol, Union

from .core.auth import PaywallAuthenticator
from .core.credits_context import CreditsContextProvider
from .core.paywall import PaywallDecorator
from .types import (
    PaywallOptions,
    ToolOptions,
    PromptOptions,
    ResourceOptions,
)


class _AttachableServer(Protocol):
    def registerTool(
        self, name: str, config: Any, handler: Callable[..., Awaitable[Any]]
    ) -> None:
        """Register a tool handler on the server."""
        pass

    def registerResource(
        self,
        name: str,
        template: Any,
        config: Any,
        handler: Callable[..., Awaitable[Any]],
    ) -> None:
        """Register a resource handler on the server."""
        pass

    def registerPrompt(
        self, name: str, config: Any, handler: Callable[..., Awaitable[Any]]
    ) -> None:
        """Register a prompt handler on the server."""
        pass


class MCPIntegration:
    """Class-based MCP integration for Payments.

    Provides a clean methods API to configure paywall, decorate handlers and attach
    registrations to a server implementation.
    """

    def __init__(self, payments_service: Any) -> None:
        """Initialize the integration with a Payments service instance.

        Args:
            payments_service: The initialized Payments client
        """
        self._payments = payments_service
        self._authenticator = PaywallAuthenticator(self._payments)
        self._credits_context = CreditsContextProvider()
        self._decorator = PaywallDecorator(
            self._payments, self._authenticator, self._credits_context
        )

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
            extra, agent_id, server_name, method
        )

    def attach(self, server: _AttachableServer):
        """Attach helpers to a server and return registration methods.

        Args:
            server: An object exposing registerTool/registerResource/registerPrompt

        Returns:
            An object with methods to register protected handlers on the server
        """

        integration = self

        class _Registrar:
            """Helper that registers protected handlers into the provided server."""

            def registerTool(
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
                server.registerTool(name, config, protected)

            def registerResource(
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
                server.registerResource(name, template, config, protected)

            def registerPrompt(
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
                server.registerPrompt(name, config, protected)

        return _Registrar()


def build_mcp_integration(payments_service: Any) -> MCPIntegration:
    """Factory that builds the class-based MCP integration.

    Args:
        payments_service: The initialized Payments client

    Returns:
        MCPIntegration instance
    """
    return MCPIntegration(payments_service)
