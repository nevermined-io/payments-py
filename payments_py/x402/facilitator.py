"""
NeverminedFacilitator - X402 Payment Verification and Settlement.

Implements X402 payment verification and settlement using the Nevermined
network via the payments-py FacilitatorAPI.
"""

import logging

from .types import (
    SessionKeyPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from .helpers import build_payment_required
from payments_py.common.types import PaymentOptions

logger = logging.getLogger(__name__)


class NeverminedFacilitator:
    """
    A Nevermined-based facilitator that verifies and settles payments using
    the Nevermined network through the payments-py SDK.

    This facilitator uses X402 access tokens to verify subscriber permissions
    and settle (burn) credits on-chain.

    Example:
        ```python
        from payments_py.x402 import NeverminedFacilitator, PaymentPayload, PaymentRequirements

        # Initialize facilitator
        facilitator = NeverminedFacilitator(
            nvm_api_key="nvm:your-api-key",
            environment="sandbox"
        )

        # Verify payment
        verify_result = await facilitator.verify(payment_payload, requirements)

        if verify_result.is_valid:
            # Settle payment
            settle_result = await facilitator.settle(payment_payload, requirements)
        ```
    """

    def __init__(
        self,
        nvm_api_key: str,
        environment: str = "sandbox",
    ):
        """
        Initialize the NeverminedFacilitator.

        Args:
            nvm_api_key: The Nevermined API key for authentication (format: "nvm:...")
            environment: The environment to use ('sandbox' or 'live')
        """
        # Lazy import to avoid circular dependency
        from payments_py.payments import Payments

        self.payments = Payments.get_instance(
            PaymentOptions(nvm_api_key=nvm_api_key, environment=environment)
        )
        self.environment = environment
        logger.info(f"Initialized NeverminedFacilitator for environment: {environment}")

    async def verify(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> VerifyResponse:
        """
        Verifies the payment using Nevermined's X402 access token.

        This checks if the subscriber has sufficient permissions/credits
        without actually burning them.

        Args:
            payload: The payment payload containing the X402 access token
            requirements: The payment requirements (plan_id, agent_id, max_amount)

        Returns:
            VerifyResponse indicating if the payment is valid

        Example:
            ```python
            result = await facilitator.verify(payment_payload, requirements)
            if result.is_valid:
                print("Payment verified successfully")
            else:
                print(f"Verification failed: {result.invalid_reason}")
            ```
        """
        logger.info("=== NEVERMINED FACILITATOR: VERIFY ===")

        try:
            # Extract X402 access token from payload
            # Handle both SessionKeyPayload model and dict formats
            if isinstance(payload.payload, SessionKeyPayload):
                x402_access_token = payload.payload.session_key
            elif isinstance(payload.payload, dict) and "session_key" in payload.payload:
                x402_access_token = payload.payload["session_key"]
            else:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason="Unsupported payload type - expected session_key in payload",
                )

            # Build X402PaymentRequired from requirements for the new API
            # Get endpoint from requirements.extra if available (set by server)
            endpoint = (
                requirements.extra.get("endpoint", "/") if requirements.extra else "/"
            )

            payment_required = build_payment_required(
                plan_id=requirements.plan_id,
                agent_id=requirements.agent_id,
                network=payload.network,  # Use CAIP-2 format from payload
                endpoint=endpoint,
            )

            logger.info(
                f"Verifying permissions for plan: {requirements.plan_id}, "
                f"max_amount: {requirements.max_amount}, "
                f"network: {payload.network}"
            )

            # Call new FacilitatorAPI with X402PaymentRequired
            verification = self.payments.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=x402_access_token,
                max_amount=requirements.max_amount,
            )

            if verification.is_valid:
                logger.info("✅ Payment verification successful")
                return verification
            else:
                logger.warning(
                    f"⛔ Payment verification failed: {verification.invalid_reason}"
                )
                return verification

        except Exception as e:
            logger.error(f"Error during payment verification: {e}", exc_info=True)
            return VerifyResponse(
                is_valid=False, invalid_reason=f"Verification error: {str(e)}"
            )

    async def settle(
        self, payload: PaymentPayload, requirements: PaymentRequirements
    ) -> SettleResponse:
        """
        Settles the payment by burning credits on the Nevermined network.

        This executes the actual credit consumption. If the subscriber doesn't
        have enough credits, it will attempt to order more before settling.

        Args:
            payload: The payment payload containing the X402 access token
            requirements: The payment requirements (plan_id, agent_id, max_amount)

        Returns:
            SettleResponse indicating if the settlement was successful

        Example:
            ```python
            result = await facilitator.settle(payment_payload, requirements)
            if result.success:
                print(f"Settlement successful! TX: {result.transaction}")
            else:
                print(f"Settlement failed: {result.error_reason}")
            ```
        """
        logger.info("=== NEVERMINED FACILITATOR: SETTLE ===")

        try:
            # Extract X402 access token from payload
            # Handle both SessionKeyPayload model and dict formats
            if isinstance(payload.payload, SessionKeyPayload):
                x402_access_token = payload.payload.session_key
            elif isinstance(payload.payload, dict) and "session_key" in payload.payload:
                x402_access_token = payload.payload["session_key"]
            else:
                return SettleResponse(
                    success=False,
                    error_reason="Unsupported payload type - expected session_key in payload",
                )

            # Build X402PaymentRequired from requirements for the new API
            # Get endpoint from requirements.extra if available (set by server)
            endpoint = (
                requirements.extra.get("endpoint", "/") if requirements.extra else "/"
            )

            payment_required = build_payment_required(
                plan_id=requirements.plan_id,
                agent_id=requirements.agent_id,
                network=payload.network,  # Use CAIP-2 format from payload
                endpoint=endpoint,
            )

            logger.info(
                f"Settling permissions for plan: {requirements.plan_id}, "
                f"max_amount: {requirements.max_amount}, "
                f"network: {payload.network}"
            )

            # Call new FacilitatorAPI with X402PaymentRequired
            settlement = self.payments.facilitator.settle_permissions(
                payment_required=payment_required,
                x402_access_token=x402_access_token,
                max_amount=requirements.max_amount,
            )

            if settlement.success:
                logger.info(
                    f"✅ Payment settled successfully! Credits redeemed: {settlement.credits_redeemed}"
                )
                logger.info(f"Transaction hash: {settlement.transaction}")
                return settlement
            else:
                logger.warning(
                    f"⛔ Payment settlement failed: {settlement.error_reason}"
                )
                return settlement

        except Exception as e:
            logger.error(f"Error during payment settlement: {e}", exc_info=True)
            return SettleResponse(
                success=False, error_reason=f"Settlement error: {str(e)}"
            )
