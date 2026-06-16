"""
In-band x402 metadata helpers for the MCP transport (x402 v2 MCP spec).

The x402 v2 MCP transport signals payments *in band* via the MCP tool-call
machinery instead of HTTP status codes / headers:

- The client sends the ``PaymentPayload`` in the request params
  ``_meta["x402/payment"]`` (plain JSON).
- The server returns the settlement receipt in the response
  ``_meta["x402/payment-response"]`` (plain JSON).
- Payment-required is signalled as a tool result with ``isError = True`` whose
  ``structuredContent`` carries the ``PaymentRequired`` object and whose
  ``content[0].text`` is the JSON-stringified copy of it.

Nevermined-specific observability (txHash, creditsRedeemed, …) is kept under a
namespaced ``_meta["nevermined/credits"]`` key so it never collides with the
spec-defined keys.
"""

import json
from typing import Any, Dict, Optional

from mcp.types import CallToolResult, TextContent

# Spec-defined JSON-RPC _meta keys (x402 v2 MCP transport).
X402_PAYMENT_META_KEY = "x402/payment"
X402_PAYMENT_RESPONSE_META_KEY = "x402/payment-response"

# Nevermined-namespaced observability key (NOT part of the x402 spec).
NEVERMINED_CREDITS_META_KEY = "nevermined/credits"


def read_payment_payload(mcp_server: Any) -> Optional[Dict[str, Any]]:
    """Read the in-band x402 payment payload from the current request's ``_meta``.

    Returns the object the client placed in ``params._meta["x402/payment"]``,
    or ``None`` when there is no active request context or the key is absent.

    The MCP SDK exposes incoming request ``_meta`` as ``RequestParams.Meta``
    (configured with ``extra="allow"``), so non-standard keys land in
    ``model_extra``.

    Args:
        mcp_server: The low-level MCP ``Server`` instance (exposes
            ``request_context``).

    Returns:
        The decoded PaymentPayload dict, or ``None``.
    """
    try:
        meta = mcp_server.request_context.meta
    except LookupError:
        # Called outside of a request context.
        return None
    if meta is None:
        return None
    extra = getattr(meta, "model_extra", None) or {}
    value = extra.get(X402_PAYMENT_META_KEY)
    return value if isinstance(value, dict) else None


def payment_required_result(payment_required: Dict[str, Any]) -> CallToolResult:
    """Build a spec-shaped payment-required tool result.

    Per the x402 v2 MCP transport, payment-required is an *error* tool result
    that carries the ``PaymentRequired`` object in BOTH ``structuredContent``
    (the object) and ``content[0].text`` (the JSON-stringified copy, for
    clients that cannot read structured content).

    Args:
        payment_required: The ``PaymentRequired`` object (already a plain dict).

    Returns:
        A ``CallToolResult`` with ``isError = True``.
    """
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(payment_required))],
        structuredContent=payment_required,
        isError=True,
    )
