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


# Convenience functions for easier usage

def generate_x402_access_token(
    token_api: X402TokenAPI,
    plan_id: str,
    agent_id: str
) -> str:
    """
    Generate an X402 access token and return just the token string.
    
    This is a convenience wrapper that returns just the token string
    instead of the full response dict.
    
    Args:
        token_api: An initialized X402TokenAPI instance
        plan_id: The payment plan identifier
        agent_id: The AI agent identifier
        
    Returns:
        The X402 access token string
        
    Raises:
        PaymentsError: If token generation fails
        
    Example:
        ```python
        from payments_py import Payments, PaymentOptions
        from payments_py.x402 import X402TokenAPI, generate_x402_access_token
        
        payments = Payments.get_instance(
            PaymentOptions(nvm_api_key="nvm:key", environment="sandbox")
        )
        
        token_api = X402TokenAPI.get_instance(payments.options)
        token = generate_x402_access_token(token_api, plan_id, agent_id)
        ```
    """
    result = token_api.get_x402_access_token(plan_id, agent_id)
    
    if "accessToken" not in result:
        raise PaymentsError(
            "X402 token generation failed: 'accessToken' not in response",
            {"response": result}
        )
    
    return result["accessToken"]


def get_x402_token_response(
    token_api: X402TokenAPI,
    plan_id: str,
    agent_id: str
) -> Dict[str, Any]:
    """
    Get the full X402 access token response for the given plan and agent.
    
    Returns the complete response dict including metadata.
    
    Args:
        token_api: An initialized X402TokenAPI instance
        plan_id: The payment plan identifier
        agent_id: The AI agent identifier
        
    Returns:
        Dictionary containing the access token and metadata
        
    Raises:
        PaymentsError: If token generation fails
        
    Example:
        ```python
        from payments_py import Payments, PaymentOptions
        from payments_py.x402 import X402TokenAPI, get_x402_token_response
        
        payments = Payments.get_instance(
            PaymentOptions(nvm_api_key="nvm:key", environment="sandbox")
        )
        
        token_api = X402TokenAPI.get_instance(payments.options)
        response = get_x402_token_response(token_api, plan_id, agent_id)
        
        token = response["accessToken"]
        # Additional metadata available in response
        ```
    """
    return token_api.get_x402_access_token(plan_id, agent_id)

