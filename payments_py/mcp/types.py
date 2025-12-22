"""
Types for MCP paywall functionality.
"""

from typing import Any, Callable, Dict, TypedDict, Union


class AuthResult(TypedDict, total=False):
    """Result returned by authentication routines using x402 tokens."""

    token: str
    agentId: str
    logicalUrl: str
    plan_id: str
    subscriber_address: str


CreditsOption = Union[int, Callable[[Dict[str, Any]], int]]


class BasePaywallOptions(TypedDict, total=False):
    """Common paywall options shared by all handler kinds."""

    name: str
    credits: CreditsOption
    onRedeemError: str  # 'ignore' | 'propagate'


class ToolOptions(BasePaywallOptions):
    """Paywall options for a tool handler."""

    kind: str  # 'tool'


class ResourceOptions(BasePaywallOptions):
    """Paywall options for a resource handler."""

    kind: str  # 'resource'


class PromptOptions(BasePaywallOptions):
    """Paywall options for a prompt handler."""

    kind: str  # 'prompt'


PaywallOptions = Union[ToolOptions, ResourceOptions, PromptOptions]


class PaywallContext(TypedDict, total=False):
    """Context provided to paywall-protected handlers using x402 tokens."""

    auth_result: AuthResult
    credits: int
    plan_id: str
    subscriber_address: str
