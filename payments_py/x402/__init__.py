"""
Nevermined X402 Payment Protocol Module.

This module provides X402-specific types, utilities, and the NeverminedFacilitator
for implementing payment-required services with the X402 protocol extension.

Example Usage:
    ```python
    from payments_py import Payments, PaymentOptions
    from payments_py.x402 import (
        NeverminedFacilitator,
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
    token_response = payments.x402.get_x402_access_token(
        plan_id=plan_id,
        agent_id=agent_id  # optional
    )
    token = token_response["accessToken"]

    # Verify and settle payments
    verify_result = await facilitator.verify(payment_payload, requirements)
    if verify_result.is_valid:
        settle_result = await facilitator.settle(payment_payload, requirements)
    ```
"""

from .types import (
    # x402 types
    X402Resource,
    X402SchemeExtra,
    X402Scheme,
    X402PaymentRequired,
    # Legacy types
    PaymentRequirements,
    NvmPaymentRequiredResponse,
    PaymentPayload,
    SessionKeyPayload,
    VerifyResponse,
    SettleResponse,
)
from .helpers import build_payment_required
from .networks import SupportedNetworks
from .schemes import SupportedSchemes
from .facilitator import NeverminedFacilitator
from .facilitator_api import FacilitatorAPI
from .a2a import X402A2AUtils, X402Metadata, PaymentStatus as X402PaymentStatus
from .token import X402TokenAPI, decode_access_token

# V2 extended types
from .types_v2 import (
    Extension,
    ResourceInfo,
    PaymentRequiredResponseV2,
    PaymentPayloadV2,
    Extensions,
)

__all__ = [
    # x402 types
    "X402Resource",
    "X402SchemeExtra",
    "X402Scheme",
    "X402PaymentRequired",
    # Types (V1 - legacy)
    "PaymentRequirements",
    "NvmPaymentRequiredResponse",
    "PaymentPayload",
    "SessionKeyPayload",
    "VerifyResponse",
    "SettleResponse",
    # Helper functions
    "build_payment_required",
    # Types (V2)
    "Extension",
    "ResourceInfo",
    "PaymentRequiredResponseV2",
    "PaymentPayloadV2",
    "Extensions",
    # Constants
    "SupportedNetworks",
    "SupportedSchemes",
    # APIs
    "FacilitatorAPI",
    "X402TokenAPI",
    "decode_access_token",
    # High-level facilitator
    "NeverminedFacilitator",
    # A2A Integration
    "X402A2AUtils",
    "X402Metadata",
    "X402PaymentStatus",
]

# Note: For Nevermined extension helpers, import from:
#   from payments_py.x402.extensions.nevermined import (
#       NEVERMINED,
#       declare_nevermined_extension,
#       extract_nevermined_info,
#       validate_nevermined_extension
#   )
