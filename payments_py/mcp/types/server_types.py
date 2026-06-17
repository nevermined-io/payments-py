"""
Type definitions for the Simplified MCP Server API.

This module defines all types for the high-level API that abstracts away
the complexity of McpServer, Transport, and FastAPI details.

Examples:
    >>> from payments_py.mcp.types import McpServerConfig, ServerInfo
    >>> config: McpServerConfig = {
    ...     "port": 5001,
    ...     "agentId": "abc123",
    ...     "serverName": "my-server"
    ... }
"""

from typing import Any, Awaitable, Callable, Dict, List, Optional, Union
from typing_extensions import TypedDict

from ...environments import EnvironmentName

# =============================================================================
# CONFIGURATION TYPES
# =============================================================================


class McpToolConfig(TypedDict, total=False):
    """Configuration for a tool.

    Attributes:
        title: Human-readable title for the tool (optional).
        description: Description of what the tool does (required).
        inputSchema: Pydantic model or dict for input validation (optional).
        outputSchema: JSON Schema dict for output validation (optional).
    """

    title: str
    description: str  # Required
    inputSchema: Any  # Pydantic model or dict
    outputSchema: Optional[Dict[str, Any]]


class McpResourceConfig(TypedDict, total=False):
    """Configuration for a resource.

    Attributes:
        name: Human-readable name for the resource (required).
        description: Description of the resource (optional).
        mimeType: MIME type of the resource content (optional).
    """

    name: str  # Required
    description: Optional[str]
    mimeType: Optional[str]


class McpPromptConfig(TypedDict, total=False):
    """Configuration for a prompt.

    Attributes:
        name: Human-readable name for the prompt (required).
        description: Description of the prompt (optional).
        inputSchema: Pydantic model or dict for arguments (optional).
    """

    name: str  # Required
    description: Optional[str]
    inputSchema: Any  # Pydantic model or dict


class McpRegistrationOptions(TypedDict, total=False):
    """Options for tool/resource/prompt registration.

    Attributes:
        credits: Credits to charge per call. Can be a fixed int or a callable
                that receives context with args and result. Defaults to 1.
        onRedeemError: What to do if credit redemption fails.
                      Either 'ignore' (default) or 'propagate'.
    """

    credits: Union[int, Callable[[Dict[str, Any]], int]]
    onRedeemError: str  # 'ignore' | 'propagate'


# =============================================================================
# HANDLER TYPES
# =============================================================================


# Handler function for a tool
ToolHandler = Callable[..., Union[Awaitable[Any], Any]]

# Handler function for a resource
ResourceHandler = Callable[..., Union[Awaitable[Any], Any]]

# Handler function for a prompt
PromptHandler = Callable[..., Union[Awaitable[Any], Any]]


# =============================================================================
# CONTEXT TYPES
# =============================================================================


class ToolContext(TypedDict, total=False):
    """Context passed to tool handlers.

    Attributes:
        requestId: Request ID for tracking (optional).
        credits: Credits available/charged (optional).
        extra: Raw MCP extra context (optional).
    """

    requestId: Optional[str]
    credits: Optional[int]
    extra: Any


class ResourceContext(TypedDict, total=False):
    """Context passed to resource handlers.

    Attributes:
        requestId: Request ID for tracking (optional).
        credits: Credits available/charged (optional).
        extra: Raw MCP extra context (optional).
    """

    requestId: Optional[str]
    credits: Optional[int]
    extra: Any


class PromptContext(TypedDict, total=False):
    """Context passed to prompt handlers.

    Attributes:
        requestId: Request ID for tracking (optional).
        credits: Credits available/charged (optional).
        extra: Raw MCP extra context (optional).
    """

    requestId: Optional[str]
    credits: Optional[int]
    extra: Any


# =============================================================================
# SERVER CONFIGURATION
# =============================================================================


class McpServerConfig(TypedDict, total=False):
    """Configuration for starting the MCP server.

    Attributes:
        port: Port to listen on (required).
        agentId: Agent ID (DID) for Nevermined (required).
        serverName: Human-readable server name (required).
        baseUrl: Base URL of the server. Defaults to http://localhost:{port}.
        host: Host to bind to. Defaults to '0.0.0.0'.
        environment: Nevermined environment. Defaults to Payments instance env.
        version: Server version. Defaults to '1.0.0'.
        description: Server description (optional).
        corsOrigins: CORS origins. Defaults to '*'.
        enableOAuthDiscovery: Enable OAuth discovery endpoints. Defaults to True.
        enableClientRegistration: Enable client registration. Defaults to True.
        enableHealthCheck: Enable health check endpoint. Defaults to True.
        enableServerInfo: Enable server info endpoint. Defaults to True.
        onStart: Callback when server starts (optional).
        onLog: Callback for logging (optional).
    """

    port: int  # Required
    agentId: str  # Required
    serverName: str  # Required
    baseUrl: Optional[str]
    host: Optional[str]
    environment: Optional[EnvironmentName]
    version: Optional[str]
    description: Optional[str]
    corsOrigins: Union[str, List[str], None]
    enableOAuthDiscovery: Optional[bool]
    enableClientRegistration: Optional[bool]
    enableHealthCheck: Optional[bool]
    enableServerInfo: Optional[bool]
    onStart: Optional[Callable[[Dict[str, Any]], None]]
    onLog: Optional[Callable[[str, Optional[str]], None]]


class ServerInfo(TypedDict):
    """Information about a running server.

    Attributes:
        baseUrl: Base URL of the server.
        port: Port the server is listening on.
        tools: List of registered tool names.
        resources: List of registered resource URIs.
        prompts: List of registered prompt names.
    """

    baseUrl: str
    port: int
    tools: List[str]
    resources: List[str]
    prompts: List[str]


class McpServerResult(TypedDict):
    """Result of starting the server.

    Attributes:
        info: Server information (baseUrl, port, tools, resources, prompts).
        stop: Async function to stop the server gracefully.
    """

    info: ServerInfo
    stop: Callable[[], Awaitable[None]]


# =============================================================================
# INTERNAL REGISTRATION TYPES
# =============================================================================


class ToolRegistration(TypedDict):
    """Internal registration entry for a tool.

    Attributes:
        name: Tool name identifier.
        config: Tool configuration.
        handler: Tool handler function.
        options: Registration options (credits, onRedeemError).
    """

    name: str
    config: McpToolConfig
    handler: ToolHandler
    options: McpRegistrationOptions


class ResourceRegistration(TypedDict):
    """Internal registration entry for a resource.

    Attributes:
        uri: Resource URI pattern.
        config: Resource configuration.
        handler: Resource handler function.
        options: Registration options (credits, onRedeemError).
    """

    uri: str
    config: McpResourceConfig
    handler: ResourceHandler
    options: McpRegistrationOptions


class PromptRegistration(TypedDict):
    """Internal registration entry for a prompt.

    Attributes:
        name: Prompt name identifier.
        config: Prompt configuration.
        handler: Prompt handler function.
        options: Registration options (credits, onRedeemError).
    """

    name: str
    config: McpPromptConfig
    handler: PromptHandler
    options: McpRegistrationOptions
