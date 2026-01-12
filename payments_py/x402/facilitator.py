"""
NeverminedFacilitator - X402 Payment Verification and Settlement.

Implements X402 payment verification and settlement using the Nevermined
network via the payments-py FacilitatorAPI.
"""

import logging
from typing import Optional

from .types import (
    SessionKeyPayload,
    PaymentPayload,
    PaymentRequirements,
    SettleResponse,
    VerifyResponse,
)
from .extensions.nevermined import extract_nevermined_info
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

            # Extract Nevermined info using v2 extension helper (supports v1 fallback)

            # Convert payload and requirements to dict for extraction helper
            payload_dict = (
                payload.model_dump(by_alias=True)
                if hasattr(payload, "model_dump")
                else payload
            )
            requirements_dict = (
                requirements.model_dump(by_alias=True)
                if hasattr(requirements, "model_dump")
                else requirements
            )

            nvm_info = extract_nevermined_info(
                payment_payload=payload_dict,
                payment_requirements=requirements_dict,
                validate=True,  # Validate v2 extensions if present
            )

            if not nvm_info:
                # Fallback: Extract from v1 requirements directly
                nvm_info = {
                    "plan_id": requirements.plan_id,
                    "agent_id": requirements.agent_id,
                    "max_amount": requirements.max_amount,
                    "subscriber_address": (
                        requirements.extra.get("subscriber_address")
                        if requirements.extra
                        else None
                    ),
                }

            # Extract required fields
            plan_id = nvm_info.get("plan_id")
            max_amount = nvm_info.get("max_amount")
            subscriber_address = nvm_info.get("subscriber_address")

            # If subscriber_address not in extension info, check requirements.extra
            if not subscriber_address and requirements.extra:
                subscriber_address = requirements.extra.get("subscriber_address")

            if not subscriber_address:
                return VerifyResponse(
                    is_valid=False,
                    invalid_reason="Missing subscriber_address in payment requirements",
                )

            logger.info(
                f"Verifying permissions for plan: {plan_id}, "
                f"max_amount: {max_amount}, "
                f"subscriber: {subscriber_address}"
            )

            # Call Nevermined API to verify permissions
            verification = self.payments.facilitator.verify_permissions(
                plan_id=plan_id,
                max_amount=max_amount,
                x402_access_token=x402_access_token,
                subscriber_address=subscriber_address,
            )

            if verification.get("success"):
                logger.info("✅ Payment verification successful")
                return VerifyResponse(is_valid=True, session_key=x402_access_token)
            else:
                error_msg = verification.get("message", "Verification failed")
                logger.warning(f"⛔ Payment verification failed: {error_msg}")
                return VerifyResponse(is_valid=False, invalid_reason=error_msg)

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

            # Extract Nevermined info using v2 extension helper (supports v1 fallback)

            # Convert payload and requirements to dict for extraction helper
            payload_dict = (
                payload.model_dump(by_alias=True)
                if hasattr(payload, "model_dump")
                else payload
            )
            requirements_dict = (
                requirements.model_dump(by_alias=True)
                if hasattr(requirements, "model_dump")
                else requirements
            )

            nvm_info = extract_nevermined_info(
                payment_payload=payload_dict,
                payment_requirements=requirements_dict,
                validate=True,  # Validate v2 extensions if present
            )

            if not nvm_info:
                # Fallback: Extract from v1 requirements directly
                nvm_info = {
                    "plan_id": requirements.plan_id,
                    "agent_id": requirements.agent_id,
                    "max_amount": requirements.max_amount,
                    "subscriber_address": (
                        requirements.extra.get("subscriber_address")
                        if requirements.extra
                        else None
                    ),
                }

            # Extract required fields
            plan_id = nvm_info.get("plan_id")
            max_amount = nvm_info.get("max_amount")
            subscriber_address = nvm_info.get("subscriber_address")

            # If subscriber_address not in extension info, check requirements.extra
            if not subscriber_address and requirements.extra:
                subscriber_address = requirements.extra.get("subscriber_address")

            if not subscriber_address:
                return SettleResponse(
                    success=False,
                    error_reason="Missing subscriber_address in payment requirements",
                )

            logger.info(
                f"Settling permissions for plan: {plan_id}, "
                f"max_amount: {max_amount}, "
                f"subscriber: {subscriber_address}"
            )

            # Call Nevermined API to settle permissions (burn credits)
            settlement = self.payments.facilitator.settle_permissions(
                plan_id=plan_id,
                max_amount=max_amount,
                x402_access_token=x402_access_token,
                subscriber_address=subscriber_address,
            )

            if settlement.get("success"):
                tx_hash = settlement.get("txHash")
                credits_burned = settlement.get("data", {}).get(
                    "creditsBurned", requirements.max_amount
                )

                logger.info(
                    f"✅ Payment settled successfully! Credits burned: {credits_burned}"
                )
                logger.info(f"Transaction hash: {tx_hash}")

                return SettleResponse(
                    success=True, transaction=tx_hash, network=requirements.network
                )
            else:
                error_msg = settlement.get("message", "Settlement failed")
                logger.warning(f"⛔ Payment settlement failed: {error_msg}")
                return SettleResponse(success=False, error_reason=error_msg)

        except Exception as e:
            logger.error(f"Error during payment settlement: {e}", exc_info=True)
            return SettleResponse(
                success=False, error_reason=f"Settlement error: {str(e)}"
            )
