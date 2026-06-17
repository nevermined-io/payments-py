"""
Error utilities and common JSON-RPC error codes used by the MCP paywall.
"""

from typing import Any, Dict

ERROR_CODES: Dict[str, int] = {
    "Misconfiguration": -32002,
    "PaymentRequired": -32003,
}


def create_rpc_error(code: int, message: str, data: Any | None = None) -> Exception:
    """
    Create an Exception that mimics JSON-RPC error objects with code and optional data.

     Args:
         code: Numeric error code.
         message: Human-readable error message.
         data: Optional structured payload to attach to the error.

     Returns:
         Exception configured with additional ``code`` and ``data`` attributes.
    """
    err = Exception(message)
    setattr(err, "code", code)
    if data is not None:
        setattr(err, "data", data)
    return err


class PaymentRequiredError(Exception):
    """Raised by the paywall when payment is required (x402 v2 MCP transport).

    Carries the spec-shaped ``PaymentRequired`` dict so the tool dispatcher can
    surface it *in band* as a ``CallToolResult(isError=True, ...)``. It also sets
    a JSON-RPC ``code`` (``-32003``) for non-tool paths (resources / prompts /
    meta methods), which cannot return a tool result and instead let the
    exception propagate. Note: the MCP SDK's low-level ``Server`` catch-all wraps
    uncaught handler exceptions as ``ErrorData(code=0, message=str(err))`` and
    does NOT read ``err.code`` — so on those paths only the human-readable
    message reaches the wire; the ``-32003`` code is informational for callers
    that inspect the exception directly.

    Attributes:
        payment_required: The ``PaymentRequired`` object (plain dict).
        code: JSON-RPC error code (``-32003``).
    """

    def __init__(
        self, payment_required: Dict[str, Any], message: str = "Payment required"
    ) -> None:
        super().__init__(message)
        self.payment_required = payment_required
        self.code = ERROR_CODES["PaymentRequired"]


class SettlementFailedError(PaymentRequiredError):
    """Raised when settlement fails AFTER the tool has already executed.

    Same in-band shape as :class:`PaymentRequiredError`; the tool dispatcher
    suppresses the already-computed tool content and returns only the payment
    error, per the x402 v2 MCP transport spec ("do not return the tool's content
    if settlement fails").
    """
