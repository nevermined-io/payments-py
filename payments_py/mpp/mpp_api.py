"""
The Machine Payments Protocol (MPP) API.

MPP is a second payment framing over the unchanged Nevermined core: the same
plan, the same delegation and the same credit burn as x402, negotiated with MPP
headers. Sellers issue a challenge and redeem a credential; buyers mint an
MPP-domain access token and present it as a credential.
"""

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

import requests

from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import (
    API_URL_MPP_CHALLENGE,
    API_URL_MPP_CREATE_PERMISSION,
    API_URL_MPP_SETTLE,
    API_URL_MPP_VERIFY,
)
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.x402.token_request import build_x402_token_request_body
from payments_py.x402.types import X402TokenOptions

from .errors import MppError, MppSettlementOutcomeUnknownError, to_mpp_error
from .fetch import MppFetchOptions, MppFetchResult, mpp_fetch

# Only whole, non-negative decimal digits — no sign, no leading/trailing
# whitespace, no underscore separators, no fractional part. ``int(x)`` silently
# accepts several of those for a string input (``int(" 5 ")`` is 5, ``int("1_0")``
# is 10), which a decimal-string contract must reject rather than accept quietly.
_DECIMAL_INTEGER_STRING = re.compile(r"^\d+$")


def normalize_credits(credits: Union[str, int, float]) -> str:
    """Normalize ``credits`` to the exact decimal-string amount that gets sealed
    into the challenge and burned.

    A bare ``str()`` on a Python float can emit scientific notation (``1e+21``),
    ``"nan"`` or ``"inf"`` — all forwarded unvalidated into an amount that has
    no post-hoc re-pricing as there is with x402: a corrupted amount here is not
    correctable downstream, it IS the amount. So a float is accepted only when
    it is exactly integer-valued, and rendered through ``int`` (never through
    ``str``); ``bool`` is refused outright even though it subclasses ``int``.

    Raises:
        MppError: if ``credits`` is not a non-negative integer amount.
    """
    if isinstance(credits, bool):
        raise MppError(f"credits must be a non-negative integer, got {credits!r}")

    if isinstance(credits, str):
        if not _DECIMAL_INTEGER_STRING.match(credits):
            raise MppError(
                "credits must be a non-negative integer decimal string, got "
                f"{credits!r}"
            )
        return credits

    if isinstance(credits, float):
        if not credits.is_integer():
            raise MppError(
                f"credits must be a non-negative integer, got {credits!r}: "
                "the value is not a whole number"
            )
        credits = int(credits)

    if not isinstance(credits, int):
        raise MppError(f"credits must be a non-negative integer, got {credits!r}")
    if credits < 0:
        raise MppError(f"credits must be a non-negative integer, got {credits}")
    return str(credits)


@dataclass
class IssueMppChallengeParams:
    """Inputs to :meth:`MppAPI.issue_challenge`."""

    #: The Nevermined plan the credits are burned against.
    plan_id: str
    #: Credits the buyer is asked to redeem. Sent as a decimal string.
    credits: Union[str, int, float]
    #: The protected resource. Sealed into the challenge and re-asserted at redeem.
    resource: str
    #: HTTP verb of that resource. Part of the same binding.
    http_verb: str
    agent_id: Optional[str] = None
    #: ``sha-256=<base64>`` digest binding the challenge to one request body.
    digest: Optional[str] = None
    description: Optional[str] = None


@dataclass
class RedeemMppParams:
    """Inputs to :meth:`MppAPI.verify_credential` / :meth:`MppAPI.settle_credential`."""

    #: The ``Authorization: Payment …`` value presented by the buyer.
    credential: str
    #: Must equal the resource the challenge was issued for.
    resource: str
    #: Must equal the verb the challenge was issued for.
    http_verb: str
    #: Digest of the body actually received, when the challenge bound one.
    body_digest: Optional[str] = None


#: Socket-level failures that can only happen once the request was already on
#: the wire, so on a burning call the backend may have completed the burn and
#: only the answer was lost.
#:
#: Deliberately an ALLOW-LIST, not a blanket promotion of every network error. A
#: refused connection or a DNS failure means the request never reached anything
#: that could burn, so reporting them as "may have burned" would inflate a
#: seller's records with burns that never happened — the same corruption as the
#: 4xx case, in the other direction.
_OUTCOME_UNKNOWN_SOCKET_ERRORS = (ConnectionResetError, BrokenPipeError)


