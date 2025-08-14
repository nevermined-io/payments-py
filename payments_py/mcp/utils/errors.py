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
