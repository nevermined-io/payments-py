"""
Public types for the Machine Payments Protocol (MPP) surface.

MPP is a second payment framing over the unchanged plans/credits/delegations
core: the same plan, the same delegation and the same credit burn as x402,
negotiated with different HTTP headers.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class MppChallengeRequest:
    """What the buyer is being asked to pay for. Sealed inside the challenge HMAC."""

    #: The Nevermined plan the credits are burned against.
    plan_id: str
    #: Credits to redeem, as a decimal string.
    credits: str
    #: Agent the request is addressed to.
    agent_id: Optional[str] = None


@dataclass
class MppChallenge:
    """A parsed ``WWW-Authenticate: Payment …`` challenge.

    ``request_encoded`` and ``opaque`` are kept as the exact base64url strings
    the server sent: the challenge id is an HMAC over them, so re-encoding
    either one would invalidate the credential built from this challenge.
    """

    id: str
    realm: str
    method: str
    intent: str
    request: MppChallengeRequest
    request_encoded: str
    expires: Optional[str] = None
    digest: Optional[str] = None
    opaque: Optional[str] = None
    description: Optional[str] = None


@dataclass
class MppReceipt:
    """A decoded ``Payment-Receipt``. Unsigned by design, and carries no balance."""

    method: str
    reference: str
    status: str
    timestamp: str


__all__ = ["MppChallenge", "MppChallengeRequest", "MppReceipt"]
