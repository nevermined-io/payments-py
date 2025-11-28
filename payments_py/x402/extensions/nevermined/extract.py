"""
Facilitator helpers for extracting Nevermined extension data.

These functions help facilitators parse and validate Nevermined extension
metadata from payment payloads following the x402 v2 extension pattern.
"""

from typing import Any, Dict, Optional

from .types import NeverminedInfo, NEVERMINED
from .validate import validate_nevermined_extension


def extract_nevermined_info(
    payment_payload: Dict[str, Any],
    payment_requirements: Optional[Dict[str, Any]] = None,
    validate: bool = True,
) -> Optional[NeverminedInfo]:
    """
    Extract Nevermined information from payment payload.

    Handles both v2 (extensions field) and v1 (extra field) formats for
    backward compatibility during migration.

    For v2: Extensions are in PaymentPayload.extensions (client copied from PaymentRequired)
    For v1: Nevermined data is in PaymentRequirements.extra

    Args:
        payment_payload: The payment payload from the client
        payment_requirements: Optional payment requirements (for v1 fallback)
        validate: Whether to validate against JSON Schema (default: True)

    Returns:
        NeverminedInfo if found and valid, None otherwise

    Example:
        >>> from payments_py.x402.extensions.nevermined import extract_nevermined_info
        >>>
        >>> # Extract from v2 payment payload
        >>> nvm_info = extract_nevermined_info(payment_payload, payment_requirements)
        >>>
        >>> if nvm_info:
        ...     plan_id = nvm_info["plan_id"]
        ...     agent_id = nvm_info["agent_id"]
        ...     max_amount = nvm_info["max_amount"]
        ...
        ...     # Proceed with verification/settlement
        ...     # - Check subscriber balance
        ...     # - Order credits if needed
        ...     # - Burn credits on settlement

    V2 vs V1:
        >>> # V2: Extensions in PaymentPayload
        >>> payment_payload = {
        ...     "x402Version": 2,
        ...     "extensions": {
        ...         "nevermined": {
        ...             "info": {...},
        ...             "schema": {...}
        ...         }
        ...     }
        ... }
        >>>
        >>> # V1: Nevermined data in PaymentRequirements.extra
        >>> payment_requirements = {
        ...     "extra": {
        ...         "plan_id": "...",
        ...         "agent_id": "...",
        ...         ...
        ...     }
        ... }
    """
    # Get x402 version (default to 1 for backward compatibility)
    x402_version = payment_payload.get("x402Version", 1)

    if x402_version == 2:
        # V2: Check extensions field in PaymentPayload
        extensions = payment_payload.get("extensions", {})
        nvm_extension = extensions.get(NEVERMINED)

        if nvm_extension and isinstance(nvm_extension, dict):
            # Found Nevermined extension
            if validate:
                # Validate against schema
                result = validate_nevermined_extension(nvm_extension)  # type: ignore
                if not result["valid"]:
                    print(
                        f"Nevermined extension validation failed: {result.get('errors')}"
                    )
                    return None

            # Return the info part of the extension
            return nvm_extension.get("info")  # type: ignore

    # V1 fallback: Check extra field in PaymentRequirements
    if payment_requirements:
        extra = payment_requirements.get("extra", {})

        # Check if this looks like Nevermined data
        if "plan_id" in extra and "agent_id" in extra:
            # Construct NeverminedInfo from extra field
            return {
                "plan_id": extra["plan_id"],
                "agent_id": extra["agent_id"],
                "max_amount": extra.get("max_amount", ""),
                "network": extra.get("network", ""),
                "scheme": extra.get("scheme", ""),
                "environment": extra.get("environment"),
                "subscriber_address": extra.get("subscriber_address"),
            }

    # No Nevermined data found
    return None


__all__ = ["extract_nevermined_info"]

