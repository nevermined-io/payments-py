"""
X402 Payment Protocol Types.

Defines Pydantic models for X402 payment requirements, payloads,
and responses used in payment verification and settlement.
"""

from dataclasses import dataclass
from typing import Optional, Any, List
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel
from .networks import SupportedNetworks
from .schemes import SupportedSchemes, X402SchemeType


class X402Resource(BaseModel):
    """
    x402 Resource information.

    Attributes:
        url: The protected resource URL
        description: Human-readable description
        mime_type: Expected response MIME type (e.g., "application/json")
    """

    url: str
    description: Optional[str] = None
    mime_type: Optional[str] = Field(None, alias="mimeType")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class X402SchemeExtra(BaseModel):
    """
    x402 Scheme extra fields for nvm:erc4337.

    Attributes:
        version: Scheme version (e.g., "1")
        agent_id: Agent identifier
        http_verb: HTTP method for the endpoint
    """

    version: Optional[str] = None
    agent_id: Optional[str] = Field(None, alias="agentId")
    http_verb: Optional[str] = Field(None, alias="httpVerb")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class X402Scheme(BaseModel):
    """
    x402 Scheme definition (nvm:erc4337).

    Attributes:
        scheme: Payment scheme identifier (e.g., "nvm:erc4337")
        network: Blockchain network in CAIP-2 format (e.g., "eip155:84532")
        plan_id: 256-bit plan identifier
        extra: Scheme-specific extra fields
    """

    scheme: str
    network: str
    plan_id: str = Field(alias="planId")
    extra: Optional[X402SchemeExtra] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class X402PaymentRequired(BaseModel):
    """
    x402 PaymentRequired response (402 response from server).

    Attributes:
        x402_version: x402 protocol version (always 2)
        error: Human-readable error message
        resource: Protected resource information
        accepts: Array of accepted payment schemes
        extensions: Extensions object (empty {} for nvm:erc4337)
    """

    x402_version: int = Field(alias="x402Version")
    error: Optional[str] = None
    resource: X402Resource
    accepts: list[X402Scheme]
    extensions: dict[str, Any]

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class PaymentRequirements(BaseModel):
    """
    Specifies the payment requirements for an X402-protected service.

    Attributes:
        plan_id: The Nevermined plan identifier
        agent_id: The AI agent identifier
        max_amount: The maximum credits to charge (as string-encoded integer)
        network: The blockchain network (e.g., "base-sepolia")
        scheme: The payment scheme (e.g., "contract")
        extra: Optional additional metadata
    """

    plan_id: str
    agent_id: str
    max_amount: str
    network: str
    scheme: str
    extra: Optional[dict[str, Any]] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

    @field_validator("max_amount")
    def validate_max_amount(cls, v):
        """Validate that max_amount is a valid integer encoded as string."""
        try:
            int(v)
        except ValueError:
            raise ValueError("max_amount must be an integer encoded as a string")
        return v


class NvmPaymentRequiredResponse(BaseModel):
    """
    Response indicating payment is required, including accepted payment methods.

    Attributes:
        x402_version: X402 protocol version
        accepts: List of accepted payment requirements
        error: Error message if payment setup failed
    """

    x402_version: int = Field(alias="x402Version")
    accepts: list[PaymentRequirements]
    error: str

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class SessionKeyPayload(BaseModel):
    """
    Contains the X402 access token session key.

    Attributes:
        session_key: The cryptographically signed X402 access token
    """

    session_key: str


class PaymentPayload(BaseModel):
    """
    Complete payment payload sent from client to merchant.

    Attributes:
        x402_version: X402 protocol version
        scheme: Payment scheme identifier
        network: Blockchain network identifier
        payload: The session key payload containing the access token
    """

    x402_version: int = Field(alias="x402Version")
    scheme: str
    network: str
    payload: SessionKeyPayload

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class VerifyResponse(BaseModel):
    """
    x402 Verify Response - per x402 facilitator spec.

    @see https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md

    Attributes:
        is_valid: Whether the payment authorization is valid
        invalid_reason: Reason for invalidity (only present if is_valid is false)
        payer: Address of the payer's wallet
        agent_request_id: Agent request ID for observability tracking (Nevermined extension)
        url_matching: URL pattern that matched the endpoint (Nevermined extension)
        agent_request: Full agent request context for observability (Nevermined extension)
    """

    is_valid: bool = Field(alias="isValid")
    invalid_reason: Optional[str] = Field(None, alias="invalidReason")
    payer: Optional[str] = None
    agent_request_id: Optional[str] = Field(None, alias="agentRequestId")
    url_matching: Optional[str] = Field(None, alias="urlMatching")
    agent_request: Optional[Any] = Field(None, alias="agentRequest")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class SettleResponse(BaseModel):
    """
    x402 Settle Response - per x402 facilitator spec.

    @see https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md

    Attributes:
        success: Whether settlement was successful
        error_reason: Reason for settlement failure (only present if success is false)
        payer: Address of the payer's wallet
        transaction: Blockchain transaction hash (empty string if settlement failed)
        network: Blockchain network identifier in CAIP-2 format
        credits_redeemed: Number of credits redeemed (Nevermined extension)
        remaining_balance: Subscriber's remaining balance (Nevermined extension)
        order_tx: Transaction hash of the order operation if auto top-up occurred (Nevermined extension)
    """

    success: bool
    error_reason: Optional[str] = Field(None, alias="errorReason")
    payer: Optional[str] = None
    transaction: str = ""
    network: str = ""
    credits_redeemed: Optional[str] = Field(None, alias="creditsRedeemed")
    remaining_balance: Optional[str] = Field(None, alias="remainingBalance")
    order_tx: Optional[str] = Field(None, alias="orderTx")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


