"""
AgentCore Gateway Types for x402 Payment Integration.

Pydantic models for MCP JSON-RPC 2.0 request/response structures
as used by Amazon Bedrock AgentCore Gateway.
"""

from typing import Any, Optional, Union, Callable, Awaitable
from pydantic import BaseModel, Field, ConfigDict
from dataclasses import dataclass, field

from payments_py.x402.types import X402PaymentRequired, VerifyResponse, SettleResponse


# =============================================================================
# MCP JSON-RPC 2.0 Types
# =============================================================================


class MCPParams(BaseModel):
    """MCP tools/call params."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="allow")


class MCPRequestBody(BaseModel):
    """MCP JSON-RPC 2.0 request body."""

    jsonrpc: str = "2.0"
    id: Union[str, int] = "1"
    method: str
    params: Optional[MCPParams] = None

    model_config = ConfigDict(extra="allow")


class MCPContentItem(BaseModel):
    """MCP content item (text, image, etc.)."""

    type: str = "text"
    text: Optional[str] = None

    model_config = ConfigDict(extra="allow")


class MCPResult(BaseModel):
    """MCP result object."""

    content: list[MCPContentItem] = Field(default_factory=list)
    is_error: bool = Field(False, alias="isError")
    _meta: Optional[dict[str, Any]] = None

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class MCPResponseBody(BaseModel):
    """MCP JSON-RPC 2.0 response body."""

    jsonrpc: str = "2.0"
    id: Union[str, int] = "1"
    result: Optional[MCPResult] = None
    error: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="allow")


# =============================================================================
# AgentCore Gateway Types
# =============================================================================


class GatewayRequest(BaseModel):
    """AgentCore Gateway request structure."""

    headers: dict[str, str] = Field(default_factory=dict)
    body: MCPRequestBody

    model_config = ConfigDict(extra="allow")


class GatewayResponse(BaseModel):
    """AgentCore Gateway response structure."""

    headers: dict[str, str] = Field(default_factory=dict)
    body: Union[MCPResponseBody, dict[str, Any]]
    status_code: int = Field(200, alias="statusCode")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class InterceptorEvent(BaseModel):
    """
    Lambda event from AgentCore Gateway interceptor.

    Contains either:
    - gatewayRequest only (REQUEST phase)
    - gatewayRequest + gatewayResponse (RESPONSE phase)
    """

    gateway_request: Optional[GatewayRequest] = Field(None, alias="gatewayRequest")
    gateway_response: Optional[GatewayResponse] = Field(None, alias="gatewayResponse")

    model_config = ConfigDict(populate_by_name=True, extra="allow")


class InterceptorMCPEvent(BaseModel):
    """Full interceptor event wrapper."""

    mcp: InterceptorEvent

    model_config = ConfigDict(extra="allow")


# =============================================================================
# Interceptor Output Types
# =============================================================================


class TransformedGatewayRequest(BaseModel):
    """Transformed request to forward to target."""

    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any]


class TransformedGatewayResponse(BaseModel):
    """Transformed response to return to client."""

    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any]
    status_code: int = Field(200, alias="statusCode")

    model_config = ConfigDict(populate_by_name=True)


class InterceptorOutput(BaseModel):
    """
    Lambda response for AgentCore Gateway interceptor.

    Must include interceptorOutputVersion and either:
    - transformedGatewayRequest (REQUEST phase)
    - transformedGatewayResponse (RESPONSE phase)
    """

    interceptor_output_version: str = Field("1.0", alias="interceptorOutputVersion")
    mcp: dict[str, Any]  # Contains transformedGatewayRequest or transformedGatewayResponse

    model_config = ConfigDict(populate_by_name=True)


# =============================================================================
# Configuration Types
# =============================================================================

# Type aliases for hook callbacks
CreditsCallable = Callable[[MCPRequestBody], Union[int, Awaitable[int]]]
BeforeVerifyHook = Callable[[GatewayRequest, X402PaymentRequired], Awaitable[None]]
AfterVerifyHook = Callable[[GatewayRequest, VerifyResponse], Awaitable[None]]
AfterSettleHook = Callable[[GatewayRequest, int, SettleResponse], Awaitable[None]]
PaymentErrorHook = Callable[
    [Exception, GatewayRequest], Awaitable[Optional[InterceptorOutput]]
]


@dataclass
class InterceptorConfig:
    """
    Configuration for a specific tool or route.

    Example with fixed credits:
        InterceptorConfig(plan_id="123", credits=5)

    Example with dynamic credits:
        InterceptorConfig(
            plan_id="123",
            credits=lambda req: calculate_credits(req)
        )
    """

    # The Nevermined plan ID (required)
    plan_id: str

    # Number of credits to charge (default: 1)
    # Can be static int or callable (sync/async) that takes MCPRequestBody
    credits: Union[int, CreditsCallable] = 1

    # Optional agent ID
    agent_id: Optional[str] = None

    # Protected resource endpoint URL (optional)
    endpoint: Optional[str] = None

    # Network identifier (default: Base Sepolia)
    network: str = "eip155:84532"

    # Human-readable description for 402 response
    description: Optional[str] = None


@dataclass
class InterceptorOptions:
    """
    Global options for the AgentCore interceptor.
    """

    # Header name(s) to check for x402 token
    token_header: Union[str, list[str]] = field(
        default_factory=lambda: ["payment-signature", "PAYMENT-SIGNATURE"]
    )

    # Methods that require payment (default: only tools/call)
    billable_methods: list[str] = field(
        default_factory=lambda: ["tools/call"]
    )

    # Default credits if not specified per-tool
    default_credits: int = 1

    # Hook called before verification
    on_before_verify: Optional[BeforeVerifyHook] = None

    # Hook called after successful verification
    on_after_verify: Optional[AfterVerifyHook] = None

    # Hook called after successful settlement
    on_after_settle: Optional[AfterSettleHook] = None

    # Custom error handler for payment failures
    on_payment_error: Optional[PaymentErrorHook] = None
