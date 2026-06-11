"""
X402 Token Generation API.

Provides X402 access token generation functionality for subscribers.
Tokens are used to authorize payment verification and settlement.
"""

import base64
import json
import warnings
import requests
from typing import Dict, Any, Optional
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import API_URL_CREATE_PERMISSION
from payments_py.x402.schemes import get_default_network
from payments_py.x402.types import DelegationConfig, X402TokenOptions


def _is_inline_create(delegation_config: DelegationConfig) -> bool:
    """Whether a delegation config asks the backend to create a delegation
    on the fly (the deprecated path) rather than reusing an existing one.

    The supported flow is create-first: create the delegation via
    ``POST /delegation/create`` and pass only ``delegation_id`` here. A config
    that carries no ``delegation_id`` but does carry an inline-create signal
    (a payment-method reference or spending limits) triggers the backend's
    deprecated create-on-the-fly path, which logs its own deprecation warning
    server-side (#1674) and will be removed in a future release.
    """
    if delegation_config.delegation_id:
        return False
    return any(
        value is not None
        for value in (
            delegation_config.card_id,
            delegation_config.provider_payment_method_id,
            delegation_config.spending_limit_cents,
            delegation_config.duration_secs,
        )
    )


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
        token_options: Optional[X402TokenOptions] = None,
    ) -> Dict[str, Any]:
        """
        Get an X402 access token for the given plan against a delegation.

        This token allows the agent to verify and settle delegations on behalf
        of the subscriber.

        Supported flow (**create-first**): create the delegation once via
        ``payments.delegation.create_delegation(...)`` and pass only its
        ``delegation_id`` here via ``token_options.delegation_config``.

        Passing spending limits / a payment method here instead (inline
        create-on-the-fly, i.e. a ``delegation_config`` with no
        ``delegation_id``) is **deprecated** (#1674): this method emits a
        ``DeprecationWarning`` and the backend logs its own deprecation
        warning. The inline path will be removed in a future release.

        Args:
            plan_id: The unique identifier of the payment plan
            agent_id: The unique identifier of the AI agent (optional)
            token_options: Options controlling scheme and delegation behavior (optional)

        Returns:
            A dictionary containing:
                - accessToken: The X402 access token string

        Raises:
            PaymentsError: If the request fails

        Example:
            ```python
            # Create the delegation once (currency is required), then reuse it.
            delegation = payments.delegation.create_delegation(
                CreateDelegationPayload(
                    provider="erc4337",
                    spending_limit_cents=10000,
                    duration_secs=604800,
                    currency="usdc",
                )
            )

            result = payments.x402.get_x402_access_token(
                plan_id, agent_id,
                token_options=X402TokenOptions(
                    delegation_config=DelegationConfig(
                        delegation_id=delegation.delegation_id
                    )
                )
            )
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
            else get_default_network(scheme, self.environment_name)
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

        # Add delegation config for both erc4337 and card-delegation schemes
        if token_options and token_options.delegation_config:
            delegation_config = token_options.delegation_config
            if _is_inline_create(delegation_config):
                warnings.warn(
                    "Passing spending limits / a payment method to "
                    "get_x402_access_token (inline delegation create-on-the-fly) "
                    "is deprecated and will be removed in a future release. "
                    "Create the delegation first with "
                    "payments.delegation.create_delegation(...) and pass only "
                    "DelegationConfig(delegation_id=...) here.",
                    DeprecationWarning,
                    stacklevel=2,
                )
            body["delegationConfig"] = delegation_config.model_dump(
                by_alias=True, exclude_none=True
            )

        options = self.get_backend_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to create X402 delegation token"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while creating X402 delegation token: {str(err)}"
            ) from err


__all__ = ["X402TokenAPI", "decode_access_token"]
