"""In-band x402 v2 payment helpers for the A2A transport.

Implements the client/server signalling defined by the Coinbase x402 v2 A2A
transport spec:
https://github.com/coinbase/x402/blob/main/specs/transports-v2/a2a.md

The flow these helpers support:

* **Payment required** (server -> client): a ``Task`` with
  ``status.state = "input-required"`` whose ``status.message.metadata`` carries
  ``x402.payment.status = "payment-required"`` and the ``X402PaymentRequired``
  object under ``x402.payment.required``.
* **Payment payload** (client -> server): a follow-up ``message/send`` whose
  ``message.metadata`` carries ``x402.payment.status = "payment-submitted"`` and
  the ``PaymentPayload`` object under ``x402.payment.payload``.
* **Settlement** (server -> client): a final ``Task`` whose
  ``status.message.metadata`` carries ``x402.payment.status =
  "payment-completed"`` and the ``SettleResponse`` receipt(s) under
  ``x402.payment.receipts`` (or ``payment-failed`` + ``x402.payment.error`` on
  failure).

The Nevermined facilitator's ``verify_permissions`` / ``settle_permissions``
consume the **base64 access token**, while the in-band payload travels as the
decoded ``PaymentPayload`` object. :func:`extract_inband_token` reconciles the
two by re-encoding the in-band payload back into the base64 token with
:func:`payments_py.x402.token.encode_access_token` (the same approach the MCP
in-band transport uses — the EIP-712 signature lives *inside* ``payload``, not
over the base64 envelope, so the round-trip is byte-safe for the facilitator).
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from payments_py.x402.a2a import x402Metadata
from payments_py.x402.token import encode_access_token

logger = logging.getLogger(__name__)


def _message_metadata(message: Any) -> Optional[dict]:
    """Return the metadata dict of an A2A message (dict or pydantic), or None."""
    if message is None:
        return None
    if isinstance(message, dict):
        meta = message.get("metadata")
    else:
        meta = getattr(message, "metadata", None)
    return meta if isinstance(meta, dict) else None


def get_inband_payment_payload(message: Any) -> Optional[dict]:
    """Extract the raw in-band ``x402.payment.payload`` object from a message.

    Args:
        message: The incoming A2A message (pydantic model or plain dict).

    Returns:
        The ``PaymentPayload`` dict if present in ``message.metadata`` under the
        spec key, otherwise ``None``.
    """
    meta = _message_metadata(message)
    if not meta:
        return None
    payload = meta.get(x402Metadata.PAYLOAD_KEY)
    return payload if isinstance(payload, dict) else None


def extract_inband_token(message: Any) -> Optional[str]:
    """Re-encode the in-band ``PaymentPayload`` into a base64 access token.

    The facilitator's verify/settle APIs take the base64 ``x402_access_token``;
    the in-band transport carries the decoded ``PaymentPayload`` object instead.
    Re-encoding bridges the two without touching the EIP-712 signature (which is
    inside ``payload``, not over the envelope), mirroring the MCP in-band path.

    Args:
        message: The incoming A2A message carrying the in-band payload.

    Returns:
        The base64url-encoded access token, or ``None`` if no in-band payload is
        present (caller should then fall back to the deprecated header token).
    """
    payload = get_inband_payment_payload(message)
    if payload is None:
        return None
    try:
        return encode_access_token(payload)
    except Exception:  # noqa: BLE001
        logger.error(
            "Failed to encode in-band x402 payment payload into access token",
            exc_info=True,
        )
        return None


__all__ = [
    "get_inband_payment_payload",
    "extract_inband_token",
]
