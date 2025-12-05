"""
Facilitator helpers for extracting Nevermined extension data.

These functions help facilitators parse and validate Nevermined extension
metadata from payment payloads following the x402 v2 extension pattern.
"""

from typing import Any, Dict, List, Optional

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
        # Look for qualified Nevermined extensions (e.g., "nevermined:credits")
        # or legacy single "nevermined" extension
        extensions = payment_payload.get("extensions", {})

        # First, try to find any qualified Nevermined extension
        for ext_key, ext_data in extensions.items():
            if ext_key.startswith(f"{NEVERMINED}:"):
                # Found a qualified Nevermined extension
                if validate:
                    result = validate_nevermined_extension(ext_data)
                    if not result["valid"]:
                        continue  # Try next extension

                # Return the info part
                if isinstance(ext_data, dict):
                    return ext_data.get("info")
                else:
                    return ext_data.info if hasattr(ext_data, "info") else None

        # Fallback to legacy single "nevermined" extension
        nvm_extension = extensions.get(NEVERMINED)
        if nvm_extension:
            # Found Nevermined extension
            if validate:
                # Validate against schema (handles both dict and Extension model)
                result = validate_nevermined_extension(nvm_extension)  # type: ignore
                if not result["valid"]:
                    print(
                        f"Nevermined extension validation failed: {result.get('errors')}"
                    )
                    return None

            # Return the info part of the extension
            # Handle both dict and Pydantic Extension model
            if isinstance(nvm_extension, dict):
                return nvm_extension.get("info")  # type: ignore
            else:
                # Pydantic Extension model
                return nvm_extension.info  # type: ignore

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


def extract_all_nevermined_plans(
    payment_required: Dict[str, Any],
    validate: bool = True,
) -> List[Dict[str, Any]]:
    """
    Extract all Nevermined plans from PaymentRequired response extensions.

    For v2 with multiple plans, each plan is its own extension entry with
    qualified keys like "nevermined:credits", "nevermined:payasyougo".

    Args:
        payment_required: The PaymentRequired response from the server
        validate: Whether to validate against JSON Schema (default: True)

    Returns:
        List of dictionaries containing plan info, each with:
        - extension_key: The extension key (e.g., "nevermined:credits")
        - plan_id: Nevermined plan ID
        - agent_id: Nevermined agent ID
        - max_amount: Maximum credits to burn
        - network: Blockchain network
        - scheme: Payment scheme
        - environment: Optional Nevermined environment

    Example:
        >>> from payments_py.x402.extensions.nevermined import extract_all_nevermined_plans
        >>>
        >>> plans = extract_all_nevermined_plans(payment_required_response)
        >>> for plan in plans:
        ...     print(f"Plan ID: {plan['plan_id']} ({plan['extension_key']})")
        ...     print(f"  Amount: {plan['max_amount']} credits")
        ...     # Plan name can be fetched from Nevermined API using plan_id if needed
    """
    plans = []

    # Check if this is v2 with extensions
    x402_version = payment_required.get(
        "x402Version", payment_required.get("x402_version", 1)
    )

    if x402_version == 2:
        extensions = payment_required.get("extensions", {})

        # Look for all Nevermined extensions (qualified keys like "nevermined:credits")
        for ext_key, ext_data in extensions.items():
            if ext_key.startswith(f"{NEVERMINED}:"):
                # This is a Nevermined plan extension
                if validate:
                    result = validate_nevermined_extension(ext_data)
                    if not result["valid"]:
                        continue  # Skip invalid extensions

                # Extract info
                if isinstance(ext_data, dict):
                    info = ext_data.get("info", {})
                else:
                    # Pydantic Extension model
                    info = ext_data.info if hasattr(ext_data, "info") else {}

                if info and "plan_id" in info:
                    plans.append(
                        {
                            "extension_key": ext_key,
                            "plan_id": info.get("plan_id"),
                            "agent_id": info.get("agent_id"),
                            "max_amount": info.get("max_amount"),
                            "network": info.get("network"),
                            "scheme": info.get("scheme"),
                            "environment": info.get("environment"),
                        }
                    )

        # Also check for legacy single "nevermined" extension (backwards compatibility)
        if NEVERMINED in extensions and not plans:
            ext_data = extensions[NEVERMINED]
            if validate:
                result = validate_nevermined_extension(ext_data)
                if not result["valid"]:
                    return plans

            if isinstance(ext_data, dict):
                info = ext_data.get("info", {})
            else:
                info = ext_data.info if hasattr(ext_data, "info") else {}

            if info and "plan_id" in info:
                plans.append(
                    {
                        "extension_key": NEVERMINED,
                        "plan_id": info.get("plan_id"),
                        "agent_id": info.get("agent_id"),
                        "max_amount": info.get("max_amount"),
                        "network": info.get("network"),
                        "scheme": info.get("scheme"),
                        "environment": info.get("environment"),
                    }
                )

    return plans


__all__ = ["extract_nevermined_info", "extract_all_nevermined_plans"]
