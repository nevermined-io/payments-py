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
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set, Union

from starlette.requests import Request

from payments_py.mpp.codec import (
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


def resolve_mpp_option(
    option: Optional[Union[bool, Dict[str, Any]]],
) -> ResolvedMppOption:
    """Normalize the per-route ``mpp`` option. ``True`` is shorthand for
    ``{"bind_body": False}``."""
    if option is None or option is False:
        return ResolvedMppOption(enabled=False, bind_body=False)
    if option is True:
        return ResolvedMppOption(enabled=True, bind_body=False)
    return ResolvedMppOption(
        enabled=True, bind_body=option.get("bind_body", False) is True
    )


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

#: How long a settled credential stays refused. Matches the backend's
#: ``MPP_CHALLENGE_TTL_SECONDS`` (300): past it the challenge itself is expired,
#: so the credential is refused by the backend anyway and there is nothing left
#: for this map to protect.
SPENT_CREDENTIAL_TTL_SECONDS = 300.0

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


def mark_credential_spent(credential_id: str) -> None:
    """Mark a credential spent, and drop the entries that have aged out.

    Every entry gets the same TTL, so insertion order IS expiry order: the sweep
    can stop at the first entry still alive instead of walking the whole map on
    every settlement.
    """
    now = time.monotonic()
    for spent, expires_at in list(_spent_mpp_credentials.items()):
        if expires_at > now:
            break
        del _spent_mpp_credentials[spent]
    _spent_mpp_credentials[credential_id] = now + SPENT_CREDENTIAL_TTL_SECONDS


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
    "MPP_HEADERS",
    "ResolvedMppOption",
    "SPENT_CREDENTIAL_TTL_SECONDS",
    "claim_credential",
    "compute_body_digest",
    "extract_credential",
    "is_credential_spent",
    "mark_credential_spent",
    "mpp_credential_id",
    "mpp_resource",
    "mpp_verb",
    "release_credential",
    "resolve_mpp_option",
]
