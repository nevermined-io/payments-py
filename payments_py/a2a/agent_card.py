"""Helper to build an AgentCard enriched with payment metadata (Python version)."""

from __future__ import annotations

from typing import Any, Dict, List

from payments_py.a2a.types import PaymentAgentCardMetadata
from payments_py.x402.a2a import A2A_X402_EXTENSION_URI

# Canonical A2A agent-card discovery path (A2A >= 0.3, per RFC 8615). Served by
# Nevermined A2A agents and used as the default when fetching a remote card.
AGENT_CARD_WELL_KNOWN_PATH = ".well-known/agent-card.json"

# Legacy pre-0.3 discovery path. Still served as a backward-compat alias and
# tried as a fetch fallback, so updated clients keep working against Nevermined
# agents that have not adopted the canonical path yet.
# ponytail: drop the alias + fallback one release after agents are updated.
LEGACY_AGENT_CARD_WELL_KNOWN_PATH = ".well-known/agent.json"


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

    plan_id = payment_metadata.get("planId")
    plan_ids = payment_metadata.get("planIds")

    if plan_id and plan_ids:
        raise ValueError("Provide either planId or planIds, not both")

    if plan_ids is not None:
        if not isinstance(plan_ids, list) or len(plan_ids) == 0:
            raise ValueError("planIds must be a non-empty list")

    if not plan_id and not plan_ids:
        raise ValueError("Either planId or planIds is required")

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

    # Also declare the official A2A x402 extension (v0.2) so generic,
    # spec-compliant A2A clients can detect and activate the standards-based
    # in-band payment flow. The Nevermined-specific extension is kept alongside
    # it for one release (it still carries the agentId / plan params the server
    # reads). ponytail: drop urn:nevermined:payment once clients use v0.2 only.
    x402_extension = {
        "uri": A2A_X402_EXTENSION_URI,
        "description": (
            "Supports payments using the x402 protocol for on-chain settlement."
        ),
        "required": False,
    }

    # Avoid duplicating an already-present official extension (idempotent build).
    has_official = any(
        (ext.get("uri") if isinstance(ext, dict) else None) == A2A_X402_EXTENSION_URI
        for ext in extensions
    )
    new_extensions = [*extensions, payment_extension]
    if not has_official:
        new_extensions.append(x402_extension)

    capabilities = {
        **(base_card.get("capabilities", {})),
        "extensions": new_extensions,
    }

    return {**base_card, "capabilities": capabilities}
