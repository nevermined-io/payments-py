"""
X402 Helper Functions.

Utility functions for building x402 payment protocol objects.
"""

from typing import Optional

from .types import X402PaymentRequired, X402Resource, X402Scheme, X402SchemeExtra

__all__ = ["build_payment_required", "build_payment_required_for_plans"]


def build_payment_required(
    plan_id: str,
    endpoint: Optional[str] = None,
    agent_id: Optional[str] = None,
    http_verb: Optional[str] = None,
    network: str = "eip155:84532",
    description: Optional[str] = None,
) -> X402PaymentRequired:
    """
    Build an X402PaymentRequired object for verify/settle operations.

    This helper simplifies the creation of payment requirement objects
    that are needed for the facilitator API.

    Args:
        plan_id: The Nevermined plan identifier (required)
        endpoint: The protected resource URL (optional)
        agent_id: The AI agent identifier (optional)
        http_verb: The HTTP method for the endpoint (optional)
        network: The blockchain network in CAIP-2 format (default: "eip155:84532" for Base Sepolia)
        description: Human-readable description of the resource (optional)

    Returns:
        X402PaymentRequired object ready to use with verify_permissions/settle_permissions

    Example:
        ```python
        from payments_py.x402 import build_payment_required

        payment_required = build_payment_required(
            plan_id="123456789",
            endpoint="/api/v1/agents/task",
            agent_id="987654321",
            http_verb="POST"
        )

        result = payments.facilitator.verify_permissions(
            payment_required=payment_required,
            x402_access_token=token,
            max_amount="2"
        )
        ```
    """
    # Build extra fields if any are provided
    extra = None
    if agent_id or http_verb:
        extra = X402SchemeExtra(
            agent_id=agent_id,
            http_verb=http_verb,
        )

    return X402PaymentRequired(
        x402_version=2,
        resource=X402Resource(
            url=endpoint or "",
            description=description,
        ),
        accepts=[
            X402Scheme(
                scheme="nvm:erc4337",
                network=network,
                plan_id=plan_id,
                extra=extra,
            )
        ],
        extensions={},
    )


def build_payment_required_for_plans(
    plan_ids: list[str],
    endpoint: Optional[str] = None,
    agent_id: Optional[str] = None,
    http_verb: Optional[str] = None,
    network: str = "eip155:84532",
    description: Optional[str] = None,
) -> X402PaymentRequired:
    """Build X402PaymentRequired with one or more plan_ids in the accepts array.

    For a single plan, delegates to :func:`build_payment_required`.
    For multiple plans, constructs the accepts array with one entry per plan.

    Args:
        plan_ids: List of Nevermined plan identifiers (at least one required)
        endpoint: The protected resource URL (optional)
        agent_id: The AI agent identifier (optional)
        http_verb: The HTTP method for the endpoint (optional)
        network: The blockchain network in CAIP-2 format (default: "eip155:84532" for Base Sepolia)
        description: Human-readable description of the resource (optional)

    Returns:
        X402PaymentRequired object ready to use with verify_permissions/settle_permissions
    """
    if len(plan_ids) == 1:
        return build_payment_required(
            plan_id=plan_ids[0],
            endpoint=endpoint,
            agent_id=agent_id,
            http_verb=http_verb,
            network=network,
            description=description,
        )

    extra = None
    if agent_id or http_verb:
        extra = X402SchemeExtra(agent_id=agent_id, http_verb=http_verb)

    schemes = [
        X402Scheme(
            scheme="nvm:erc4337",
            network=network,
            plan_id=pid,
            extra=extra,
        )
        for pid in plan_ids
    ]

    return X402PaymentRequired(
        x402_version=2,
        resource=X402Resource(url=endpoint or "", description=description),
        accepts=schemes,
        extensions={},
    )
