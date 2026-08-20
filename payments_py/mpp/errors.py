"""
Typed errors for the MPP surface.

The backend deliberately collapses every rejection reason into one code so the
endpoint cannot be used as a forgery oracle. The SDK mirrors that: it does not
try to reconstruct why a credential was refused.
"""

from dataclasses import dataclass
from typing import Any, FrozenSet, Optional


@dataclass
class MppSpendReport:
    """What a buyer-side failure reports about money already committed.

    ``payments.mpp.fetch`` returns this accounting on its success path
    (``credentials_presented`` / ``credits_presented`` on ``MppFetchResult``).
    It is repeated on the ERROR path because that is where a caller needs it
    most: the credential and its access token are function-local and gone once
    the helper raises, so an error without these numbers leaves the caller
    unable to tell whether money left — the one outcome a buyer helper must
    never produce.

    Read it with :func:`mpp_spend_of` rather than reaching for the attribute:
    it rides on ``PaymentsError`` too (a ``max_credits`` or ``plan_id`` guard
    can fire on the re-challenge turn, after a credential has already been
    presented).
    """

    #: How many credentials were minted and sent before the failure (0, 1 or 2).
    credentials_presented: int
    #: Total credits named by the challenges those credentials were minted
    #: against, as a decimal string. Present whenever ``credentials_presented > 0``.
    credits_presented: Optional[str] = None
    #: ``id`` of the challenge the last credential was minted against, so the
    #: caller can correlate it with the seller's side.
    challenge_id: Optional[str] = None


def mpp_spend_of(error: Any) -> Optional[MppSpendReport]:
    """Read the spend accounting off any error raised by ``payments.mpp.fetch``.

    Exported so a caller never has to reach into ``__dict__``: the attribute is
    declared on :class:`MppError` but is also attached to the ``PaymentsError``
    a caller-constraint guard raises on the re-challenge turn, and those two do
    not share a base class.

    A report is attached **only** when at least one credential was presented,
    so a non-``None`` result always means money may have left, and ``None``
    always means nothing was spent. That is what makes ``if mpp_spend_of(err):``
    a usable test rather than one that fires on plain argument validation too.
    """
    spend = getattr(error, "spend", None)
    if not isinstance(spend, MppSpendReport):
        return None
    return spend


