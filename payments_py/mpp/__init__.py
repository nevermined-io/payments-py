"""
Machine Payments Protocol (MPP) module.
"""

from .codec import (
    build_credential_header,
    extract_credential_challenge_id,
    extract_payment_scheme,
    parse_challenge_header,
    parse_receipt_header,
)
from .errors import (
    MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE,
    MPP_SPEND_OUTCOME_UNKNOWN_CODE,
    MppBodyDigestMismatchError,
    MppChallengeExpiredError,
    MppCredentialRejectedError,
    MppError,
    MppNotConfiguredError,
    MppSettlementOutcomeUnknown,
    MppSettlementOutcomeUnknownError,
    MppSpendOutcomeUnknownError,
    MppSpendReport,
    # The docstring on is_retryable_mpp_code exists to stop a buyer hardcoding
    # ["BCK.MPP.0004", "BCK.MPP.0005"] at their call site, where it goes stale
    # the moment a code joins the set — so the function has to be reachable from
    # the package, not just from inside it. The wire-level ``retryable`` flag the
    # middleware puts on its 402s only helps buyers of THIS middleware; a buyer
    # calling payments.mpp.* directly and catching MppError has nothing but
    # ``error.code``.
    is_retryable_mpp_code,
    # Same argument as is_retryable_mpp_code: the accounting a buyer needs after
    # a failed payment rides on two error classes with no common base (MppError
    # and PaymentsError), so ``mpp_spend_of`` has to be reachable from the
    # package or every consumer reaches into ``__dict__``.
    mpp_spend_of,
)

# ``mpp_fetch`` itself is deliberately NOT re-exported: ``payments.mpp.fetch``
# (via ``MppAPI``) is the intended public surface — it routes through
# ``MppAPI._post``'s error translation and the ``Nevermined-Version`` pinning.
# Exporting the free function would hand consumers a supported way to bypass
# both, which could not be withdrawn later without a major bump. Tests import
# ``payments_py.mpp.fetch`` directly.
from .fetch import MppFetchOptions, MppFetchResult
from .mpp_api import (
    IssueMppChallengeParams,
    MppAPI,
    RedeemMppParams,
    normalize_credits,
)
from .types import MppChallenge, MppChallengeRequest, MppReceipt

__all__ = [
    "normalize_credits",
    "RedeemMppParams",
    "MppFetchResult",
    "MppFetchOptions",
    "MppAPI",
    "IssueMppChallengeParams",
    "MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE",
    "MPP_SPEND_OUTCOME_UNKNOWN_CODE",
    "MppBodyDigestMismatchError",
    "MppChallenge",
    "MppChallengeExpiredError",
    "MppChallengeRequest",
    "MppCredentialRejectedError",
    "MppError",
    "MppNotConfiguredError",
    "MppReceipt",
    "MppSettlementOutcomeUnknown",
    "MppSettlementOutcomeUnknownError",
    "MppSpendOutcomeUnknownError",
    "MppSpendReport",
    "build_credential_header",
    "extract_credential_challenge_id",
    "extract_payment_scheme",
    "is_retryable_mpp_code",
    "mpp_spend_of",
    "parse_challenge_header",
    "parse_receipt_header",
]
