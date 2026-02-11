"""
FastAPI middleware for Nevermined payment protection using the x402 protocol.

This middleware provides a simple way to protect FastAPI routes with
Nevermined payment verification and settlement.

## x402 HTTP Transport Headers

Following the x402 spec (https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md):

- **Client -> Server**: `payment-signature` header with base64-encoded token
- **Server -> Client (402)**: `payment-required` header with base64-encoded PaymentRequired
- **Server -> Client (success)**: `payment-response` header with settlement receipt

Example usage:
    ```python
    from fastapi import FastAPI, Request
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.fastapi import payment_middleware, X402_HEADERS

    app = FastAPI()
    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="sandbox")
    )

    # Protect routes with payment middleware
    app.add_middleware(
        PaymentMiddleware,
        payments=payments,
        routes={
            "POST /ask": {"plan_id": "123", "credits": 1},
            "POST /generate": {"plan_id": "123", "credits": 5},
        }
    )

    # Route handlers - no payment logic needed!
    @app.post("/ask")
    async def ask(request: Request):
        # Access payment context if needed
        payment_context = request.state.payment_context
        return {"answer": "..."}
    ```

Example client usage:
    ```python
    import httpx
    from payments_py.x402.fastapi import X402_HEADERS

    token = await payments.x402.get_x402_access_token(plan_id)

    response = httpx.post(
        "http://localhost:8000/ask",
        headers={
            "Content-Type": "application/json",
            X402_HEADERS["PAYMENT_SIGNATURE"]: token.access_token,
        },
        json={"query": "Hello!"},
    )
    ```
"""

import asyncio
import base64
import inspect
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from payments_py.x402.helpers import build_payment_required
from payments_py.x402.types import PaymentContext, VerifyResponse, X402PaymentRequired

# Type alias for dynamic credits function
# Can be sync or async, takes Request and returns int
CreditsCallable = Callable[[Request], Union[int, Awaitable[int]]]

# x402 HTTP Transport header names (v2 spec)
# @see https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md
X402_HEADERS = {
    # Client sends payment token in this header
    "PAYMENT_SIGNATURE": "payment-signature",
    # Server sends PaymentRequired in this header (base64-encoded)
    "PAYMENT_REQUIRED": "payment-required",
    # Server sends settlement receipt in this header (base64-encoded)
    "PAYMENT_RESPONSE": "payment-response",
}


@dataclass
class RouteConfig:
    """
    Configuration for a protected route.

    Example with fixed credits:
        RouteConfig(plan_id="123", credits=5)

    Example with dynamic credits:
        RouteConfig(
            plan_id="123",
            credits=lambda req: calculate_credits(req)
        )

    Example with async dynamic credits:
        async def calc_credits(request: Request) -> int:
            body = await request.json()
            return len(body.get("messages", [])) * 2

        RouteConfig(plan_id="123", credits=calc_credits)
    """

    # The Nevermined plan ID that protects this route
    plan_id: str
    # Number of credits to charge for this route (default: 1)
    # Can be a static int or a callable (sync/async) that takes Request and returns int
    credits: Union[int, CreditsCallable] = 1
    # Optional agent ID
    agent_id: Optional[str] = None
    # Network identifier (default: "eip155:84532" for Base Sepolia)
    network: str = "eip155:84532"


# Type for hook callbacks
BeforeVerifyHook = Callable[[Request, X402PaymentRequired], Awaitable[None]]
AfterVerifyHook = Callable[[Request, VerifyResponse], Awaitable[None]]
AfterSettleHook = Callable[[Request, int, Any], Awaitable[None]]
PaymentErrorHook = Callable[[Exception, Request], Awaitable[Optional[Response]]]


@dataclass
class PaymentMiddlewareOptions:
    """Options for the payment middleware."""

    # Header name(s) to check for the x402 access token
    # Default: "payment-signature" (x402 v2 compliant)
    token_header: Union[str, list] = field(
        default_factory=lambda: [X402_HEADERS["PAYMENT_SIGNATURE"]]
    )
    # Hook called before verification
    on_before_verify: Optional[BeforeVerifyHook] = None
    # Hook called after successful verification
    on_after_verify: Optional[AfterVerifyHook] = None
    # Hook called after successful settlement
    on_after_settle: Optional[AfterSettleHook] = None
    # Custom error handler for payment failures
    on_payment_error: Optional[PaymentErrorHook] = None


