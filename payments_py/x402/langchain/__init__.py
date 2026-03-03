"""
LangChain tool decorator for Nevermined payment protection using the x402 protocol.

This module provides a decorator to protect LangChain tools with
Nevermined payment verification and settlement following the x402 protocol.

Example usage::

    from langchain_core.tools import tool
    from langchain_core.runnables import RunnableConfig
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.langchain import requires_payment

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="sandbox")
    )

    @tool
    @requires_payment(payments=payments, plan_id="plan-123", credits=1)
    def analyze_data(query: str, config: RunnableConfig) -> str:
        \"\"\"Analyze data with payment protection.\"\"\"
        return f"Analysis: {query}"

    # Invoke with payment token via config
    result = analyze_data.invoke(
        {"query": "sales data"},
        config={"configurable": {"payment_token": "x402-token-here"}},
    )

For full documentation, see the decorator module.
"""

from payments_py.x402.types import PaymentContext
from .decorator import (
    requires_payment,
    PaymentRequiredError,
    CreditsCallable,
)

__all__ = [
    "requires_payment",
    "PaymentRequiredError",
    "PaymentContext",
    "CreditsCallable",
]
