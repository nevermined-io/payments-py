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

    Defines the API endpoints and authentication configuration for an agent.
    Used when registering agents with :meth:`payments.agents.register_agent` or
    :meth:`payments.agents.register_agent_and_plan`.

    Args:
        endpoints: List of endpoint dictionaries with HTTP verb as key and URL as value.
                  URLs can include placeholders like `:agentId` which will be replaced.
        open_endpoints: List of endpoints that don't require authentication
        agent_definition_url: URL to the agent definition. Can be an OpenAPI spec, MCP Manifest, or A2A agent card. This field is mandatory.
        auth_type: Authentication type (default: AuthType.NONE)
        username: Username for basic auth (if auth_type is BASIC)
        password: Password for basic auth (if auth_type is BASIC)
        token: Token for bearer auth (if auth_type is BEARER)
        api_key: API key for authentication
        headers: Additional headers to include in requests

    Example::
        agent_api = AgentAPIAttributes(
            endpoints=[
                {"POST": "https://example.com/api/v1/agents/:agentId/tasks"},
                {"GET": "https://example.com/api/v1/agents/:agentId/tasks/:taskId"}
            ],
            agent_definition_url="https://example.com/api/v1/openapi.json",  # OpenAPI spec, MCP Manifest, or A2A agent card
            auth_type=AuthType.BEARER
        )
    """

    endpoints: List[Endpoint]
    open_endpoints: Optional[List[str]] = None
    agent_definition_url: str
    auth_type: Optional[AuthType] = AuthType.NONE
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    api_key: Optional[str] = None
    headers: Optional[Dict[str, str]] = None


class AgentMetadata(BaseModel):
    """
    Metadata for an agent.

    Used when registering agents with :meth:`payments.agents.register_agent` or
    :meth:`payments.agents.register_agent_and_plan`.

    Args:
        name: The name of the agent (required)
        description: A description of the agent
        author: The author of the agent
        license: License information
        tags: List of tags for categorization
        integration: Integration type
        sample_link: Link to a sample/demo
        api_description: Description of the API
        date_created: ISO date string of creation date

    Example::
        agent_metadata = AgentMetadata(
            name="My AI Agent",
            description="A helpful AI assistant",
            tags=["ai", "assistant"],
            author="John Doe"
        )
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

    Used when registering payment plans with methods like :meth:`payments.plans.register_credits_plan`,
    :meth:`payments.plans.register_time_plan`, or :meth:`payments.agents.register_agent_and_plan`.

    Args:
        name: The name of the plan (required, inherited from AgentMetadata)
        description: A description of the plan (inherited from AgentMetadata)
        is_trial_plan: Whether this is a trial plan (can only be purchased once per user)
        All other fields from :class:`AgentMetadata` are also available

    Example::
        plan_metadata = PlanMetadata(
            name="Basic Plan",
            description="100 credits plan",
            is_trial_plan=False
        )

        # For trial plans
        trial_metadata = PlanMetadata(
            name="Free Trial",
            description="10 free credits",
            is_trial_plan=True
        )
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

    Use helper functions from :mod:`payments_py.plans` to create instances:
    - :func:`payments_py.plans.get_fiat_price_config` for fiat payments
    - :func:`payments_py.plans.get_erc20_price_config` for ERC20 token payments
    - :func:`payments_py.plans.get_native_token_price_config` for native token (ETH) payments
    - :func:`payments_py.plans.get_free_price_config` for free plans

    Args:
        token_address: Address of the ERC20 token (ZeroAddress for native token or fiat)
        amounts: List of payment amounts in smallest unit
        receivers: List of receiver addresses
        contract_address: Smart contract address (usually ZeroAddress)
        fee_controller: Fee controller address (usually ZeroAddress)
        external_price_address: External price oracle address (usually ZeroAddress)
        template_address: Template address (usually ZeroAddress)
        is_crypto: Whether this is a crypto payment (False for fiat)

    Example::
        # Don't create directly - use helper functions instead:
        from payments_py.plans import get_erc20_price_config

        price_config = get_erc20_price_config(20, ERC20_ADDRESS, builder_address)
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

    Use helper functions from :mod:`payments_py.plans` to create instances:
    - :func:`payments_py.plans.get_fixed_credits_config` for fixed credits per request
    - :func:`payments_py.plans.get_dynamic_credits_config` for variable credits per request
    - :func:`payments_py.plans.get_expirable_duration_config` for time-limited plans
    - :func:`payments_py.plans.get_non_expirable_duration_config` for non-expiring plans

    Args:
        is_redemption_amount_fixed: Whether credits consumed per request is fixed (True) or variable (False)
        redemption_type: Who can redeem credits (PlanRedemptionType enum)
        proof_required: Whether proof is required for redemption
        duration_secs: Duration in seconds (0 for non-expirable, >0 for expirable)
        amount: Total credits granted as string
        min_amount: Minimum credits consumed per request
        max_amount: Maximum credits consumed per request
        nft_address: Optional NFT address

    Example::
        # Don't create directly - use helper functions instead:
        from payments_py.plans import get_fixed_credits_config, ONE_DAY_DURATION, get_expirable_duration_config

        # Fixed credits plan
        credits_config = get_fixed_credits_config(100, credits_per_request=1)

        # Time-limited plan
        time_config = get_expirable_duration_config(ONE_DAY_DURATION)
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
