"""
The FacilitatorAPI class provides methods to verify and settle AI agent permissions using X402 access tokens.
This allows AI agents to act as facilitators, verifying and settling credits on behalf of subscribers.

Example usage:
    from payments_py import Payments, PaymentOptions
    from payments_py.x402 import X402PaymentRequired, X402Scheme

    # Initialize the Payments instance
    payments = Payments.get_instance(
        PaymentOptions(
            nvm_api_key="your-nvm-api-key",
            environment="sandbox"
        )
    )

    # The server's 402 PaymentRequired response
    payment_required = X402PaymentRequired(
        x402_version=2,
        accepts=[
            X402Scheme(
                scheme="nvm:erc4337",
                network="eip155:84532",
                plan_id="123",
            )
        ],
        extensions={}
    )

    # Get X402 access token from subscriber request
    x402_token = request.headers.get("X-Payment")

    # Verify if subscriber has sufficient permissions/credits
    verification = payments.facilitator.verify_permissions(
        payment_required=payment_required,
        x402_access_token=x402_token,
        max_amount="2"  # optional
    )

    if verification.is_valid:
        # Settle (burn) the credits
        settlement = payments.facilitator.settle_permissions(
            payment_required=payment_required,
            x402_access_token=x402_token,
            max_amount="2"  # optional
        )
        print(f"Credits redeemed: {settlement.credits_redeemed}")
"""

import requests
from typing import Optional
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import (
    API_URL_VERIFY_PERMISSIONS,
    API_URL_SETTLE_PERMISSIONS,
)
from payments_py.x402.types import VerifyResponse, SettleResponse, X402PaymentRequired


class FacilitatorAPI(BasePaymentsAPI):
    """
    The FacilitatorAPI class provides methods to verify and settle AI agent permissions.
    It enables AI agents to act as facilitators, managing credit verification and settlement
    for subscribers using X402 access tokens.
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "FacilitatorAPI":
        """
        Get a singleton instance of the FacilitatorAPI class.

        Args:
            options: The options to initialize the payments class

        Returns:
            The instance of the FacilitatorAPI class
        """
        return cls(options)

    def verify_permissions(
        self,
        payment_required: X402PaymentRequired,
        x402_access_token: str,
        max_amount: Optional[str] = None,
    ) -> VerifyResponse:
        """
        Verify if a subscriber has permission to use credits from a payment plan.
        This method simulates the credit usage without actually burning credits,
        checking if the subscriber has sufficient balance and permissions.

        The planId and subscriberAddress are extracted from the x402AccessToken.

        Args:
            payment_required: x402 PaymentRequired from 402 response (required, for validation)
            x402_access_token: The X402 access token (contains planId, subscriberAddress, agentId)
            max_amount: The maximum number of credits to verify (as string, optional)

        Returns:
            VerifyResponse with is_valid boolean and optional error details

        Raises:
            PaymentsError: If verification fails
        """
        url = f"{self.environment.backend}{API_URL_VERIFY_PERMISSIONS}"

        body: dict = {
            "paymentRequired": payment_required.model_dump(by_alias=True),
            "x402AccessToken": x402_access_token,
        }

        if max_amount is not None:
            body["maxAmount"] = max_amount

        options = self.get_public_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return VerifyResponse.model_validate(response.json())
        except requests.HTTPError as err:
            try:
                error_message = response.json().get(
                    "message", "Permission verification failed"
                )
            except Exception:
                error_message = "Permission verification failed"
            raise PaymentsError.backend_error(
                error_message,
                f"HTTP {response.status_code}",
                {},
            ) from err
        except Exception as err:
            if isinstance(err, PaymentsError):
                raise
            raise PaymentsError.backend_error(
                "Network error during permission verification",
                str(err),
                {},
            ) from err

    def settle_permissions(
        self,
        payment_required: X402PaymentRequired,
        x402_access_token: str,
        max_amount: Optional[str] = None,
    ) -> SettleResponse:
        """
        Settle (burn) credits from a subscriber's payment plan.
        This method executes the actual credit consumption, burning the specified
        number of credits from the subscriber's balance. If the subscriber doesn't
        have enough credits, it will attempt to order more before settling.

        The planId and subscriberAddress are extracted from the x402AccessToken.

        Args:
            payment_required: x402 PaymentRequired from 402 response (required, for validation)
            x402_access_token: The X402 access token (contains planId, subscriberAddress, agentId)
            max_amount: The number of credits to burn (as string, optional)

        Returns:
            SettleResponse with success boolean and transaction details

        Raises:
            PaymentsError: If settlement fails
        """
        url = f"{self.environment.backend}{API_URL_SETTLE_PERMISSIONS}"

        body: dict = {
            "paymentRequired": payment_required.model_dump(by_alias=True),
            "x402AccessToken": x402_access_token,
        }

        if max_amount is not None:
            body["maxAmount"] = max_amount

        options = self.get_public_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return SettleResponse.model_validate(response.json())
        except requests.HTTPError as err:
            try:
                error_message = response.json().get(
                    "message", "Permission settlement failed"
                )
            except Exception:
                error_message = "Permission settlement failed"
            raise PaymentsError.backend_error(
                error_message,
                f"HTTP {response.status_code}",
                {},
            ) from err
        except Exception as err:
            if isinstance(err, PaymentsError):
                raise
            raise PaymentsError.backend_error(
                "Network error during permission settlement",
                str(err),
                {},
            ) from err
