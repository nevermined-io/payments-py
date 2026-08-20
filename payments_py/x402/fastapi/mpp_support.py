"""
Seller-edge helpers for MPP.

The edge is a thin, secret-free shim: it never mints a challenge itself and
never holds the MPP signing secret. It renames headers and forwards opaque
strings to the backend.

It does read exactly one field out of a credential — ``challenge.id``, via
:func:`mpp_credential_id`. That is a deliberate, bounded exception to "forwards
opaque strings", and it is forced: enforcing single-use requires a stable
identity for a credential, and the header bytes are not one (see
:func:`extract_credential_challenge_id`). The id is public, unsigned and already
the backend's own burn key, so reading it grants the edge nothing it could not
already observe; nothing here validates, trusts or acts on any other field, and
the credential itself is still forwarded verbatim.
"""

import base64
import hashlib
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Union

from starlette.requests import Request

from payments_py.mpp.codec import (
    extract_credential_challenge_expires,
    extract_credential_challenge_id,
    extract_payment_scheme,
)

#: MPP HTTP header names, lowercased for header lookups.
MPP_HEADERS = {
    # Server sends the challenge here on the 402.
    "CHALLENGE": "www-authenticate",
    # Client sends the credential here.
    "CREDENTIAL": "authorization",
    # Server sends the settlement receipt here on success.
    "RECEIPT": "payment-receipt",
}


@dataclass
class ResolvedMppOption:
    """A route's MPP opt-in, normalized."""

    enabled: bool
    bind_body: bool


@dataclass
class MppRouteOptions:
    """The dict form of the per-route ``mpp`` option.

    Constructed as ``MppRouteOptions(**option)`` so an unknown key raises
    ``TypeError``, exactly as ``RouteConfig(**value)`` already does for the
    outer route dict — the nested ``mpp`` dict was the one place that accepted
    anything and kept going.

    That silence mattered because of WHAT it turned off: ``{"bindBody": True}``
    resolved to ``bind_body=False`` with no error, no warning and no log, and an
    unbound challenge is not a missing nicety — the backend skips the digest
    comparison when the challenge carries none, so the BUYER decides whether
    body binding applies. Mint against an empty request, attach any body to the
    paid retry.
    """

    bind_body: bool = False


def resolve_mpp_option(
    option: Optional[Union[bool, Dict[str, Any]]],
) -> ResolvedMppOption:
    """Normalize the per-route ``mpp`` option. ``True`` is shorthand for
    ``{"bind_body": False}``.

    Raises:
        TypeError: if the dict form carries a key other than ``bind_body``, or
            a ``bind_body`` that is not a bool. Both are typos that would
            otherwise ship an unbound challenge on a route whose author asked
            for a bound one.
    """
    if option is None or option is False:
        return ResolvedMppOption(enabled=False, bind_body=False)
    if option is True:
        return ResolvedMppOption(enabled=True, bind_body=False)

    try:
        options = MppRouteOptions(**option)
    except TypeError as error:
        raise TypeError(
            f"Unsupported key in the route's `mpp` option: {error}. "
            "Supported keys: bind_body."
        ) from error
    # The dataclass gives no runtime type enforcement, and `{"bind_body": "true"}`
    # is the same class of typo as a misspelled key: truthy to a reader, and off
    # under the identity check this used to do.
    if not isinstance(options.bind_body, bool):
        raise TypeError(
            "The route's `mpp.bind_body` must be a bool, got "
            f"{type(options.bind_body).__name__}."
        )
    return ResolvedMppOption(enabled=True, bind_body=options.bind_body)


def mpp_resource(request: Request) -> str:
    """The resource the challenge is bound to.

    Identical to the endpoint value the x402 path already uses, so the scope
    includes the query string — the buyer reproduces it by retrying the same
    request.
    """
    query = request.url.query
    return f"{request.url.path}?{query}" if query else request.url.path


def mpp_verb(request: Request) -> str:
    return request.method.upper()


