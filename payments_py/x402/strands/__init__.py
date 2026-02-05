"""
Strands agent tool decorator for Nevermined payment protection using the x402 protocol.

This module provides a decorator to protect Strands agent tools with
Nevermined payment verification and settlement following the x402 protocol.

Example usage:
    ```python
    from strands import tool, Agent
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.strands import requires_payment, PaymentContext

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="sandbox")
    )

    @tool
    @requires_payment(payments=payments, plan_id="plan-123", credits=1)
    def analyze_data(query: str, tool_context=None) -> dict:
        \"\"\"Analyze data with payment protection.

        Args:
            query: The analysis query
        \"\"\"
        return {"status": "success", "content": [{"text": f"Analysis: {query}"}]}

    # Create agent with payment-protected tools
    agent = Agent(tools=[analyze_data])

    # Invoke with payment token via invocation_state
    result = agent("Analyze sales data", payment_token="x402-access-token")
    ```

For full documentation, see the decorator module.
"""

from payments_py.x402.types import PaymentContext
from .decorator import (
    requires_payment,
    extract_payment_required,
    CreditsCallable,
)

__all__ = [
    "requires_payment",
    "extract_payment_required",
    "PaymentContext",
    "CreditsCallable",
]
