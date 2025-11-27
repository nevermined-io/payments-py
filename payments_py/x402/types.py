"""
X402 Payment Protocol Types.

Defines Pydantic models for X402 payment requirements, payloads,
and responses used in payment verification and settlement.
"""

from typing import Optional, Any
from pydantic import BaseModel, ConfigDict, Field, field_validator
from .networks import SupportedNetworks
from .schemes import SupportedSchemes


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
            raise ValueError(
                "max_amount must be an integer encoded as a string"
            )
        return v


class NvmPaymentRequiredResponse(BaseModel):
    """
    Response indicating payment is required, including accepted payment methods.
    
    Attributes:
        nvm_version: X402 protocol version
        accepts: List of accepted payment requirements
        error: Error message if payment setup failed
    """
    nvm_version: int
    accepts: list[PaymentRequirements]
    error: str

    model_config = ConfigDict(
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
        nvm_version: X402 protocol version
        scheme: Payment scheme identifier
        network: Blockchain network identifier
        payload: The session key payload containing the access token
    """
    nvm_version: int
    scheme: str
    network: str
    payload: SessionKeyPayload

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class VerifyResponse(BaseModel):
    """
    Response from payment verification.
    
    Attributes:
        is_valid: Whether the payment credentials are valid
        invalid_reason: Reason for invalidity (if is_valid=False)
        session_key: The validated session key (if is_valid=True)
    """
    is_valid: bool = Field(alias="isValid")
    invalid_reason: Optional[str] = Field(None, alias="invalidReason")
    session_key: Optional[str] = Field(None, alias="sessionKey")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class SettleResponse(BaseModel):
    """
    Response from payment settlement.
    
    Attributes:
        success: Whether the settlement succeeded
        error_reason: Reason for failure (if success=False)
        transaction: Blockchain transaction hash (if success=True)
        network: Network where transaction was executed
    """
    success: bool
    error_reason: Optional[str] = None
    transaction: Optional[str] = None
    network: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )

