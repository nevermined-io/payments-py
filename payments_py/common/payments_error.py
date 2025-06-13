"""
Custom error class for the Nevermined Payments protocol.
"""

class PaymentsError(Exception):
    """
    Custom exception for Nevermined Payments protocol errors.

    Args:
        message (str): The error message.
    """
    def __init__(self, message: str):
        super().__init__(message)
        self.name = "PaymentsError"