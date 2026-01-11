"""
Server helpers for declaring Nevermined extension metadata.

These functions help resource servers attach Nevermined payment requirements
to their PaymentRequired responses following the x402 v2 extension pattern.
"""

from typing import Optional

from .types import NeverminedExtension, NeverminedInfo


def declare_nevermined_extension(
    plan_id: str,
    agent_id: str,
    max_amount: str,
    network: str = "base-sepolia",
    scheme: str = "contract",
    environment: Optional[str] = None,
    subscriber_address: Optional[str] = None,
) -> NeverminedExtension:
    """
    Create a Nevermined extension for a PaymentRequired response.

    This helper creates properly formatted Nevermined extension metadata
    that can be included in a PaymentRequired response. It follows the
    x402 v2 extension pattern of info + schema.

    Args:
        plan_id: Nevermined pricing plan ID
        agent_id: Nevermined AI agent ID
        max_amount: Maximum credits to burn per request (as string)
        network: Blockchain network (default: "base-sepolia")
        scheme: Payment scheme (default: "contract")
        environment: Nevermined environment ("sandbox", "live")
        subscriber_address: Optional subscriber blockchain address

    Returns:
        NeverminedExtension with info and schema following x402 v2 pattern

    Example:
        >>> from payments_py.x402.extensions.nevermined import (
        ...     declare_nevermined_extension,
        ...     NEVERMINED
        ... )
        >>> from payments_py.x402.types_v2 import (
        ...     PaymentRequiredResponseV2,
        ...     ResourceInfo
        ... )
        >>>
        >>> extension = declare_nevermined_extension(
        ...     plan_id="85917684554499762134516240562181895926019634254204202319880150802501990701934",
        ...     agent_id="80918427023170428029540261117198154464497879145267720259488529685089104529015",
        ...     max_amount="2",
        ...     network="base-sepolia",
        ...     environment="sandbox"
        ... )
        >>>
        >>> payment_required = PaymentRequiredResponseV2(
        ...     x402_version=2,
        ...     resource=ResourceInfo(url="https://api.example.com/data"),
        ...     accepts=[...],
        ...     extensions={
        ...         NEVERMINED: extension
        ...     }
        ... )
    """
    # Build the info object with required fields
    info: NeverminedInfo = {
        "plan_id": plan_id,
        "agent_id": agent_id,
        "max_amount": max_amount,
        "network": network,
        "scheme": scheme,
    }

    # Add optional fields if provided
    if environment:
        info["environment"] = environment
    if subscriber_address:
        info["subscriber_address"] = subscriber_address

    # Define JSON Schema for validation
    # This allows facilitators to validate the extension data
    schema = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "plan_id": {
                "type": "string",
                "description": "Nevermined pricing plan ID",
            },
            "agent_id": {
                "type": "string",
                "description": "Nevermined AI agent ID",
            },
            "max_amount": {
                "type": "string",
                "description": "Maximum credits to burn per request",
            },
            "network": {
                "type": "string",
                "description": "Blockchain network (e.g., base-sepolia)",
            },
            "scheme": {
                "type": "string",
                "description": "Payment scheme (e.g., contract)",
            },
            "environment": {
                "type": "string",
                "description": "Nevermined environment (staging_sandbox, staging_live, sandbox, live, custom)",
                "enum": [
                    "staging_sandbox",
                    "staging_live",
                    "sandbox",
                    "live",
                    "custom",
                ],
            },
            "subscriber_address": {
                "type": "string",
                "description": "Subscriber's blockchain address",
            },
        },
        "required": ["plan_id", "agent_id", "max_amount", "network", "scheme"],
        "additionalProperties": False,
    }

    return {"info": info, "schema": schema}


__all__ = ["declare_nevermined_extension"]
