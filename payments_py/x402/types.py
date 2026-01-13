"""
X402 Payment Protocol Types.

Defines Pydantic models for X402 payment requirements, payloads,
and responses used in payment verification and settlement.
"""

from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel
from .networks import SupportedNetworks
from .schemes import SupportedSchemes


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
    network: SupportedNetworks
    scheme: SupportedSchemes
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
    """

    is_valid: bool = Field(alias="isValid")
    invalid_reason: Optional[str] = Field(None, alias="invalidReason")
    payer: Optional[str] = None
    agent_request_id: Optional[str] = Field(None, alias="agentRequestId")

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
