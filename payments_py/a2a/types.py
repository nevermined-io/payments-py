"""Internal helper types for payments_py.a2a package."""

from __future__ import annotations
from a2a.types import MessageSendParams as MessageSendParams  # noqa: F401

from dataclasses import dataclass
from typing import Any, Dict, TypedDict

# ------------------------------------------------------------------
# Public aliases re-exported from a2a SDK (keep simple dict stubs)
# ------------------------------------------------------------------
AgentCard = Dict[str, Any]


# ------------------------------------------------------------------
# Core helper types
# ------------------------------------------------------------------
class ClientRegistryOptions(TypedDict):  # noqa: D101
    agent_base_url: str
    agent_id: str
    plan_id: str


class PaymentMetadata(TypedDict, total=False):  # noqa: D101
    creditsUsed: int
    planId: str
    paymentType: str
    costDescription: str


class PaymentAgentCardMetadata(TypedDict, total=False):  # noqa: D101
    paymentType: str  # "fixed" | "dynamic"
    credits: int
    planId: str
    agentId: str
    costDescription: str
    isTrialPlan: bool


@dataclass
class HttpRequestContext:  # noqa: D101
    bearer_token: str
    url_requested: str
    http_method_requested: str
    validation: Dict[str, Any]
