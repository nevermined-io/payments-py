"""
Custom error class for the Nevermined Payments protocol.
"""


class PaymentsError(Exception):
    """
    Custom exception for Nevermined Payments protocol errors.

    Args:
        message (str): The error message.
        code (str): The error code (e.g., 'unauthorized', 'payment_required')
    """

    def __init__(self, message: str, code: str = "payments_error"):
        super().__init__(message)
        self.name = "PaymentsError"
        self.code = code

    @classmethod
    def unauthorized(cls, message: str = "Unauthorized"):
        return cls(message, "unauthorized")

    @classmethod
    def payment_required(cls, message: str = "Payment required"):
        return cls(message, "payment_required")

    @classmethod
    def validation(cls, message: str = "Validation error"):
        return cls(message, "validation")

    @classmethod
    def internal(cls, message: str = "Internal error"):
        return cls(message, "internal")

    @classmethod
    def from_backend(cls, message: str, error: dict):
        backend_message = error.get("message", str(error))
        code = error.get("code", "payments_error")
        return cls(f"{message}. {backend_message}", code)

    @classmethod
    def from_response(cls, response, fallback_message: str) -> "PaymentsError":
        """Build a PaymentsError from an HTTP error response, preserving the
        backend's structured envelope.

        The Nevermined backend wraps errors in an NVMException envelope:
        ``{code, message, httpStatus, hint, details, ...}``. This helper
        promotes the canonical ``code`` (e.g. ``'BCK.VISA.0014'``) onto the
        exception so callers can branch programmatically, and appends
        ``hint`` and ``details`` to the message so corrective actions and
        per-field validation breakdowns surface to the developer.

        Falls back to ``http_<status>`` and the supplied ``fallback_message``
        when the body isn't JSON or doesn't follow the NVMException shape.

        If ``response`` is ``None`` or doesn't expose ``status_code`` (e.g.
        a refactor wired in an unrelated object), returns a minimal
        PaymentsError rather than raising — the original error path is
        already inside a failure handler, masking it would be worse.
        """
        if response is None or not hasattr(response, "status_code"):
            return cls(fallback_message, "payments_error")

        error_message = fallback_message
        error_code = f"http_{response.status_code}"
        # Narrow catch: ``.json()`` raises ``ValueError`` (JSONDecodeError
        # subclasses it) on non-JSON bodies, and ``AttributeError`` if a
        # mocked/duck-typed response is missing ``.json``. Anything else
        # (e.g. an unexpected library error) should propagate so we don't
        # mask genuinely surprising failures.
        try:
            body = response.json()
        except (ValueError, AttributeError):
            body = None
        if isinstance(body, dict):
            if body.get("message"):
                error_message = body["message"]
            if body.get("code"):
                error_code = body["code"]
            if body.get("hint"):
                error_message = f"{error_message} — {body['hint']}"
            if body.get("details"):
                error_message = f"{error_message} ({body['details']})"
        return cls(f"{error_message} (HTTP {response.status_code})", error_code)
