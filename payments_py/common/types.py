"""
Type definitions for the Nevermined Payments protocol.
"""

from typing import Optional, List, Dict, Any, Union
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum

# Address type alias
Address = str


class PaymentOptions(BaseModel):
    """
    Options for initializing the Payments class.

    Args:
        environment: Nevermined environment (e.g. ``"sandbox"``, ``"live"``).
        nvm_api_key: NVM API key used to authenticate against the backend.
        return_url: Optional URL to return to after login (browser flows).
        app_id: Optional application identifier stamped on registered assets.
        version: Optional SDK version reported to the backend.
        api_version: Optional backend API version (monorepo ``MAJOR.MINOR``,
            e.g. ``"1.1"``) sent as the ``Nevermined-Version`` header on
            every backend request. Defaults to
            :data:`payments_py.common.api_version.LOCKED_API_VERSION` — the
            backend API version this SDK release is built and tested
            against. Override only to target a different backend contract;
            see https://docs. An
            empty string is treated as unset (the default applies) — the
            SDK never sends an empty ``Nevermined-Version`` header.nevermined.app/api-reference/versioning.
        headers: Optional default headers to merge into every request.
        organization_id: Optional organization id (e.g. ``"org-..."``) used
            as the active workspace for every authenticated backend call.
            When set, the SDK forwards it as the ``X-Current-Org-Id``
            request header so the backend scopes published agents, plans,
            and other workspace-aware resources to this organization.
            If omitted, the backend falls back to the API key's org tag
            or the caller's most-recent active membership (see
            ``CurrentOrgContextGuard`` in nvm-monorepo). Override per-call
            via the ``organization_id`` argument on publish methods.
    """

    environment: str
    nvm_api_key: Optional[str] = None
    return_url: Optional[str] = None
    app_id: Optional[str] = None
    version: Optional[str] = None
    api_version: Optional[str] = None
    headers: Optional[Dict[str, str]] = None
    organization_id: Optional[str] = None


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

    All fields are optional. Provide ``endpoints`` and/or
    ``agent_definition_url`` only when you want the platform to enforce a
    route-level allowlist as **Additional Security** (defense-in-depth on top
    of any per-route gating the Payments library applies in your agent), or
    when you want a discoverable agent definition. Otherwise omit them — your
    library middleware remains the sole gate.

    Used when registering agents with :meth:`payments.agents.register_agent` or
    :meth:`payments.agents.register_agent_and_plan`.

    Args:
        endpoints: Optional allowlist of endpoint dictionaries with HTTP verb
                  as key and URL as value. When provided, the Nevermined
                  platform enforces this list as Additional Security on x402
                  verify. URLs can include placeholders like ``:agentId``.
        open_endpoints: Optional list of endpoints that don't require subscription.
        agent_definition_url: Optional URL to a discoverable agent definition
                  (OpenAPI spec, MCP Manifest, or A2A agent card). Stored as
                  metadata; not consumed at runtime by the platform.
        auth_type: Authentication type (default: AuthType.NONE)
        username: Username for basic auth (if auth_type is BASIC)
        password: Password for basic auth (if auth_type is BASIC)
        token: Token for bearer auth (if auth_type is BEARER)
        api_key: API key for authentication
        headers: Additional headers to include in requests

    Example::

        # Minimal (recommended): your library middleware handles per-route gating
        agent_api = AgentAPIAttributes(
            auth_type=AuthType.BEARER,
            token="sk-test",
        )

        # With Additional Security: platform enforces a route allowlist
        agent_api = AgentAPIAttributes(
            endpoints=[
                {"verb": "POST", "url": "https://example.com/api/v1/agents/:agentId/tasks"},
            ],
            agent_definition_url="https://example.com/api/v1/openapi.json",
            auth_type=AuthType.BEARER,
        )
    """

    endpoints: Optional[List[Endpoint]] = None
    open_endpoints: Optional[List[str]] = None
    agent_definition_url: Optional[str] = None
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


class Currency(str, Enum):
    """
    Supported currencies for payment plans.

    - Fiat: USD, EUR (processed via Stripe)
    - Crypto: USDC, EURC (ERC20 stablecoins on Base)
    """

    USD = "USD"
    EUR = "EUR"
    USDC = "USDC"
    EURC = "EURC"


# EURC token address on Base Mainnet (chain 8453)
EURC_TOKEN_ADDRESS: str = "0x60a3E35Cc302bFA44Cb288Bc5a4F316Fdb1adb42"
# EURC token address on Base Sepolia testnet (chain 84532)
EURC_TOKEN_ADDRESS_TESTNET: str = "0x808456652fdb597867f38412077A9182bf77359F"


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
    0 - ONLY_GLOBAL_ROLE, 1 - ONLY_OWNER, 2 - ONLY_PLAN_ROLE, 4 - ONLY_SUBSCRIBER
    """

    ONLY_GLOBAL_ROLE = 0
    ONLY_OWNER = 1
    ONLY_PLAN_ROLE = 2
    ONLY_SUBSCRIBER = 4


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
        currency: Optional currency code for off-chain denomination.
            For fiat payments, use an uppercase ISO-4217 code (e.g. ``"USD"``, ``"EUR"``).
            For stablecoins, use the token symbol (e.g. ``"EURC"``).
            For pure ERC20 or native token plans, this is typically ``None``.

    Example::
        # Don't create directly - use helper functions instead:
        from payments_py.plans import get_erc20_price_config

        price_config = get_erc20_price_config(20, ERC20_ADDRESS, builder_address)
    """

    token_address: Optional[str] = None
    amounts: List[Union[int, str]] = Field(default_factory=list)
    receivers: List[str] = Field(default_factory=list)
    contract_address: Optional[str] = None
    fee_controller: Optional[str] = None
    external_price_address: Optional[str] = None
    template_address: Optional[str] = None
    is_crypto: bool = False
    currency: Optional[str] = None

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Override to serialize amounts as strings for backend BigInt compatibility."""
        d = super().model_dump(**kwargs)
        if "amounts" in d:
            d["amounts"] = [str(a) for a in d["amounts"]]
        return d


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
        onchain_mirror: Whether burns of these credits are mirrored on-chain.
            Defaults to ``False`` — keeps the ledger off-chain in the API's
            Postgres, and recovers gracefully when API responses omit the
            field entirely. ``True`` enables the API-side
            ``OnchainMirrorWorker`` that replays each burn to
            ``NFT1155Credits`` for audit. Accepts the camelCase alias
            ``onchainMirror`` so plans deserialized from API JSON also
            resolve cleanly into this field regardless of casing.
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

    model_config = ConfigDict(populate_by_name=True)

    is_redemption_amount_fixed: bool = False
    redemption_type: PlanRedemptionType
    onchain_mirror: bool = Field(default=False, alias="onchainMirror")
    duration_secs: int
    amount: str
    min_amount: int
    max_amount: int
    nft_address: Optional[str] = None

    def model_dump(self, **kwargs: Any) -> Dict[str, Any]:
        """Serialize uint256-typed fields as decimal strings.

        The Nevermined backend tightened uint256 validation on plan and
        agent-and-plan registration. JSON numbers are rejected for fields
        that map to Solidity ``uint256`` (``durationSecs``, ``amount``,
        ``minAmount``, ``maxAmount``) because numbers larger than
        ``Number.MAX_SAFE_INTEGER`` lose precision in transit. The
        TypeScript SDK gets this for free via the ``BigInt``
        ``jsonReplacer``; Python emits the same wire shape by
        stringifying here.
        """
        d = super().model_dump(**kwargs)
        for field in ("duration_secs", "amount", "min_amount", "max_amount"):
            if field in d and d[field] is not None:
                d[field] = str(d[field])
        return d


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