class MppError(Exception):
    """Base class for every typed MPP failure."""

    def __init__(self, message: str, code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.code = code
        #: Spend accounting, set when this error was raised after a credential
        #: had been minted and presented. ``None`` means nothing was spent.
        #: Prefer :func:`mpp_spend_of`, which also reads it off a
        #: ``PaymentsError``.
        self.spend: Optional[MppSpendReport] = None


class MppNotConfiguredError(MppError):
    """``BCK.MPP.0002`` — the deployment has no MPP secret, so MPP routes are off."""

    def __init__(self, message: str = "MPP is not configured on this environment"):
        super().__init__(message, "BCK.MPP.0002")


class MppCredentialRejectedError(MppError):
    """``BCK.MPP.0003`` — the credential was refused (replay, forgery, plan, balance)."""

    def __init__(self, message: str = "MPP credential rejected"):
        super().__init__(message, "BCK.MPP.0003")


class MppChallengeExpiredError(MppError):
    """``BCK.MPP.0004`` — the challenge expired. Fetch a fresh one; do not retry blindly."""

    def __init__(self, message: str = "MPP challenge expired"):
        super().__init__(message, "BCK.MPP.0004")


class MppBodyDigestMismatchError(MppError):
    """``BCK.MPP.0005`` — the body sent does not match the digest sealed in the challenge."""

    def __init__(self, message: str = "MPP body digest mismatch"):
        super().__init__(message, "BCK.MPP.0005")


#: Stable ``code`` on :class:`MppSettlementOutcomeUnknownError`. Not a backend
#: code — no ``BCK.MPP.*`` prefix, so it can never collide with one.
MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE = "settlement_outcome_unknown"


class MppSettlementOutcomeUnknownError(MppError):
    """Settlement's outcome could not be determined.

    Raised when ``settle_credential``'s own outbound deadline fires before any
    response, when the connection dies after the request was written, when the
    backend answers 5xx/408, or when a 2xx body could not be read. Settlement is
    the one MPP call that burns, so in all of those cases the burn may already
    have happened even though the caller received nothing usable. Collapsing
    that into the same ``network_error`` :class:`MppError` used for "nothing
    happened" failures (connection refused, DNS failure, a hung
    challenge/verify call) would let a real burn be logged and treated exactly
    like one that never occurred — silently corrupting the seller's own
    accounting on the call that is not safe to shrug off.
    """

    def __init__(
        self,
        message: str = (
            "MPP settlement outcome unknown: the request timed out before the "
            "backend responded, so the credits may or may not have been burned"
        ),
    ):
        # No backend issues this code — the condition is detected here — but it
        # still carries one, following the same convention as the other
        # SDK-invented codes (``network_error``, ``http_<status>``). ``code`` is
        # the only DATA-level discriminant on this hierarchy, and this is the
        # branch whose whole point is that misclassifying it corrupts the
        # seller's accounting. Two copies of this package in one environment
        # make ``isinstance`` false for a genuinely-MPP error, and the check
        # would degrade silently to the "nothing happened" path — which the
        # integration guide tells sellers to rely on. Same across a process or
        # serialization boundary.
        super().__init__(message, MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE)


#: Stable ``code`` on :class:`MppSpendOutcomeUnknownError`. Not a backend code,
#: for the same reason as :data:`MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE`.
MPP_SPEND_OUTCOME_UNKNOWN_CODE = "spend_outcome_unknown"


class MppSpendOutcomeUnknownError(MppError):
    """The buyer-side mirror of :class:`MppSettlementOutcomeUnknownError`.

    Raised when the retry that carries a credential fails at the transport
    level — a disconnect, a DNS failure, or a read timeout after the request
    was written.

    The credential is on the wire by then, so the seller may already have
    verified and burned it. Left as the raw ``requests`` exception, the failure
    would escape the ``except MppError`` pattern this module and the MPP
    integration guide both prescribe, and carry no accounting at all: spent,
    invisible, unrecoverable. Wrapped, it reaches the documented handler with
    :class:`MppSpendReport` attached and the original error preserved on
    ``__cause__`` and ``cause``.

    A transport failure BEFORE any credential exists is not this error — it
    stays exactly as ``requests`` raised it, because nothing was spent and
    wrapping it would only obscure a plain network fault.
    """

    def __init__(
        self,
        message: str,
        cause: Optional[BaseException] = None,
        spend: Optional[MppSpendReport] = None,
    ):
        super().__init__(message, MPP_SPEND_OUTCOME_UNKNOWN_CODE)
        #: The original error ``requests`` (or the mint) raised.
        self.cause = cause
        self.spend = spend


@dataclass
class MppSettlementOutcomeUnknown:
    """What ``payment_middleware``'s ``on_after_settle`` hook receives as its
    third argument when settlement raised
    :class:`MppSettlementOutcomeUnknownError`.

    That parameter is untyped (shared with the x402 hook of the same name), so
    nothing stops a consumer from treating it as a settle result and silently
    reading ``None`` for ``credits_redeemed`` on this branch. Passing this shape
    gives a consumer something concrete to check for instead — e.g.
    ``isinstance(result, MppSettlementOutcomeUnknown)`` — and documents that the
    branch exists at all.
    """

    reason: str
    outcome: str = "unknown"


#: ``BCK.MPP.*`` codes a buyer can retry by minting a fresh credential against
#: the NEW challenge the same 402 carries alongside them — as opposed to
#: ``BCK.MPP.0003``, which means the credential itself was refused and paying
#: again cannot help.
#:
#: ``0004`` (expired) is obviously retryable: fetch a fresh challenge, pay it.
#: ``0005`` (body digest mismatch) is less obvious but equally retryable: the
#: fresh challenge is sealed to the digest of the request that just arrived, so
#: a credential minted against it — presented with the SAME body — would
#: succeed. A buyer gate that only excepts ``0004`` from a bare
#: ``code.startswith("BCK.MPP.")`` check wrongly treats ``0005`` as terminal and
#: gives up on a request that would have worked on the next attempt.
#:
#: Grouped here, once, so a buyer checks :func:`is_retryable_mpp_code` instead
#: of hardcoding the exception list — and so a future retryable code only needs
#: to be added to this one set. Exported so the buyer's own tests derive their
#: table from this set instead of repeating its members, which is what makes "a
#: code added here is honoured by ``payments.mpp.fetch``" an enforced property
#: rather than a convention. It is deliberately NOT re-exported from the
#: package barrel: a mutable-looking membership list is not public API.
RETRYABLE_BCK_MPP_CODES: FrozenSet[str] = frozenset({"BCK.MPP.0004", "BCK.MPP.0005"})


def is_retryable_mpp_code(code: Optional[str]) -> bool:
    """Whether a ``BCK.MPP.*`` code means "mint a fresh credential and try
    again" rather than "this credential was refused; a new one changes nothing"."""
    return code is not None and code in RETRYABLE_BCK_MPP_CODES


def to_mpp_error(code: Optional[str], message: str) -> MppError:
    """Map a backend error payload onto the typed error hierarchy."""
    if code == "BCK.MPP.0002":
        return MppNotConfiguredError(message)
    if code == "BCK.MPP.0003":
        return MppCredentialRejectedError(message)
    if code == "BCK.MPP.0004":
        return MppChallengeExpiredError(message)
    if code == "BCK.MPP.0005":
        return MppBodyDigestMismatchError(message)
    return MppError(message, code)


__all__ = [
    "MppError",
    "MppNotConfiguredError",
    "MppCredentialRejectedError",
    "MppChallengeExpiredError",
    "MppBodyDigestMismatchError",
    "MppSettlementOutcomeUnknownError",
    "MppSettlementOutcomeUnknown",
    "MppSpendOutcomeUnknownError",
    "MppSpendReport",
    "MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE",
    "MPP_SPEND_OUTCOME_UNKNOWN_CODE",
    "RETRYABLE_BCK_MPP_CODES",
    "is_retryable_mpp_code",
    "mpp_spend_of",
    "to_mpp_error",
]
