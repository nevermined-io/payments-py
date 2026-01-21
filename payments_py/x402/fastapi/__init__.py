"""
FastAPI middleware for Nevermined payment protection using the x402 protocol.

This module provides FastAPI middleware for protecting routes with Nevermined
payment verification and settlement following the x402 HTTP transport spec.

Example usage:
    ```python
    from fastapi import FastAPI, Request
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.fastapi import PaymentMiddleware, X402_HEADERS

    app = FastAPI()
    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="sandbox")
    )

    # Add payment protection middleware
    app.add_middleware(
        PaymentMiddleware,
        payments=payments,
        routes={
            "POST /ask": {"plan_id": "123", "credits": 1},
        }
    )

    @app.post("/ask")
    async def ask(request: Request):
        # Access payment context if needed
        context = request.state.payment_context
        return {"answer": "...", "request_id": context.agent_request_id}
    ```

For full documentation, see the middleware module.
"""

from .middleware import (
    X402_HEADERS,
    RouteConfig,
    PaymentContext,
    PaymentMiddlewareOptions,
    PaymentMiddleware,
    payment_middleware,
)

__all__ = [
    "X402_HEADERS",
    "RouteConfig",
    "PaymentContext",
    "PaymentMiddlewareOptions",
    "PaymentMiddleware",
    "payment_middleware",
]
