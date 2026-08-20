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
from payments_py.x402.token_request import build_x402_token_request_body
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


def encode_access_token(payload: Dict[str, Any]) -> str:
    """
    Encode a PaymentPayload dict into an x402 access token string.

    Inverse of :func:`decode_access_token`. Used by the MCP transport to turn
    the in-band ``_meta["x402/payment"]`` PaymentPayload object back into the
    base64url token string the facilitator's verify/settle APIs consume.

    The base64 envelope is transport-only: the EIP-712 signature lives inside
    ``payload.authorization`` / ``payload.signature``, not over the base64
    wrapper, so re-encoding a decoded payload is byte-safe for the facilitator
    (round-trip verified by ``tests/unit/mcp_tests/test_x402_inband.py``).

    Args:
        payload: The decoded PaymentPayload dict (e.g. from ``_meta["x402/payment"]``).

    Returns:
        The base64url-encoded access token string (unpadded), matching the
        encoding ``decode_access_token`` accepts.
    """
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


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
        ``FutureWarning`` and the backend logs its own deprecation warning.
        The inline path will be removed in a future release.

        Args:
            plan_id: The unique identifier of the payment plan
            agent_id: The unique identifier of the AI agent (optional)
            token_options: Options controlling scheme and delegation behavior (optional)

        Returns:
            A dictionary containing:
                - accessToken: The X402 access token string

        Raises:
            PaymentsError: If the request fails, or (``code='validation'``) if
                ``delegation_config.delegation_id`` is an empty string — pass a
                valid delegation UUID or omit the field.

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

        # Body shape is shared with the MPP mint (`payments.mpp`): same
        # inputs, same delegation rules, different EIP-712 domain at the
        # backend. Kept in one place so the two cannot drift.
        body = build_x402_token_request_body(
            plan_id=plan_id,
            agent_id=agent_id,
            token_options=token_options,
            environment_name=self.environment_name,
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


__all__ = ["X402TokenAPI", "decode_access_token", "encode_access_token"]