def _is_post_request_socket_failure(error: BaseException) -> bool:
    """Whether a ``requests`` failure is a connection that died AFTER the
    request was written — i.e. an unknown settlement outcome rather than a
    definite failure.

    ``requests`` wraps the underlying OS error several layers deep (its own
    ``ConnectionError`` over urllib3's ``ProtocolError`` over the builtin), so
    the chain is walked rather than the top-level type inspected.
    """
    seen = set()
    current: Optional[BaseException] = error
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _OUTCOME_UNKNOWN_SOCKET_ERRORS):
            return True
        # urllib3 raises ProtocolError("Connection aborted.", ConnectionResetError(...)),
        # and the builtin is carried in ``args`` rather than on ``__cause__``.
        for arg in getattr(current, "args", ()):
            if isinstance(arg, _OUTCOME_UNKNOWN_SOCKET_ERRORS):
                return True
            if isinstance(arg, BaseException) and _is_post_request_socket_failure(arg):
                return True
        current = current.__cause__ or current.__context__
    return False


class MppAPI(BasePaymentsAPI):
    """Challenge issuance, credential redemption and the buyer-side helper."""

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "MppAPI":
        """Get an instance of the MppAPI class."""
        return cls(options)

    def issue_challenge(self, params: IssueMppChallengeParams) -> Dict[str, Any]:
        """Mint the challenge a plan-protected endpoint returns with its 402.

        Each call returns a distinct challenge even for identical inputs — the
        id doubles as the burn idempotency key, so two requests sharing one
        would settle as a single burn.

        Returns:
            ``{"challenge": <WWW-Authenticate value>, "id": <challenge id>}``
        """
        body: Dict[str, Any] = {
            "planId": params.plan_id,
            "credits": normalize_credits(params.credits),
            "resource": params.resource,
            "httpVerb": params.http_verb,
        }
        if params.agent_id:
            body["agentId"] = params.agent_id
        if params.digest:
            body["digest"] = params.digest
        if params.description:
            body["description"] = params.description
        return self._post(API_URL_MPP_CHALLENGE, body)

    def verify_credential(self, params: RedeemMppParams) -> Dict[str, Any]:
        """Run the full credential and plan checks without burning anything."""
        return self._post(API_URL_MPP_VERIFY, self._redeem_body(params))

    def settle_credential(self, params: RedeemMppParams) -> Dict[str, Any]:
        """Verify and burn through the same chokepoint an x402 settlement uses,
        so the credits charged are identical on both protocols. Settling the
        same credential twice burns once.

        Raises:
            MppSettlementOutcomeUnknownError: when the call ended without a
                definite answer — the burn may or may not have committed.
        """
        return self._post(API_URL_MPP_SETTLE, self._redeem_body(params), burns=True)

    def get_mpp_access_token(
        self,
        plan_id: str,
        agent_id: Optional[str] = None,
        token_options: Optional[X402TokenOptions] = None,
    ) -> Dict[str, Any]:
        """Mint an access token signed under the ``Nevermined-MPP`` EIP-712 domain.

        Same inputs and same settlement rail as
        :meth:`X402TokenAPI.get_x402_access_token`; the token verifies only on
        the MPP routes, which is what keeps the two protocols isolated even
        though the tokens are byte-identical on the wire.
        """
        body = build_x402_token_request_body(
            plan_id=plan_id,
            agent_id=agent_id,
            token_options=token_options,
            environment_name=self.environment_name,
        )
        return self._post(API_URL_MPP_CREATE_PERMISSION, body)

    def fetch(
        self,
        method: str,
        url: str,
        options: MppFetchOptions,
        **request_kwargs: Any,
    ) -> MppFetchResult:
        """Perform an HTTP request, paying an MPP challenge if the endpoint
        returns one.

        The buyer needs no new plan, delegation or credential: the delegation
        that works for x402 works here unchanged. ``request_kwargs`` are handed
        to :func:`requests.request` unchanged (``headers``, ``json``, ``data``,
        ``params``, ``timeout``, ``stream``, …).

        A request body must be replayable **if the endpoint may challenge the
        request**: a generator, iterator or file-like ``data=`` raises a typed
        :class:`PaymentsError` once a 402 challenge actually requires a retry,
        since it cannot be resent. A request that is never challenged sends such
        a body exactly once, exactly like a plain ``requests`` call — the
        ``paid=False`` / untouched-response guarantee still holds.

        ``options.delegation_config`` must carry a ``delegation_id`` — this call
        refuses the deprecated inline create-on-the-fly shape (no
        ``delegation_id``) that
        :meth:`X402TokenAPI.get_x402_access_token` otherwise tolerates with a
        warning: the retry loop here can mint an access token twice per call, so
        that shape could silently create two delegations as a side effect of
        paying.

        Example:
            ```python
            result = payments.mpp.fetch(
                "POST",
                "https://agent.example/ask",
                MppFetchOptions(
                    delegation_config=DelegationConfig(delegation_id=delegation_id),
                    plan_id=plan_id,
                ),
                json={"q": "hello"},
            )
            print(result.paid, result.receipt)
            ```
        """
        delegation_config = getattr(options, "delegation_config", None)
        if not delegation_config or not getattr(
            delegation_config, "delegation_id", None
        ):
            raise PaymentsError.validation(
                "payments.mpp.fetch requires delegation_config.delegation_id. "
                "Create a delegation first with "
                "payments.delegation.create_delegation(), then pass "
                "DelegationConfig(delegation_id=...). An inline "
                "create-on-the-fly delegation_config (no delegation_id) is not "
                "accepted here — the retry loop can mint against it twice per "
                "call, which would create two delegations."
            )
        return mpp_fetch(
            self.get_mpp_access_token, method, url, options, **request_kwargs
        )

    def _redeem_body(self, params: RedeemMppParams) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "credential": params.credential,
            "resource": params.resource,
            "httpVerb": params.http_verb,
        }
        if params.body_digest:
            body["bodyDigest"] = params.body_digest
        return body

    def _post(
        self, path: str, body: Dict[str, Any], burns: bool = False
    ) -> Dict[str, Any]:
        """One place for the POST + error translation every MPP call shares.

        ``burns`` marks a call where "no answer" is not the same as "did not
        happen" — currently only :meth:`settle_credential`. For that call alone,
        a read timeout (the request was written, the answer never arrived), a
        connection torn down after the request was written, a 5xx/408, and a 2xx
        whose body could not be read are all raised as
        :class:`MppSettlementOutcomeUnknownError` instead of the generic
        ``network_error`` :class:`MppError` used everywhere else, so a caller can
        tell "definitely nothing happened" apart from "the backend may have
        already burned the credits; we just didn't hear back".

        A connect timeout is deliberately NOT in that set: nothing was written,
        so nothing can have burned.
        """
        url = f"{self.environment.backend}{path}"
        options = self.get_backend_http_options("POST", body)

        try:
            response = requests.post(url, **options)
        except requests.exceptions.ReadTimeout as error:
            if burns:
                raise MppSettlementOutcomeUnknownError() from error
            raise to_mpp_error(
                "network_error", f"Network error during MPP request: {error}"
            ) from error
        except requests.exceptions.RequestException as error:
            if burns and _is_post_request_socket_failure(error):
                raise MppSettlementOutcomeUnknownError(
                    "The connection to the backend failed after the settle "
                    f"request was written: {error}"
                ) from error
            raise to_mpp_error(
                "network_error", f"Network error during MPP request: {error}"
            ) from error

        if not response.ok:
            message = f"MPP request to {path} failed"
            code: Optional[str] = f"http_{response.status_code}"
            try:
                error_data = response.json()
                if isinstance(error_data, dict):
                    if error_data.get("message"):
                        message = error_data["message"]
                    if error_data.get("code"):
                        code = error_data["code"]
                    if error_data.get("hint"):
                        message = f"{message} — {error_data['hint']}"
            except ValueError:
                pass  # Keep the default message.

            # On a burning call, a 5xx (or a 408) is an UNKNOWN outcome, not a
            # failure. A 504 in particular means an intermediary gave up waiting
            # on the backend — it says nothing about whether the burn committed.
            # Classified as a definite failure, the middleware logs "settlement
            # failed" and skips on_after_settle for credits that may well be gone.
            #
            # Confined to 5xx/408: the backend's own rejections (BCK.MPP.0003 and
            # friends) come back as 4xx and ARE definite — reporting those as
            # unknown would corrupt the accounting in the other direction.
            if burns and (response.status_code >= 500 or response.status_code == 408):
                raise MppSettlementOutcomeUnknownError(
                    f"The backend answered {response.status_code} without a "
                    f"definite settlement outcome: {message}"
                )
            raise to_mpp_error(code, message)

        # The success path is not exempt from a malformed body: a WAF
        # interstitial, a gateway HTML page, or a truncated 2xx response would
        # otherwise raise a raw JSON decoding error — the one call site in this
        # method that was NOT already converted to a typed error.
        try:
            return response.json()
        except (ValueError, json.JSONDecodeError) as error:
            # On a burning call this is an UNKNOWN outcome, not a failure. The
            # backend already answered 2xx — the burn committed — and only the
            # body was lost. Reporting it as a definite failure is exactly the
            # accounting corruption MppSettlementOutcomeUnknownError exists to
            # prevent. If anything this case is MORE likely to have burned than
            # the pre-response timeout the error was introduced for.
            if burns:
                raise MppSettlementOutcomeUnknownError(
                    f"The backend answered {response.status_code} but its body "
                    f"could not be read: {error}"
                ) from error
            raise to_mpp_error(
                f"http_{response.status_code}",
                f"MPP response from {path} was not valid JSON: {error}",
            ) from error


__all__ = [
    "IssueMppChallengeParams",
    "MppFetchOptions",
    "MppFetchResult",
    "MppAPI",
    "RedeemMppParams",
    "normalize_credits",
]