# ---------------------------------------------------------------------------
# Organizations
# ---------------------------------------------------------------------------


class OrganizationMemberRole(str, Enum):
    """Role of a member inside an organization.

    Mirrors ``OrganizationMemberRole`` from ``@nevermined-io/commons`` in the
    nvm-monorepo backend. ``CLIENT`` is retained for backwards compatibility
    with historical rows; new memberships only use ``ADMIN`` or ``MEMBER``.
    """

    ADMIN = "Admin"
    MEMBER = "Member"
    CLIENT = "Client"


class OrganizationType(str, Enum):
    """Tier of an organization. Mirrors the backend ``OrganizationType`` enum
    (``libs/commons/src/lib/types/types.ts`` in nvm-monorepo).

    No ``Free`` member — the backend never emits it (legacy bucket replaced
    by ``Lapsed``). ``Other`` is the legacy pre-tiered-pricing bucket and
    is still returned for orgs that pre-date the tier system.
    """

    PREMIUM = "Premium"
    ENTERPRISE = "Enterprise"
    LAPSED = "Lapsed"
    OTHER = "Other"


class MyMembership(BaseModel):
    """A single organization the authenticated user is an active member of.

    Returned by :meth:`OrganizationsAPI.get_my_memberships` and used by
    clients to power workspace pickers and "where will this publish?" UX.

    Shape mirrors ``MyMembershipDto`` in the Nevermined backend
    (``apps/api/src/organizations/dto/my-membership.dto.ts``).
    """

    model_config = ConfigDict(populate_by_name=True)

    org_id: str = Field(alias="orgId")
    org_name: str = Field(alias="orgName")
    role: OrganizationMemberRole
    # ``Union[OrganizationType, str]`` for forward-compat: if the backend
    # introduces a new tier before the SDK ships an enum update,
    # ``model_validate`` falls through to a bare string instead of raising.
    # Matches the same shape used by ``OrganizationActivityEvent.event_type``.
    org_type: Union[OrganizationType, str] = Field(alias="orgType")
    is_admin: bool = Field(alias="isAdmin")
    # `True` when the org has at least one ``organizationSubscription`` row —
    # the org has previously been associated with a paid tier (active,
    # past_due, trialing, lapsed, or canceled). Combined with
    # ``org_type == Lapsed`` it distinguishes "subscription expired" from
    # "free org that never subscribed".
    has_subscription_history: bool = Field(
        default=False, alias="hasSubscriptionHistory"
    )


