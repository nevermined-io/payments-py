"""
X402 Token Generation API.

Provides X402 access token generation functionality for subscribers.
Tokens are used to authorize payment verification and settlement.
"""

import base64
import json
import requests
from typing import Dict, Any, Optional
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import API_URL_CREATE_PERMISSION
from payments_py.x402.schemes import X402_SCHEME_NETWORKS
from payments_py.x402.types import X402TokenOptions


def decode_access_token(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Decode an x402 access token to extract subscriber address and plan ID.

    The x402 access token is a base64-encoded JSON document containing
    session key information and permissions.

    Args:
        access_token: The x402 access token to decode (base64-encoded JSON)

    Returns:
        The decoded token data or None if invalid
    """
    padded = access_token + "=" * (4 - len(access_token) % 4)

    # Try URL-safe base64 first, then standard base64
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            decoded_bytes = decoder(padded)
            return json.loads(decoded_bytes)
        except Exception:
            continue

    return None


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

    def get_x402_access_token(
        self,
        plan_id: str,
        agent_id: Optional[str] = None,
        redemption_limit: Optional[int] = None,
        order_limit: Optional[str] = None,
        expiration: Optional[str] = None,
        token_options: Optional[X402TokenOptions] = None,
    ) -> Dict[str, Any]:
        """
        Create a permission and get an X402 access token for the given plan.

        This token allows the agent to verify and settle permissions on behalf
        of the subscriber. The token contains cryptographically signed session keys
        that delegate specific permissions (order, burn) to the agent.

        Args:
            plan_id: The unique identifier of the payment plan
            agent_id: The unique identifier of the AI agent (optional)
            redemption_limit: Maximum number of interactions/redemptions allowed (optional)
            order_limit: Maximum spend limit in token units (wei) for ordering (optional)
            expiration: Expiration date in ISO 8601 format, e.g. "2025-02-01T10:00:00Z" (optional)
            token_options: Options controlling scheme and delegation behavior (optional)

        Returns:
            A dictionary containing:
                - accessToken: The X402 access token string

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
            result = token_api.get_x402_access_token(plan_id="123", agent_id="456")
            token = result["accessToken"]
            ```
        """
        url = f"{self.environment.backend}{API_URL_CREATE_PERMISSION}"

        # Extract scheme/network from token_options or defaults
        scheme = (
            token_options.scheme
            if token_options and token_options.scheme
            else "nvm:erc4337"
        )
        network = (
            token_options.network
            if token_options and token_options.network
            else X402_SCHEME_NETWORKS.get(scheme, "eip155:84532")
        )

        # Build x402-aligned request body
        extra: Dict[str, Any] = {}
        if agent_id is not None:
            extra["agentId"] = agent_id

        body: Dict[str, Any] = {
            "accepted": {
                "scheme": scheme,
                "network": network,
                "planId": plan_id,
                "extra": extra,
            },
        }

        # Add delegation config for card-delegation scheme
        if (
            scheme == "nvm:card-delegation"
            and token_options
            and token_options.delegation_config
        ):
            body["delegationConfig"] = token_options.delegation_config.model_dump(
                by_alias=True, exclude_none=True
            )

        # Add session key config if any options are provided (erc4337 only)
        if scheme == "nvm:erc4337":
            session_key_config: Dict[str, Any] = {}
            if redemption_limit is not None:
                session_key_config["redemptionLimit"] = redemption_limit
            if order_limit is not None:
                session_key_config["orderLimit"] = order_limit
            if expiration is not None:
                session_key_config["expiration"] = expiration
            if session_key_config:
                body["sessionKeyConfig"] = session_key_config

        options = self.get_backend_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as err:
            try:
                error_message = response.json().get(
                    "message", "Failed to create X402 permission"
                )
            except Exception:
                error_message = "Failed to create X402 permission"
            raise PaymentsError.internal(
                f"{error_message} (HTTP {response.status_code})"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while creating X402 permission: {str(err)}"
            ) from err


__all__ = ["X402TokenAPI", "decode_access_token"]
