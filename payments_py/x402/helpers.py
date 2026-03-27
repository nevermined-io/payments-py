"""
X402 Helper Functions.

Utility functions for building x402 payment protocol objects.
"""

from typing import Optional

from .schemes import get_default_network
from .types import X402PaymentRequired, X402Resource, X402Scheme, X402SchemeExtra

__all__ = ["build_payment_required", "build_payment_required_for_plans"]


def build_payment_required(
    plan_id: str,
    endpoint: Optional[str] = None,
    agent_id: Optional[str] = None,
    http_verb: Optional[str] = None,
    network: Optional[str] = None,
    description: Optional[str] = None,
    mime_type: Optional[str] = None,
    scheme: str = "nvm:erc4337",
    environment: Optional[str] = None,
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
        network: The network identifier. Auto-derived from scheme/environment if None.
        description: Human-readable description of the resource (optional)
        mime_type: Expected response MIME type (e.g., "application/json") (optional)
        scheme: The x402 payment scheme (default: "nvm:erc4337")
        environment: The Nevermined environment name (e.g. "sandbox", "live").
            Used to auto-derive the correct network when ``network`` is not provided.

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
    # Auto-derive network from scheme/environment if not provided
    resolved_network = network or get_default_network(scheme, environment)

    # Build extra fields — always include version for scheme versioning
    extra = X402SchemeExtra(
        version="1",
        agent_id=agent_id,
        http_verb=http_verb,
    )

    return X402PaymentRequired(
        x402_version=2,
        resource=X402Resource(
            url=endpoint or "",
            description=description,
            mime_type=mime_type,
        ),
        accepts=[
            X402Scheme(
                scheme=scheme,
                network=resolved_network,
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
    network: Optional[str] = None,
    description: Optional[str] = None,
    scheme: str = "nvm:erc4337",
    environment: Optional[str] = None,
) -> X402PaymentRequired:
    """Build X402PaymentRequired with one or more plan_ids in the accepts array.

    For a single plan, delegates to :func:`build_payment_required`.
    For multiple plans, constructs the accepts array with one entry per plan.

    Args:
        plan_ids: List of Nevermined plan identifiers (at least one required)
        endpoint: The protected resource URL (optional)
        agent_id: The AI agent identifier (optional)
        http_verb: The HTTP method for the endpoint (optional)
        network: The network identifier. Auto-derived from scheme/environment if None.
        description: Human-readable description of the resource (optional)
        scheme: The x402 payment scheme (default: "nvm:erc4337")
        environment: The Nevermined environment name (e.g. "sandbox", "live").
            Used to auto-derive the correct network when ``network`` is not provided.

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
            scheme=scheme,
            environment=environment,
        )

    # Auto-derive network from scheme/environment if not provided
    resolved_network = network or get_default_network(scheme, environment)

    extra = X402SchemeExtra(version="1", agent_id=agent_id, http_verb=http_verb)

    schemes = [
        X402Scheme(
            scheme=scheme,
            network=resolved_network,
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
