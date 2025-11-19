"""
The FacilitatorAPI class provides methods to verify and settle AI agent permissions using X402 access tokens.
This allows AI agents to act as facilitators, verifying and settling credits on behalf of subscribers.

Example usage:
    from payments_py import Payments, PaymentOptions

    # Initialize the Payments instance
    payments = Payments.get_instance(
        PaymentOptions(
            nvm_api_key="your-nvm-api-key",
            environment="testing"
        )
    )

    # Get X402 access token from agents API
    token_result = payments.agents.get_x402_access_token(
        plan_id="123",
        agent_id="456"
    )
    x402_token = token_result["accessToken"]

    # Verify if subscriber has sufficient permissions/credits
    verification = payments.facilitator.verify_permissions(
        plan_id="123",
        max_amount="2",
        x402_access_token=x402_token,
        subscriber_address="0x1234..."
    )

    if verification["success"]:
        # Settle (burn) the credits
        settlement = payments.facilitator.settle_permissions(
            plan_id="123",
            max_amount="2",
            x402_access_token=x402_token,
            subscriber_address="0x1234..."
        )
        print(f"Credits burned: {settlement['data']['creditsBurned']}")
"""

import requests
from typing import Dict, Any
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import (
    API_URL_VERIFY_PERMISSIONS,
    API_URL_SETTLE_PERMISSIONS,
)


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
        plan_id: str,
        max_amount: str,
        x402_access_token: str,
        subscriber_address: str,
    ) -> Dict[str, Any]:
        """
        Verify if a subscriber has permission to use credits from a payment plan.
        This method simulates the credit usage without actually burning credits,
        checking if the subscriber has sufficient balance and permissions.

        Args:
            plan_id: The unique identifier of the payment plan
            max_amount: The maximum number of credits to verify (as string)
            x402_access_token: The X402 access token for permission verification
            subscriber_address: The Ethereum address of the subscriber

        Returns:
            A dictionary containing verification result with 'success' boolean

        Raises:
            PaymentsError: If verification fails
        """
        url = f"{self.environment.backend}{API_URL_VERIFY_PERMISSIONS}"

        body = {
            "plan_id": plan_id,
            "max_amount": max_amount,
            "x402_access_token": x402_access_token,
            "subscriber_address": subscriber_address,
        }

        options = self.get_backend_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as err:
            try:
                error_message = response.json().get("message", "Permission verification failed")
            except Exception:
                error_message = "Permission verification failed"
            raise PaymentsError.backend_error(
                error_message,
                f"HTTP {response.status_code}",
                {
                    "plan_id": plan_id,
                    "subscriber_address": subscriber_address,
                    "max_amount": max_amount,
                },
            ) from err
        except Exception as err:
            raise PaymentsError.backend_error(
                "Network error during permission verification",
                str(err),
                {
                    "plan_id": plan_id,
                    "subscriber_address": subscriber_address,
                },
            ) from err

    def settle_permissions(
        self,
        plan_id: str,
        max_amount: str,
        x402_access_token: str,
        subscriber_address: str,
    ) -> Dict[str, Any]:
        """
        Settle (burn) credits from a subscriber's payment plan.
        This method executes the actual credit consumption, burning the specified
        number of credits from the subscriber's balance. If the subscriber doesn't
        have enough credits, it will attempt to order more before settling.

        Args:
            plan_id: The unique identifier of the payment plan
            max_amount: The number of credits to burn (as string)
            x402_access_token: The X402 access token for permission settlement
            subscriber_address: The Ethereum address of the subscriber

        Returns:
            A dictionary containing settlement result with transaction details

        Raises:
            PaymentsError: If settlement fails
        """
        url = f"{self.environment.backend}{API_URL_SETTLE_PERMISSIONS}"

        body = {
            "plan_id": plan_id,
            "max_amount": max_amount,
            "x402_access_token": x402_access_token,
            "subscriber_address": subscriber_address,
        }

        options = self.get_backend_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as err:
            try:
                error_message = response.json().get("message", "Permission settlement failed")
            except Exception:
                error_message = "Permission settlement failed"
            raise PaymentsError.backend_error(
                error_message,
                f"HTTP {response.status_code}",
                {
                    "plan_id": plan_id,
                    "subscriber_address": subscriber_address,
                    "max_amount": max_amount,
                },
            ) from err
        except Exception as err:
            raise PaymentsError.backend_error(
                "Network error during permission settlement",
                str(err),
                {
                    "plan_id": plan_id,
                    "subscriber_address": subscriber_address,
                },
            ) from err