class OrganizationActivityEventType(str, Enum):
    """Known event types emitted into the organization activity feed.

    The SDK accepts unknown strings as well — when the backend introduces
    a new event type, ``OrganizationActivityEvent.event_type`` stays a
    plain ``str`` so consumers don't break on first-encounter.
    """

    # Membership lifecycle
    MEMBER_INVITED = "member.invited"
    MEMBER_JOINED = "member.joined"
    MEMBER_ROLE_CHANGED = "member.role_changed"
    MEMBER_DEACTIVATED = "member.deactivated"
    MEMBER_REACTIVATED = "member.reactivated"
    MEMBER_REMOVED = "member.removed"
    INVITATION_REVOKED = "invitation.revoked"
    INVITATION_EXPIRED = "invitation.expired"
    # Resource lifecycle
    AGENT_CREATED = "agent.created"
    PLAN_CREATED = "plan.created"
    PLAN_PURCHASED = "plan.purchased"
    # Customer lifecycle
    CUSTOMER_ADDED = "customer.added"
    CUSTOMER_BLOCKED = "customer.blocked"
    CUSTOMER_UNBLOCKED = "customer.unblocked"
    # Subscription lifecycle
    SUBSCRIPTION_UPGRADED = "subscription.upgraded"
    SUBSCRIPTION_DOWNGRADED = "subscription.downgraded"
    SUBSCRIPTION_CANCELED = "subscription.canceled"
    SUBSCRIPTION_LAPSED = "subscription.lapsed"
    # Webhook delivery
    WEBHOOK_DELIVERED = "webhook.delivered"
    WEBHOOK_FAILED = "webhook.failed"


