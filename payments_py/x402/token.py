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
from payments_py.x402.token_version import (
    X402_TOKEN_VERSION_V2,
    X402_TOKEN_VERSION_V3,
)
from payments_py.x402.types import X402TokenOptions, X402TokenVersion


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
    # Shape-checked before the padding concatenation: a non-str input (bytes, an
    # int, a dict) would raise TypeError there instead of returning None, which
    # is what every caller — and this function's own contract — expects.
    if not isinstance(access_token, str):
        return None

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


def is_single_use_access_token(access_token: Optional[str]) -> bool:
    """Whether the token is consumed by its first successful settlement.

    True exactly for v3 (single-use, seller/resource-bound) tokens. A caller
    that caches an access token must test this before reusing one: settling a
    spent v3 token fails with ``BCK.X402.0059``
    (see :func:`payments_py.x402.errors.is_access_token_already_used`).

    Read from the token that came BACK, never from the ``token_version`` that
    was asked for: the backend's ``ValidationPipe`` runs with ``whitelist: True``
    and without ``forbidNonWhitelisted``, so ``tokenVersion: 3`` sent to a
    backend that predates nvm-monorepo#2646 is dropped **without an error** and
    the caller gets a v2 token back. Inferring the version from the request
    would therefore treat a reusable v2 token as single-use (harmless) or, worse,
    let a caller believe replay protection is on when it is not.

    The discriminant is the one field only v3 carries:
    ``payload.authorization.nonce``, a non-empty, non-whitespace **string**.
    The wire type is checked, not assumed: the backend mints it as
    ``0x`` + 32 CSPRNG bytes hex-encoded (``generateTokenNonce`` in core-kit's
    ``AgentX402AccessToken.ts``), i.e. always a string. A numeric or otherwise
    reshaped nonce therefore reads as v2 — see
    :func:`detect_access_token_version` for why that asymmetry is the one worth
    guarding.
    """
    if not access_token:
        return False
    decoded = decode_access_token(access_token)
    if not isinstance(decoded, dict):
        return False
    payload = decoded.get("payload")
    if not isinstance(payload, dict):
        return False
    authorization = payload.get("authorization")
    if not isinstance(authorization, dict):
        return False
    nonce = authorization.get("nonce")
    return isinstance(nonce, str) and nonce.strip() != ""


def detect_access_token_version(access_token: Optional[str]) -> X402TokenVersion:
    """The EIP-712 version the given access token was actually signed under.

    Nothing here is verified — it answers "which settle semantics does this
    token have", which only the backend's signature check ultimately enforces.

    Returns :data:`X402_TOKEN_VERSION_V3` for a token carrying a non-empty
    string ``authorization.nonce``, :data:`X402_TOKEN_VERSION_V2` otherwise,
    including for a token that cannot be decoded.

    Note which way that fallback is unsafe. Callers branch on this to decide
    whether to cache (:meth:`PaymentsClient._get_access_token`), and the four
    cases are not symmetric: v2-read-as-v3 only re-mints more often than needed,
    while **v3-read-as-v2 caches a spent token** and fails every later settle
    with ``BCK.X402.0059``. So v2 is the fallback for *undecodable input* — where
    no version claim exists at all and today's reusable semantics are what every
    pre-v3 token already gets — not because it is the conservative reading of an
    ambiguous nonce. It is not: for a token that decodes, the nonce check is
    what has to be right, which is why its wire type is verified rather than
    assumed (see :func:`is_single_use_access_token`).
    """
    return (
        X402_TOKEN_VERSION_V3
        if is_single_use_access_token(access_token)
        else X402_TOKEN_VERSION_V2
    )


def with_detected_token_version(response: Dict[str, Any]) -> Dict[str, Any]:
    """Add the detected ``tokenVersion`` to a mint response, in place.

    Used by the x402 mint only: the MPP mint reports no version at all, since
    MPP has no version ladder (nvm-monorepo#3266). Kept as a named helper
    rather than inlined so the "report what came back, never what was asked
    for" rule has one place to be read and tested.

    A response without an ``accessToken`` string is left untouched — there is
    no token to read a version from, and inventing one would be a lie.
    """
    if not isinstance(response, dict):
        return response
    access_token = response.get("accessToken")
    if isinstance(access_token, str) and access_token:
        response["tokenVersion"] = detect_access_token_version(access_token)
    return response


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

        A **v3** token (single-use, bound to one seller and one endpoint) is
        requested with ``token_options.token_version=3`` plus the
        ``resource`` / ``http_verb`` it should be bound to. Requesting v3 does
        not guarantee v3: a backend predating nvm-monorepo#2646 strips the
        field silently and returns v2. Read the ``tokenVersion`` key of the
        result — it is detected from the token that came back, never from what
        was asked for.

        Args:
            plan_id: The unique identifier of the payment plan
            agent_id: The unique identifier of the AI agent (optional)
            token_options: Options controlling scheme, delegation, the
                resource/verb the token is bound to, and the requested token
                version (optional)

        Returns:
            A dictionary containing:
                - accessToken: The X402 access token string
                - tokenVersion: ``2`` or ``3``, detected from the returned
                  token's ``authorization.nonce``

        Raises:
            PaymentsError: If the request fails, or (``code='validation'``) if
                ``delegation_config.delegation_id`` is an empty string — pass a
                valid delegation UUID or omit the field — or if
                ``token_options.resource`` carries a blank URL.

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

            # Single-use, bound to one seller endpoint (v3):
            result = payments.x402.get_x402_access_token(
                plan_id, agent_id,
                token_options=X402TokenOptions(
                    delegation_config=DelegationConfig(
                        delegation_id=delegation.delegation_id
                    ),
                    resource="https://seller.example/api/v1/tasks",
                    http_verb="POST",
                    token_version=3,
                ),
            )
            if result["tokenVersion"] == 3:
                ...  # single-use: mint a fresh token for the next paid request
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
            # Report the version of the token we GOT, not the one we asked for:
            # `tokenVersion` is silently stripped by a backend that predates
            # nvm-monorepo#2646, so echoing the request would claim replay
            # protection that is not there.
            return with_detected_token_version(response.json())
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to create X402 delegation token"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while creating X402 delegation token: {str(err)}"
            ) from err


__all__ = [
    "X402TokenAPI",
    "X402_TOKEN_VERSION_V2",
    "X402_TOKEN_VERSION_V3",
    "decode_access_token",
    "encode_access_token",
    "detect_access_token_version",
    "is_single_use_access_token",
    "with_detected_token_version",
]
