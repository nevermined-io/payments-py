"""
Type definitions for the Nevermined Payments protocol.
"""

from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# Address type alias
Address = str


class PaymentOptions(BaseModel):
    """
    Options for initializing the Payments class.
    """

    environment: str
    nvm_api_key: Optional[str] = None
    return_url: Optional[str] = None
    app_id: Optional[str] = None
    version: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class Endpoint(BaseModel):
    """
    Endpoint for a service. Dict with HTTP verb as key and URL as value.
    """

    verb: str
    url: str


class AuthType(str, Enum):
    """
    Allowed authentication types for AgentAPIAttributes.
    """

    NONE = "none"
    BASIC = "basic"
    OAUTH = "oauth"
    BEARER = "bearer"


class AgentAPIAttributes(BaseModel):
    """
    API attributes for an agent.
    """

    endpoints: List[Endpoint]
    open_endpoints: Optional[List[str]] = None
    open_api_url: Optional[str] = None
    auth_type: Optional[AuthType] = AuthType.NONE
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class AgentMetadata(BaseModel):
    """
    Metadata for an agent.
    """

    name: str
    description: Optional[str] = None
    author: Optional[str] = None
    license: Optional[str] = None
    tags: Optional[List[str]] = None
    integration: Optional[str] = None
    sample_link: Optional[str] = None
    api_description: Optional[str] = None
    date_created: Optional[str] = None


class PlanMetadata(AgentMetadata):
    """
    Metadata for a payment plan, extends AgentMetadata.
    """

    is_trial_plan: Optional[bool] = False


class PlanPriceType(Enum):
    """
    Different types of prices that can be configured for a plan.
    0 - FIXED_PRICE, 1 - FIXED_FIAT_PRICE, 2 - SMART_CONTRACT_PRICE
    """

    FIXED_PRICE = 0
    FIXED_FIAT_PRICE = 1
    SMART_CONTRACT_PRICE = 2


class PlanCreditsType(Enum):
    """
    Different types of credits that can be obtained when purchasing a plan.
    0 - EXPIRABLE, 1 - FIXED, 2 - DYNAMIC
    """

    EXPIRABLE = 0
    FIXED = 1
    DYNAMIC = 2


class PlanRedemptionType(Enum):
    """
    Different types of redemptions criterias that can be used when redeeming credits.
    0 - ONLY_GLOBAL_ROLE, 1 - ONLY_OWNER, 2 - ONLY_PLAN_ROLE
    """

    ONLY_GLOBAL_ROLE = 0
    ONLY_OWNER = 1
    ONLY_PLAN_ROLE = 2


class PlanPriceConfig(BaseModel):
    """
    Definition of the price configuration for a Payment Plan.
    """

    token_address: Optional[str] = None
    amounts: List[int] = Field(default_factory=list)
    receivers: List[str] = Field(default_factory=list)
    contract_address: Optional[str] = None
    fee_controller: Optional[str] = None
    external_price_address: Optional[str] = None
    template_address: Optional[str] = None
    is_crypto: bool = False


class PlanCreditsConfig(BaseModel):
    """
    Definition of the credits configuration for a payment plan.
    """

    is_redemption_amount_fixed: bool = False
    redemption_type: PlanRedemptionType
    proof_required: bool
    duration_secs: int
    amount: str
    min_amount: int
    max_amount: int
    nft_address: Optional[str] = None


class PlanBalance(BaseModel):
    """
    Balance information for a payment plan.
    """

    model_config = ConfigDict(populate_by_name=True)

    plan_id: str = Field(alias="planId")
    plan_name: str = Field(alias="planName")
    plan_type: str = Field(alias="planType")
    holder_address: str = Field(alias="holderAddress")
    balance: int
    credits_contract: str = Field(alias="creditsContract")
    is_subscriber: bool = Field(alias="isSubscriber")
    price_per_credit: float = Field(alias="pricePerCredit")
    batch: Optional[bool] = None


class PaginationOptions(BaseModel):
    """
    Options for pagination in API requests to the Nevermined API.
    """

    sort_by: Optional[str] = None
    sort_order: str = "desc"
    page: int = 1
    offset: int = 10


class AgentTaskStatus(str, Enum):
    """
    Status of an agent task.
    """

    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PENDING = "PENDING"


class TrackAgentSubTaskDto(BaseModel):
    """
    Data transfer object for tracking agent sub tasks.
    """

    agent_request_id: str
    credits_to_redeem: Optional[int] = 0
    tag: Optional[str] = None
    description: Optional[str] = None
    status: Optional[AgentTaskStatus] = None


class StartAgentRequest(BaseModel):
    """
    Information about the initialization of an agent request.
    """

    model_config = ConfigDict(populate_by_name=True)

    agent_request_id: str = Field(alias="agentRequestId")
    agent_name: str = Field(alias="agentName")
    agent_id: str = Field(alias="agentId")
    balance: PlanBalance
    url_matching: str = Field(alias="urlMatching")
    verb_matching: str = Field(alias="verbMatching")
    batch: bool


class AgentAccessCredentials(BaseModel):
    """
    Access credentials for an agent.
    """

    access_token: str
    proxies: Optional[List[str]] = None


class NvmAPIResult(BaseModel):
    """
    Result of a Nevermined API operation.
    """

    success: bool
    message: Optional[str] = None
    tx_hash: Optional[str] = None
    http_status: Optional[int] = None
    data: Optional[Dict[str, Any]] = None
    when: Optional[str] = None
