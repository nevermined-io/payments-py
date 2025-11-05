"""
Types for MCP paywall functionality.
"""

from typing import Any, Callable, Dict, TypedDict, Union


class AuthResult(TypedDict):
    """Result returned by authentication routines."""

    requestId: str
    token: str
    agentId: str
    logicalUrl: str
    agentRequest: Dict[str, Any]  # StartAgentRequest as dict


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


class PaywallContext(TypedDict):
    """Context provided to paywall-protected handlers."""

    auth_result: AuthResult
    credits: int
    agent_request: Dict[str, Any]  # StartAgentRequest as dict
