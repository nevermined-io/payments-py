"""
The FacilitatorAPI class provides methods to verify and settle AI agent permissions using X402 access tokens.
This allows AI agents to act as facilitators, verifying and settling credits on behalf of subscribers.

Example usage:
    from payments_py import Payments, PaymentOptions

    # Initialize the Payments instance
    payments = Payments.get_instance(
        PaymentOptions(
            nvm_api_key="your-nvm-api-key",
            environment="sandbox"
        )
    )

    # Get X402 access token from X402 API
    token_result = payments.x402.get_x402_access_token(
        plan_id="123",
        agent_id="456"  # optional
    )
    x402_token = token_result["accessToken"]

    # Verify if subscriber has sufficient permissions/credits
    verification = payments.facilitator.verify_permissions(
        plan_id="123",
        x402_access_token=x402_token,
        subscriber_address="0x1234...",
        max_amount="2"  # optional
    )

    if verification["success"]:
        # Settle (burn) the credits
        settlement = payments.facilitator.settle_permissions(
            plan_id="123",
            x402_access_token=x402_token,
            subscriber_address="0x1234...",
            max_amount="2"  # optional
        )
        print(f"Credits burned: {settlement['data']['creditsBurned']}")
"""

import requests
from typing import Dict, Any, Optional
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
        x402_access_token: str,
        subscriber_address: str,
        max_amount: Optional[str] = None,
        endpoint: Optional[str] = None,
        http_verb: Optional[str] = None,
        agent_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Verify if a subscriber has permission to use credits from a payment plan.
        This method simulates the credit usage without actually burning credits,
        checking if the subscriber has sufficient balance and permissions.

        Args:
            plan_id: The unique identifier of the payment plan
            x402_access_token: The X402 access token for permission verification
            subscriber_address: The Ethereum address of the subscriber
            max_amount: The maximum number of credits to verify (as string, optional)
            endpoint: The endpoint to verify permissions for (optional - enables endpoint validation)
            http_verb: The HTTP verb to verify permissions for (optional - enables endpoint validation)
            agent_id: The unique identifier of the agent (required when endpoint and http_verb are provided)

        Returns:
            A dictionary containing verification result with 'success' boolean

        Raises:
            PaymentsError: If verification fails
        """
        url = f"{self.environment.backend}{API_URL_VERIFY_PERMISSIONS}"

        body: Dict[str, Any] = {
            "plan_id": plan_id,
            "x402_access_token": x402_access_token,
            "subscriber_address": subscriber_address,
        }

        if max_amount is not None:
            body["max_amount"] = max_amount
        if endpoint is not None:
            body["endpoint"] = endpoint
        if http_verb is not None:
            body["http_verb"] = http_verb
        if agent_id is not None:
            body["agent_id"] = agent_id

        options = self.get_public_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return response.json()
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
        x402_access_token: str,
        subscriber_address: str,
        max_amount: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Settle (burn) credits from a subscriber's payment plan.
        This method executes the actual credit consumption, burning the specified
        number of credits from the subscriber's balance. If the subscriber doesn't
        have enough credits, it will attempt to order more before settling.

        Args:
            plan_id: The unique identifier of the payment plan
            x402_access_token: The X402 access token for permission settlement
            subscriber_address: The Ethereum address of the subscriber
            max_amount: The number of credits to burn (as string, optional)

        Returns:
            A dictionary containing settlement result with transaction details

        Raises:
            PaymentsError: If settlement fails
        """
        url = f"{self.environment.backend}{API_URL_SETTLE_PERMISSIONS}"

        body: Dict[str, Any] = {
            "plan_id": plan_id,
            "x402_access_token": x402_access_token,
            "subscriber_address": subscriber_address,
        }

        if max_amount is not None:
            body["max_amount"] = max_amount

        options = self.get_public_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return response.json()
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
