"""
Nevermined Extension Types

Defines the structure and types for the Nevermined payment extension.
"""

from typing import Optional
from typing_extensions import TypedDict

# Extension identifier constant
# This is used as the key in the extensions dictionary
NEVERMINED = "nevermined"


class NeverminedInfo(TypedDict, total=False):
    """
    Information for Nevermined payments.

    This is the 'info' part of the Nevermined extension, containing
    the actual payment requirements data.

    Required fields:
        plan_id: Nevermined pricing plan ID
        agent_id: Nevermined AI agent ID
        max_amount: Maximum credits to burn per request (as string)
        network: Blockchain network (e.g., "base-sepolia")
        scheme: Payment scheme (e.g., "contract")

    Optional fields:
        environment: Nevermined environment ("staging", "sandbox", "production")
        subscriber_address: Subscriber's blockchain address
    """

    # Required fields
    plan_id: str
    agent_id: str
    max_amount: str
    network: str
    scheme: str

    # Optional fields
    environment: Optional[str]
    subscriber_address: Optional[str]


class NeverminedExtension(TypedDict):
    """
    Complete Nevermined extension structure (info + schema).

    Follows the x402 v2 extension pattern where extensions contain:
    - info: The actual extension data
    - schema: JSON Schema validating the info

    This structure allows for self-validating, machine-readable metadata.
    """

    info: NeverminedInfo
    schema: dict


__all__ = [
    "NEVERMINED",
    "NeverminedInfo",
    "NeverminedExtension",
]