class OrganizationActivityEventSubject(BaseModel):
    """Resource an activity event is about.

    ``kind`` describes the resource type (``plan``, ``agent``, ``member``,
    ``subscription``, ``invitation``, ``customer``, ``webhook``) and ``id``
    is the resource identifier. Extras vary by kind — invitations include
    ``role`` + ``email``, members include ``role`` + ``userId``,
    subscriptions include ``tier``. The model accepts unknown keys for
    forward-compatibility.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    kind: str
    id: str


class OrganizationActivityEvent(BaseModel):
    """A single event emitted into the organization activity feed.

    Shape mirrors ``OrganizationActivityEventResponseDto`` in the backend.
    """

    model_config = ConfigDict(populate_by_name=True)

    id: str
    event_type: str = Field(alias="eventType")
    actor_user_id: Optional[str] = Field(default=None, alias="actorUserId")
    subject: OrganizationActivityEventSubject
    metadata: Optional[Dict[str, Any]] = None
    occurred_at: str = Field(alias="occurredAt")


class OrganizationActivityPage(BaseModel):
    """Paginated page of activity events.

    The backend only echoes ``items`` and ``total``; ``page`` and ``limit``
    are not in the response.
    """

    items: List[OrganizationActivityEvent] = Field(default_factory=list)
    total: int = 0


class OrganizationActivityFilters(BaseModel):
    """Optional filters accepted by :meth:`OrganizationsAPI.get_organization_activity`.

    ``event_type`` accepts a single value or a list (sent to the backend
    as a comma-separated list). ``limit`` is the page size (backend cap
    is 200); the legacy ``offset`` name is not supported by this endpoint.
    """

    event_type: Optional[
        Union[
            OrganizationActivityEventType,
            str,
            List[Union[OrganizationActivityEventType, str]],
        ]
    ] = None
    actor_user_id: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    page: Optional[int] = None
    limit: Optional[int] = None

    model_config = ConfigDict(populate_by_name=True)


class OrganizationMember(BaseModel):
    """A single row from an organization's member list.

    Returned by :meth:`OrganizationsAPI.get_members`. Mirrors the
    ``OrganizationMember`` entity in the Nevermined backend.

    ``extra="allow"`` keeps any new backend-emitted fields accessible on
    the model without an SDK upgrade, matching the forward-compat
    treatment of :class:`OrganizationActivityEventSubject`.
    """

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    id: str
    user_id: str = Field(alias="userId")
    org_id: str = Field(alias="orgId")
    user_address: str = Field(alias="userAddress")
    role: OrganizationMemberRole
    is_active: bool = Field(alias="isActive")
    created_at: str = Field(alias="createdAt")
    updated_at: str = Field(alias="updatedAt")


class OrganizationMembersResponse(BaseModel):
    """Paginated members response used by :meth:`OrganizationsAPI.get_members`.

    The backend returns ``totalResults`` on the wire; the SDK normalizes
    it to ``total`` so both Python and TypeScript clients see the same
    shape.
    """

    members: List[OrganizationMember] = Field(default_factory=list)
    total: int = 0


class CreateUserResponse(BaseModel):
    """Result of :meth:`OrganizationsAPI.create_member`.

    The backend response carries the freshly minted wallet under
    ``walletResult``; the SDK flattens those fields and exposes the
    wallet hash as ``nvm_api_key`` for parity with the TS SDK.
    """

    model_config = ConfigDict(populate_by_name=True)

    nvm_api_key: str = Field(alias="nvmApiKey")
    user_id: str = Field(alias="userId")
    user_wallet: str = Field(alias="userWallet")
    already_member: bool = Field(default=False, alias="alreadyMember")


class StripeAccountConnectResult(BaseModel):
    """Result of :meth:`OrganizationsAPI.connect_stripe_account`.

    Named ``StripeAccountConnectResult`` rather than ``StripeCheckoutResult``
    to disambiguate the Stripe Connect onboarding flow from the
    plan-purchase checkout flow that ``payments.plans`` uses.

    Mirrors the TS ``StripeCheckoutResult`` in
    ``src/api/organizations-api/types.ts``.
    """

    model_config = ConfigDict(populate_by_name=True)

    stripe_account_id: str = Field(alias="stripeAccountId")
    stripe_account_link: str = Field(alias="stripeAccountLink")
    user_id: str = Field(alias="userId")
    user_country_code: str = Field(alias="userCountryCode")
    link_created_at: int = Field(alias="linkCreatedAt")
    link_expires_at: int = Field(alias="linkExpiresAt")
