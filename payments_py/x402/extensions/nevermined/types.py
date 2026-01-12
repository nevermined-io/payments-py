"""
Nevermined Extension Types

Defines the structure and types for the Nevermined payment extension.
"""

from typing import Optional
from typing_extensions import TypedDict

# Extension identifier constants
# Base identifier for Nevermined extensions
NEVERMINED = "nevermined"


# Qualified extension identifiers for multiple plans
# Format: "nevermined:{plan_type}" where plan_type is a descriptive identifier
# Examples: "nevermined:credits", "nevermined:payasyougo"
def nevermined_extension_key(plan_type: str) -> str:
    """
    Generate a qualified extension key for a Nevermined plan.

    Args:
        plan_type: Descriptive identifier for the plan (e.g., "credits", "payasyougo")

    Returns:
        Qualified extension key (e.g., "nevermined:credits")
    """
    return f"{NEVERMINED}:{plan_type}"


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
        environment: Nevermined environment ("sandbox", "live")
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
    "nevermined_extension_key",
    "NeverminedInfo",
    "NeverminedExtension",
]