def extract_credential(request: Request) -> Optional[str]:
    """Pull the ``Payment`` credential out of ``Authorization``, tolerating a
    header that carries other schemes alongside it (RFC 9110 11.6.1)."""
    header = request.headers.get(MPP_HEADERS["CREDENTIAL"])
    if not header or not isinstance(header, str):
        return None
    return extract_payment_scheme(header)


def mpp_credential_expires(credential: str) -> Optional[str]:
    """The ``expires`` the credential's sealed challenge states, if any."""
    return extract_credential_challenge_expires(credential)


def mpp_credential_id(credential: str) -> Optional[str]:
    """The key the middleware's single-use and in-flight sets are keyed on: the
    credential's challenge id, never the header bytes.

    ``None`` means the credential carries no usable id, which the middleware
    treats as a rejection.
    """
    return extract_credential_challenge_id(credential)


def compute_body_digest(raw: bytes) -> str:
    """The RFC 9530 ``sha-256=<base64>`` digest MPP challenges use."""
    return f"sha-256={base64.b64encode(hashlib.sha256(raw).digest()).decode('ascii')}"


#: Digest of zero bytes — what a ``bind_body`` route binds when the request
#: carries no body, so "no body" is a bound state rather than an unbound
#: challenge the buyer can attach anything to later.
EMPTY_BODY_DIGEST = compute_body_digest(b"")

#: Challenge ids of the credentials currently between "verified" and "settled",
#: shared across every MPP request in this process.
#:
#: Keyed on the id, never on the header bytes: the bytes are buyer-malleable
#: (scheme case, inner whitespace, JSON key order) while the backend collapses
#: every variant onto one burn, so a byte-keyed set is a guard a buyer walks
#: around by flipping one character. See :func:`mpp_credential_id`.
#:
#: ``verify_credential`` burns nothing and ``settle_credential`` settling the
#: SAME credential twice burns once — that idempotency is what makes settlement
#: safe to retry, and it is exactly what makes concurrent delivery cheap: N
#: concurrent requests presenting the same credential would each pass verify,
#: each get served, and the N settles would collapse to a single burn. This set
#: closes that window WITHIN one process: a second request presenting a
#: credential already in this set is refused rather than served.
#:
#: What this does NOT close: multiple worker processes or horizontally-scaled
#: instances, which do not share this in-memory set and would need a shared
#: store (e.g. Redis) this package does not provide. Note that a multi-worker
#: uvicorn/gunicorn deployment is already several processes, so this caveat
#: applies to an ordinary production setup, not only to a scaled-out cluster.
_in_flight_mpp_credentials: Set[str] = set()

#: FLOOR on how long a settled credential stays refused, in seconds. Matches the
#: backend's ``MPP_CHALLENGE_TTL_SECONDS`` (300): past it the challenge itself is
#: expired, so the credential is refused by the backend anyway and there is
#: nothing left for this map to protect.
#:
#: It is a floor rather than the whole rule because nothing here could otherwise
#: notice the backend raising that TTL — the map would forget a credential the
#: backend still honours, and the advertised "single use" would quietly become
#: "replayable after 300 seconds", which is exactly the replay the backend
#: cannot refuse on its own. :func:`mark_credential_spent` therefore prefers the
#: ``expires`` the challenge itself states.
SPENT_CREDENTIAL_TTL_SECONDS = 300.0

#: CEILING on the same, in seconds. The ``expires`` used to extend the floor is
#: buyer-supplied and unsigned, so a crafted far-future value would otherwise
#: pin an entry in memory indefinitely. Refusing a buyer's own credential for
#: longer harms nobody but them; retaining it forever is our problem, so the
#: window is bounded.
SPENT_CREDENTIAL_MAX_TTL_SECONDS = 3600.0

#: Challenge ids of the credentials whose settlement has already been started,
#: and the instant each stops being worth remembering.
#:
#: The in-flight set closes only the OVERLAP window — it is released when the
#: request ends. Without this second map, a buyer who simply REPEATS the same
#: credential after the first response finished is served again:
#: ``verify_credential`` burns nothing so it verifies clean, and the backend's
#: settle idempotency (the challenge id doubles as the burn key) collapses the
#: second settle onto the first burn instead of rejecting it. The result is pay
#: once, be served for the whole challenge TTL — the backend cannot refuse it,
#: because from its side a replayed settle succeeding IS the idempotency
#: contract working as designed.
#:
#: So single-use is the seller edge's job, and this is where it lives. Same
#: process-local caveat as the in-flight set.
_spent_mpp_credentials: Dict[str, float] = {}