@dataclass
class PaymentContext:
    """
    Payment context available after x402 verification.

    Populated by middleware/decorators and made available to handlers:
    - FastAPI: ``request.state.payment_context``
    - Strands: ``tool_context.invocation_state["payment_context"]``
    """

    token: str
    payment_required: X402PaymentRequired
    credits_to_settle: int
    verified: bool
    agent_request_id: Optional[str] = None
    agent_request: Optional[Any] = None


class CardDelegationConfig(BaseModel):
    """
    Configuration for card delegation (fiat/Stripe) payments.

    Exactly one of the following three modes must be used:

    1. **Reuse an existing delegation** — supply ``delegation_id`` only.
    2. **Reuse an enrolled card** — supply ``card_id``.  Optionally also
       provide ``spending_limit_cents``, ``duration_secs``,
       ``merchant_account_id``, ``max_transactions``, and/or ``currency``
       to override the card's defaults for this delegation.
    3. **Create a brand-new delegation** — supply
       ``provider_payment_method_id``, ``spending_limit_cents``, and
       ``duration_secs`` (all three are required for this mode).

    Attributes:
        card_id: PaymentMethod entity UUID -- preferred way to reference an enrolled card
        delegation_id: Existing delegation UUID to reuse instead of creating a new one
        provider_payment_method_id: Stripe payment method ID (e.g., 'pm_...'). Required for new delegations.
        spending_limit_cents: Maximum spending limit in cents. Required for new delegations; optional override when using card_id.
        duration_secs: Duration of the delegation in seconds. Required for new delegations; optional override when using card_id.
        currency: Currency code (default: 'usd')
        merchant_account_id: Stripe Connect merchant account ID
        max_transactions: Maximum number of transactions allowed
    """

    card_id: Optional[str] = Field(None, alias="cardId")
    delegation_id: Optional[str] = Field(None, alias="delegationId")
    provider_payment_method_id: Optional[str] = Field(
        None, alias="providerPaymentMethodId"
    )
    spending_limit_cents: Optional[int] = Field(None, alias="spendingLimitCents")
    duration_secs: Optional[int] = Field(None, alias="durationSecs")
    currency: Optional[str] = None
    merchant_account_id: Optional[str] = Field(None, alias="merchantAccountId")
    max_transactions: Optional[int] = Field(None, alias="maxTransactions")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

    @model_validator(mode="after")
    def _check_valid_combination(self) -> "CardDelegationConfig":
        has_delegation_id = self.delegation_id is not None
        has_card_id = self.card_id is not None
        new_delegation_fields = {
            "provider_payment_method_id": self.provider_payment_method_id,
            "spending_limit_cents": self.spending_limit_cents,
            "duration_secs": self.duration_secs,
        }
        has_new_delegation = any(v is not None for v in new_delegation_fields.values())

        if not has_delegation_id and not has_card_id and not has_new_delegation:
            raise ValueError(
                "CardDelegationConfig requires at least one of: 'delegation_id', "
                "'card_id', or the new-delegation fields "
                "('provider_payment_method_id', 'spending_limit_cents', 'duration_secs')."
            )

        if has_new_delegation and not has_card_id and not has_delegation_id:
            missing = [
                name for name, val in new_delegation_fields.items() if val is None
            ]
            if missing:
                raise ValueError(
                    "When creating a brand-new delegation (without 'card_id' or "
                    f"'delegation_id') all three fields are required: "
                    f"'provider_payment_method_id', 'spending_limit_cents', "
                    f"'duration_secs'. Missing: {missing}."
                )

        return self


class X402TokenOptions(BaseModel):
    """
    Options for x402 token generation that control scheme and delegation behavior.

    Attributes:
        scheme: The x402 scheme to use (defaults to 'nvm:erc4337')
        network: Network identifier (auto-derived from scheme if omitted)
        delegation_config: Card delegation configuration (only for 'nvm:card-delegation')
    """

    scheme: Optional[str] = None
    network: Optional[str] = None
    delegation_config: Optional[CardDelegationConfig] = Field(
        None, alias="delegationConfig"
    )

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )
