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