def _ttl_for(challenge_expires: Optional[str]) -> float:
    """How long to remember a credential, given the ``expires`` its challenge
    states.

    Only ever EXTENDS :data:`SPENT_CREDENTIAL_TTL_SECONDS`, never shortens it:
    the value is buyer-supplied and unsigned, and the seller's clock may be
    skewed against the backend's, so a value that reads as already-expired must
    not shrink the window a replay has to get through. Bounded above by
    :data:`SPENT_CREDENTIAL_MAX_TTL_SECONDS`.
    """
    if not challenge_expires:
        return SPENT_CREDENTIAL_TTL_SECONDS
    try:
        expires_at = datetime.fromisoformat(challenge_expires.replace("Z", "+00:00"))
    except ValueError:
        return SPENT_CREDENTIAL_TTL_SECONDS
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
    return min(
        max(remaining, SPENT_CREDENTIAL_TTL_SECONDS), SPENT_CREDENTIAL_MAX_TTL_SECONDS
    )


def mark_credential_spent(
    credential_id: str, challenge_expires: Optional[str] = None
) -> None:
    """Mark a credential spent, and drop the entries that have aged out.

    ``challenge_expires`` is the ``expires`` the credential's own challenge
    carries (:func:`extract_credential_challenge_expires`). Passing it keeps the
    store honest if the backend's challenge TTL is ever raised — see
    :data:`SPENT_CREDENTIAL_TTL_SECONDS`.

    The sweep walks every expired entry rather than stopping at the first live
    one: entries no longer share a single TTL, so insertion order is no longer
    expiry order and an early long-lived entry would otherwise block the sweep
    behind it.
    """
    now = time.monotonic()
    for spent in [k for k, exp in _spent_mpp_credentials.items() if exp <= now]:
        del _spent_mpp_credentials[spent]
    _spent_mpp_credentials[credential_id] = now + _ttl_for(challenge_expires)


def is_credential_spent(credential_id: str) -> bool:
    """Whether this credential has already bought a response."""
    expires_at = _spent_mpp_credentials.get(credential_id)
    if expires_at is None:
        return False
    if expires_at <= time.monotonic():
        del _spent_mpp_credentials[credential_id]
        return False
    return True


def claim_credential(credential_id: str) -> bool:
    """Claim a credential for this request, or report that another one holds it.

    Check and claim are ONE step with no ``await`` between them, which is the
    whole point: several awaits separate the early spent-check from here
    (``on_before_verify``, ``verify_credential``, ``on_after_verify``), and in
    that gap a concurrent request holding the same credential can complete, mark
    itself spent AND release its claim.
    """
    if credential_id in _in_flight_mpp_credentials:
        return False
    _in_flight_mpp_credentials.add(credential_id)
    return True


def release_credential(credential_id: str) -> None:
    """Release the in-flight claim. Safe to call for a credential never claimed."""
    _in_flight_mpp_credentials.discard(credential_id)


def _reset_stores_for_tests() -> None:
    """Clear both process-local stores. Tests only."""
    _in_flight_mpp_credentials.clear()
    _spent_mpp_credentials.clear()


__all__ = [
    "EMPTY_BODY_DIGEST",
    "SPENT_CREDENTIAL_MAX_TTL_SECONDS",
    "MPP_HEADERS",
    "MppRouteOptions",
    "ResolvedMppOption",
    "SPENT_CREDENTIAL_TTL_SECONDS",
    "claim_credential",
    "compute_body_digest",
    "extract_credential",
    "is_credential_spent",
    "mark_credential_spent",
    "mpp_credential_expires",
    "mpp_credential_id",
    "mpp_resource",
    "mpp_verb",
    "release_credential",
    "resolve_mpp_option",
]
