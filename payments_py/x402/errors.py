"""
Typed x402 errors that need their own branch at the call site.

Everything the backend rejects still arrives as a :class:`PaymentsError` with
the canonical ``BCK.X402.*`` code on ``.code``. This module promotes the one
code whose *remedy* differs from every other rejection into its own class, so a
caller can react without string-matching a message.
"""

from typing import Any, Optional

from payments_py.common.payments_error import PaymentsError

#: ``BCK.X402.0059`` — a v3 (single-use) access token was presented to
#: ``POST /x402/settle`` after it had already been consumed.
#:
#: Deliberately NOT forgery-gated at the backend: unlike ``BCK.X402.0005``
#: (signature/envelope mismatch) it says plainly that the token was spent, and
#: it is the one rejection a buyer fixes by minting a new token rather than by
#: fixing what they sent.
X402_TOKEN_ALREADY_USED_CODE = "BCK.X402.0059"

#: Appended to the backend's own message so the remedy travels with the error,
#: including through logs that only keep ``str(err)``.
_ALREADY_USED_REMEDY = (
    "This x402 access token was already spent — a v3 token is single-use and is "
    "consumed by its first settle. Mint a new access token instead of replaying "
    "this one; do not retry the same token."
)


class AccessTokenAlreadyUsedError(PaymentsError):
    """``BCK.X402.0059`` — the access token was already consumed by a settle.

    A subclass of :class:`PaymentsError` (never a sibling) so existing
    ``except PaymentsError`` handlers keep working unchanged; ``.code`` stays
    :data:`X402_TOKEN_ALREADY_USED_CODE`.

    A retry wrapper must treat this as "re-mint", not "retry": replaying the
    same token can only produce this error again, however many times it runs.
    """

    def __init__(self, message: str = _ALREADY_USED_REMEDY):
        super().__init__(message, X402_TOKEN_ALREADY_USED_CODE)


def is_access_token_already_used(error: Any) -> bool:
    """Whether ``error`` is the "token already spent" rejection.

    Checks ``.code`` rather than ``isinstance``: the code is the wire-level
    discriminant, so this still answers correctly for an error that crossed a
    process or serialization boundary, or that came from a second copy of this
    package in the same environment.
    """
    return getattr(error, "code", None) == X402_TOKEN_ALREADY_USED_CODE


def x402_error_from_response(
    response: Optional[Any], fallback_message: str
) -> PaymentsError:
    """:meth:`PaymentsError.from_response`, upgrading ``BCK.X402.0059`` to
    :class:`AccessTokenAlreadyUsedError`.

    Used by the facilitator's verify/settle paths so a spent token surfaces as
    its own actionable failure instead of being flattened into the same generic
    error as a declined plan or a forged envelope.
    """
    error = PaymentsError.from_response(response, fallback_message)
    if error.code == X402_TOKEN_ALREADY_USED_CODE:
        return AccessTokenAlreadyUsedError(f"{error} — {_ALREADY_USED_REMEDY}")
    return error


__all__ = [
    "AccessTokenAlreadyUsedError",
    "X402_TOKEN_ALREADY_USED_CODE",
    "is_access_token_already_used",
    "x402_error_from_response",
]