def _extract_token(request: Request, header_names: Union[str, list]) -> Optional[str]:
    """Extract the x402 access token from the request headers."""
    headers = [header_names] if isinstance(header_names, str) else header_names

    for header_name in headers:
        header_value = request.headers.get(header_name.lower())
        if header_value and isinstance(header_value, str):
            return header_value

    return None


def _match_route(
    method: str, path: str, routes: Dict[str, RouteConfig]
) -> Optional[RouteConfig]:
    """
    Match a request to a route config.
    Returns the config if found, None otherwise.
    """
    # Try exact match first: "POST /ask"
    exact_key = f"{method} {path}"
    if exact_key in routes:
        return routes[exact_key]

    # Try pattern matching with path parameters
    for route_key, config in routes.items():
        parts = route_key.split(" ", 1)
        if len(parts) != 2:
            continue

        route_method, route_path = parts
        if route_method != method:
            continue

        # Simple pattern matching: /users/:id -> /users/123
        route_parts = route_path.split("/")
        path_parts = path.split("/")

        if len(route_parts) != len(path_parts):
            continue

        match = True
        for i in range(len(route_parts)):
            if route_parts[i].startswith(":"):
                continue  # Parameter - always matches
            if route_parts[i] != path_parts[i]:
                match = False
                break

        if match:
            return config

    return None


async def _resolve_credits(
    credits: Union[int, CreditsCallable], request: Request
) -> int:
    """
    Resolve credits value - handles both static int and callable (sync/async).
    """
    if isinstance(credits, int):
        return credits

    # It's a callable - check if it's async or sync
    result = credits(request)
    if inspect.isawaitable(result):
        return await result
    return result


def _send_payment_required(
    payment_required: X402PaymentRequired, message: str
) -> JSONResponse:
    """Helper to send a 402 Payment Required response with proper x402 headers."""
    # Base64 encode the PaymentRequired object for the header (per x402 spec)
    payment_required_json = payment_required.model_dump_json(by_alias=True)
    payment_required_base64 = base64.b64encode(payment_required_json.encode()).decode()

    return JSONResponse(
        status_code=402,
        content={"error": "Payment Required", "message": message},
        headers={X402_HEADERS["PAYMENT_REQUIRED"]: payment_required_base64},
    )


class PaymentMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware that protects routes with Nevermined payments.

    The middleware:
    1. Checks if the request matches a protected route
    2. Extracts the x402 token from headers
    3. Verifies the subscriber has sufficient credits
    4. Lets the route handler execute
    5. Settles (burns) the credits after successful response
    """

    def __init__(
        self,
        app: Any,
        payments: Any,  # Payments instance
        routes: Dict[str, Union[RouteConfig, dict]],
        options: Optional[PaymentMiddlewareOptions] = None,
    ):
        super().__init__(app)
        self.payments = payments
        # Convert dict configs to RouteConfig objects
        self.routes: Dict[str, RouteConfig] = {}
        for key, value in routes.items():
            if isinstance(value, RouteConfig):
                self.routes[key] = value
            else:
                self.routes[key] = RouteConfig(**value)
        self.options = options or PaymentMiddlewareOptions()

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process the request through the payment middleware."""
        # Check if this route requires payment
        method = request.method.upper()
        path = request.url.path

        route_config = _match_route(method, path, self.routes)
        if not route_config:
            # Route not protected - pass through
            return await call_next(request)

        # Build payment required object
        payment_required = build_payment_required(
            plan_id=route_config.plan_id,
            endpoint=str(request.url.path),
            agent_id=route_config.agent_id,
            http_verb=method,
            network=route_config.network,
        )

        # Extract token from headers
        token = _extract_token(request, self.options.token_header)
        if not token:
            error = Exception("Payment required: missing x402 access token")
            if self.options.on_payment_error:
                custom_response = await self.options.on_payment_error(error, request)
                if custom_response:
                    return custom_response
            return _send_payment_required(
                payment_required,
                f"Missing x402 payment token. Send token in {X402_HEADERS['PAYMENT_SIGNATURE']} header.",
            )

        try:
            # Calculate credits (supports both static and dynamic)
            credits_to_charge = await _resolve_credits(route_config.credits, request)

            # Hook: before verification
            if self.options.on_before_verify:
                await self.options.on_before_verify(request, payment_required)

            # Verify permissions
            verification = self.payments.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=token,
                max_amount=str(credits_to_charge),
            )

            if not verification.is_valid:
                error = Exception(
                    verification.invalid_reason or "Payment verification failed"
                )
                if self.options.on_payment_error:
                    custom_response = await self.options.on_payment_error(
                        error, request
                    )
                    if custom_response:
                        return custom_response
                return _send_payment_required(
                    payment_required,
                    verification.invalid_reason
                    or "Insufficient credits or invalid token",
                )

            # Hook: after verification
            if self.options.on_after_verify:
                await self.options.on_after_verify(request, verification)

            # Store payment context for settlement and route handler access
            payment_context = PaymentContext(
                token=token,
                payment_required=payment_required,
                credits_to_settle=credits_to_charge,
                verified=True,
                agent_request_id=verification.agent_request_id,
                agent_request=verification.agent_request,
            )
            request.state.payment_context = payment_context

            # Call the actual route handler
            response = await call_next(request)

            # Only settle if response is successful (2xx)
            if 200 <= response.status_code < 300:
                try:
                    # Settle credits (pass agentRequestId for observability updates)
                    settlement = self.payments.facilitator.settle_permissions(
                        payment_required=payment_required,
                        x402_access_token=token,
                        max_amount=str(credits_to_charge),
                        agent_request_id=payment_context.agent_request_id,
                    )

                    # Add settlement response header (base64-encoded per x402 spec)
                    settlement_json = settlement.model_dump_json(by_alias=True)
                    settlement_base64 = base64.b64encode(
                        settlement_json.encode()
                    ).decode()

                    # Create a new response with the header added
                    # We need to read the body and create a new response
                    body = b""
                    async for chunk in response.body_iterator:
                        body += chunk

                    new_response = Response(
                        content=body,
                        status_code=response.status_code,
                        headers=dict(response.headers),
                        media_type=response.media_type,
                    )
                    new_response.headers[X402_HEADERS["PAYMENT_RESPONSE"]] = (
                        settlement_base64
                    )

                    # Hook: after settlement
                    if self.options.on_after_settle:
                        await self.options.on_after_settle(
                            request, credits_to_charge, settlement
                        )

                    return new_response

                except Exception as settle_error:
                    # Log but don't fail the response if settlement fails
                    print(f"Payment settlement failed: {settle_error}")
                    return response

            return response

        except Exception as error:
            if self.options.on_payment_error:
                custom_response = await self.options.on_payment_error(error, request)
                if custom_response:
                    return custom_response
            return _send_payment_required(
                payment_required,
                str(error) if str(error) else "Payment verification failed",
            )


def payment_middleware(
    payments: Any,  # Payments instance
    routes: Dict[str, Union[RouteConfig, dict]],
    options: Optional[PaymentMiddlewareOptions] = None,
) -> Callable:
    """
    Create a FastAPI middleware factory function for payment protection.

    This is an alternative to directly using PaymentMiddleware with app.add_middleware().

    Example:
        ```python
        from payments_py.x402.fastapi import payment_middleware

        middleware = payment_middleware(
            payments,
            {
                "POST /ask": {"plan_id": "123", "credits": 1},
            }
        )

        # Use with Starlette/FastAPI
        app.add_middleware(middleware)
        ```

    Args:
        payments: The Payments instance
        routes: Map of routes to protect: {"METHOD /path": {"plan_id", "credits"}}
        options: Optional middleware configuration

    Returns:
        A middleware class that can be added to FastAPI
    """

    class ConfiguredPaymentMiddleware(PaymentMiddleware):
        def __init__(self, app: Any):
            super().__init__(app, payments=payments, routes=routes, options=options)

    return ConfiguredPaymentMiddleware
