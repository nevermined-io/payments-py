"""
X402 Token Generation API.

Provides X402 access token generation functionality for subscribers.
Tokens are used to authorize payment verification and settlement.
"""

import requests
from typing import Dict, Any
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import API_URL_GET_AGENT_X402_ACCESS_TOKEN


class X402TokenAPI(BasePaymentsAPI):
    """
    X402 Token API for generating access tokens.
    
    Handles X402 access token generation for subscribers to authorize
    payment operations with AI agents.
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "X402TokenAPI":
        """
        Get a singleton instance of the X402TokenAPI class.

        Args:
            options: The options to initialize the API

        Returns:
            The instance of the X402TokenAPI class
        """
        return cls(options)

    def get_x402_access_token(self, plan_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Get an X402 access token for the given plan and agent.
        
        This token allows the agent to verify and settle permissions on behalf
        of the subscriber. The token contains cryptographically signed session keys
        that delegate specific permissions (order, burn) to the agent.

        Args:
            plan_id: The unique identifier of the payment plan
            agent_id: The unique identifier of the AI agent

        Returns:
            A dictionary containing:
                - accessToken: The X402 access token string
                - Additional metadata about the token

        Raises:
            PaymentsError: If the request fails

        Example:
            ```python
            from payments_py import Payments, PaymentOptions
            from payments_py.x402 import X402TokenAPI
            
            payments = Payments.get_instance(
                PaymentOptions(nvm_api_key="nvm:subscriber-key", environment="sandbox")
            )
            
            token_api = X402TokenAPI.get_instance(payments.options)
            result = token_api.get_x402_access_token(plan_id, agent_id)
            token = result["accessToken"]
            ```
        """
        url_path = API_URL_GET_AGENT_X402_ACCESS_TOKEN.format(
            plan_id=plan_id, agent_id=agent_id
        )
        url = f"{self.environment.backend}{url_path}"

        options = self.get_backend_http_options("GET")

        try:
            response = requests.get(url, **options)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as err:
            try:
                error_message = response.json().get(
                    "message", "Failed to get X402 access token"
                )
            except Exception:
                error_message = "Failed to get X402 access token"
            raise PaymentsError.internal(
                f"{error_message} (HTTP {response.status_code})"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while getting X402 access token: {str(err)}"
            ) from err


__all__ = ["X402TokenAPI"]

