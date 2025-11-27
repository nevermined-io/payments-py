"""
Nevermined X402 Payment Protocol Module.

This module provides X402-specific types, utilities, and the NeverminedFacilitator
for implementing payment-required services with the X402 protocol extension.

Example Usage:
    ```python
    from payments_py import Payments, PaymentOptions
    from payments_py.x402 import (
        NeverminedFacilitator,
        generate_x402_access_token,
        PaymentPayload,
        PaymentRequirements,
    )
    
    # Initialize payments
    payments = Payments.get_instance(
        PaymentOptions(
            nvm_api_key="nvm:your-key",
            environment="sandbox"
        )
    )
    
    # Initialize facilitator
    facilitator = NeverminedFacilitator(
        nvm_api_key="nvm:your-key",
        environment="sandbox"
    )
    
    # Generate X402 token for subscriber
    token = generate_x402_access_token(payments, plan_id, agent_id)
    
    # Verify and settle payments
    verify_result = await facilitator.verify(payment_payload, requirements)
    if verify_result.is_valid:
        settle_result = await facilitator.settle(payment_payload, requirements)
    ```
"""

from .types import (
    PaymentRequirements,
    NvmPaymentRequiredResponse,
    PaymentPayload,
    SessionKeyPayload,
    VerifyResponse,
    SettleResponse,
)
from .networks import SupportedNetworks
from .schemes import SupportedSchemes
from .facilitator import NeverminedFacilitator
from .facilitator_api import FacilitatorAPI
from .token import X402TokenAPI, generate_x402_access_token, get_x402_token_response

__all__ = [
    # Types
    "PaymentRequirements",
    "NvmPaymentRequiredResponse",
    "PaymentPayload",
    "SessionKeyPayload",
    "VerifyResponse",
    "SettleResponse",
    # Constants
    "SupportedNetworks",
    "SupportedSchemes",
    # APIs
    "FacilitatorAPI",
    "X402TokenAPI",
    # High-level facilitator
    "NeverminedFacilitator",
    # Token utilities
    "generate_x402_access_token",
    "get_x402_token_response",
]

