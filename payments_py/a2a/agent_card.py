"""Helper to build an AgentCard enriched with payment metadata (Python version)."""

from __future__ import annotations

from typing import Any, Dict, List

from payments_py.a2a.types import PaymentAgentCardMetadata


def build_payment_agent_card(
    base_card: Dict[str, Any], payment_metadata: PaymentAgentCardMetadata
) -> Dict[str, Any]:  # noqa: D401
    """Return a new agent card with payments extension.

    Args:
        base_card: The original agent card (dict following a2a.types.AgentCard schema).
        payment_metadata: Dict with payment information.

    Raises:
        ValueError: If required fields are missing or invalid.

    Returns:
        A copy of *base_card* that contains the payment extension in
        ``capabilities.extensions``.
    """
    # ------------------------------------------------------------------
    # Basic validation (mirror TS)
    # ------------------------------------------------------------------
    if "paymentType" not in payment_metadata:
        raise ValueError("paymentType is required")

    credits = payment_metadata.get("credits", 0)
    if credits < 0:
        raise ValueError("credits cannot be negative")

    if payment_metadata.get("isTrialPlan"):
        # Trial plan can have 0 credits, nothing else to check
        pass
    else:
        if credits <= 0:
            raise ValueError("credits must be a positive number for paid plans")

    if not payment_metadata.get("agentId"):
        raise ValueError("agentId is required")

    # ------------------------------------------------------------------
    # Build new card
    # ------------------------------------------------------------------
    extensions: List[Dict[str, Any]] = (
        base_card.get("capabilities", {}).get("extensions", []) or []
    )

    payment_extension = {
        "uri": "urn:nevermined:payment",
        "description": payment_metadata.get("costDescription"),
        "required": False,
        "params": dict(payment_metadata),  # cast to plain dict
    }

    new_extensions = [*extensions, payment_extension]

    capabilities = {
        **(base_card.get("capabilities", {})),
        "extensions": new_extensions,
    }

    return {**base_card, "capabilities": capabilities}
