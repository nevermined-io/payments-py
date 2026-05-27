"""LangSmith Deployment middleware for Nevermined x402 payment protection.

This module provides a Starlette-compatible ASGI middleware that wraps a
LangGraph agent deployed to LangSmith Deployment with the Nevermined x402
verify-then-work-then-settle payment lifecycle. The middleware reads the
payment-signature header before the agent runs, verifies it against the
Nevermined facilitator, lets the agent execute, and settles credits only
after a successful 2xx response. Buyers are not charged for failed runs.

Pair it with build_payment_app for the recommended single-line wiring, or
use PaymentMiddleware directly for custom Starlette or FastAPI apps.

x402 HTTP Transport Headers (v2 spec):

- Client to Server (request)        - payment-signature header carrying the
  base64-encoded x402 access token.
- Server to Client (402 response)   - payment-required header carrying the
  base64-encoded PaymentRequired envelope.
- Server to Client (success)        - payment-response header carrying the
  base64-encoded settlement receipt.

Known limitation - response body buffering. The middleware reads the
downstream response body in full before attaching the payment-response
settlement header. This negates streaming for endpoints like /runs/stream
or SSE responses (they become blocking-then-bulk). Use this middleware on
non-streaming endpoints, or omit it for paths where streaming matters
more than payment gating.
"""

import base64
import inspect
import logging
import os
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Optional, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from payments_py.x402.helpers import build_payment_required
from payments_py.x402.resolve_scheme import resolve_network, resolve_scheme
from payments_py.x402.types import PaymentContext, X402PaymentRequired

logger = logging.getLogger("payments_py.langsmith.middleware")

CreditsCallable = Callable[[Request], Union[int, Awaitable[int]]]

# x402 v2 HTTP transport header names.
X402_HEADERS = {
    "PAYMENT_SIGNATURE": "payment-signature",
    "PAYMENT_REQUIRED": "payment-required",
    "PAYMENT_RESPONSE": "payment-response",
}

# Env-var names that act as a single-plan fallback when no routes match.
ENV_PLAN_ID = "NVM_PLAN_ID"
ENV_CREDITS_PER_INVOKE = "NVM_CREDITS_PER_INVOKE"
ENV_AGENT_ID = "NVM_AGENT_ID"


@dataclass
class RouteConfig:
    """Configuration for a protected route under LangSmith Deployment.

    Copied from payments_py.x402.fastapi.RouteConfig so the two extras can
    evolve independently. Field semantics are identical.
    """

    plan_id: str
    credits: Union[int, CreditsCallable] = 1
    agent_id: Optional[str] = None
    network: Optional[str] = None
    scheme: Optional[str] = None
    description: Optional[str] = None
    mime_type: Optional[str] = None


def _extract_token(request: Request) -> Optional[str]:
    header_value = request.headers.get(X402_HEADERS["PAYMENT_SIGNATURE"])
    return header_value if header_value and isinstance(header_value, str) else None


def _match_route(
    method: str, path: str, routes: Dict[str, RouteConfig]
) -> Optional[RouteConfig]:
    """Match a request method+path against the configured routes.

    Supports exact matches ("POST /runs") and path parameters in either
    Starlette-style (":id") or FastAPI/LangGraph-style ("{thread_id}").
    """
    exact_key = f"{method} {path}"
    if exact_key in routes:
        return routes[exact_key]

    for route_key, config in routes.items():
        parts = route_key.split(" ", 1)
        if len(parts) != 2:
            continue
        route_method, route_path = parts
        if route_method != method:
            continue
        route_parts = route_path.split("/")
        path_parts = path.split("/")
        if len(route_parts) != len(path_parts):
            continue
        matches = True
        for i, segment in enumerate(route_parts):
            is_param = segment.startswith(":") or (
                segment.startswith("{") and segment.endswith("}")
            )
            if is_param:
                continue
            if segment != path_parts[i]:
                matches = False
                break
        if matches:
            return config
    return None


def _env_var_fallback() -> Optional[RouteConfig]:
    """Build a RouteConfig from env vars for single-plan deployments.

    Returns None if NVM_PLAN_ID is unset. NVM_CREDITS_PER_INVOKE defaults
    to 1 if missing or non-numeric. NVM_AGENT_ID is optional.
    """
    plan_id = os.environ.get(ENV_PLAN_ID)
    if not plan_id:
        return None
    credits_raw = os.environ.get(ENV_CREDITS_PER_INVOKE, "1")
    try:
        credits = int(credits_raw)
    except ValueError:
        logger.warning(
            "%s=%r is not an integer; defaulting to 1",
            ENV_CREDITS_PER_INVOKE,
            credits_raw,
        )
        credits = 1
    return RouteConfig(
        plan_id=plan_id,
        credits=credits,
        agent_id=os.environ.get(ENV_AGENT_ID),
    )


async def _resolve_credits(
    credits: Union[int, CreditsCallable], request: Request
) -> int:
    if isinstance(credits, int):
        return credits
    result = credits(request)
    if inspect.isawaitable(result):
        return await result
    return result


def _send_payment_required(
    payment_required: X402PaymentRequired, message: str
) -> JSONResponse:
    payment_required_json = payment_required.model_dump_json(by_alias=True)
    payment_required_base64 = base64.b64encode(payment_required_json.encode()).decode()
    return JSONResponse(
        status_code=402,
        content={"error": "Payment Required", "message": message},
        headers={X402_HEADERS["PAYMENT_REQUIRED"]: payment_required_base64},
    )


class PaymentMiddleware(BaseHTTPMiddleware):
    """Starlette middleware that gates a LangSmith Deployment agent with x402.

    Lifecycle for each request:

    1. Resolve a RouteConfig from the configured routes table (exact or
       parameterized match) or, failing that, from the env-var fallback.
       If neither resolves, the request passes through ungated.
    2. Build the x402 PaymentRequired envelope from the resolved config.
    3. Extract the payment-signature header. If missing, return 402 with the
       envelope in the payment-required response header.
    4. Verify the token via payments.facilitator.verify_permissions. On
       failure, return 402 with the envelope.
    5. Stash the PaymentContext on request.state and call_next - the agent
       runs here.
    6. If the response status is 2xx, settle via
       payments.facilitator.settle_permissions and attach the receipt to the
       payment-response response header. Non-2xx responses skip settlement
       so buyers are not charged for failed runs.
    7. Settlement failures after a successful agent response are logged at
       ERROR level but do not change the response - the buyer already got
       the value.
    """

    def __init__(
        self,
        app: Any,
        payments: Any,
        routes: Optional[Dict[str, Union[RouteConfig, dict]]] = None,
    ):
        super().__init__(app)
        self.payments = payments
        self.routes: Dict[str, RouteConfig] = {}
        for key, value in (routes or {}).items():
            self.routes[key] = (
                value if isinstance(value, RouteConfig) else RouteConfig(**value)
            )
        # Env-var fallback is for single-plan deployments where users want
        # to gate every path with one config without writing a routes dict.
        # When routes is non-empty, the user has explicitly opted into per-
        # route gating - the env vars must not act as a catch-all on
        # unmatched paths (would silently gate /threads, /assistants, etc.).
        self._env_fallback = _env_var_fallback() if not self.routes else None

    def _resolve_route_config(self, method: str, path: str) -> Optional[RouteConfig]:
        return _match_route(method, path, self.routes) or self._env_fallback

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method.upper()
        path = request.url.path

        route_config = self._resolve_route_config(method, path)
        if not route_config:
            return await call_next(request)

        resolved_scheme = resolve_scheme(
            self.payments, route_config.plan_id, route_config.scheme
        )
        resolved_network = resolve_network(
            self.payments, route_config.plan_id, route_config.network
        )

        payment_required = build_payment_required(
            plan_id=route_config.plan_id,
            endpoint=str(request.url.path),
            agent_id=route_config.agent_id,
            http_verb=method,
            network=resolved_network,
            description=route_config.description,
            mime_type=route_config.mime_type,
            scheme=resolved_scheme,
            environment=getattr(self.payments, "environment_name", None),
        )

        token = _extract_token(request)
        if not token:
            return _send_payment_required(
                payment_required,
                f"Missing x402 payment token. Send token in {X402_HEADERS['PAYMENT_SIGNATURE']} header.",
            )

        # Verify phase. Failures here are payment-level - return 402.
        # Agent failures (in call_next below) are deliberately NOT caught here
        # so they propagate to Starlette's exception handler as 5xx.
        try:
            credits_to_charge = await _resolve_credits(route_config.credits, request)

            verification = self.payments.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=token,
                max_amount=str(credits_to_charge),
            )
        except Exception as error:
            logger.error(
                "x402 verify failed for plan_id=%s: %s",
                route_config.plan_id,
                error,
            )
            return _send_payment_required(
                payment_required,
                str(error) or "Payment verification failed",
            )

        if not verification.is_valid:
            return _send_payment_required(
                payment_required,
                verification.invalid_reason or "Insufficient credits or invalid token",
            )

        request.state.payment_context = PaymentContext(
            token=token,
            payment_required=payment_required,
            credits_to_settle=credits_to_charge,
            verified=True,
            agent_request_id=verification.agent_request_id,
            agent_request=verification.agent_request,
        )

        # Agent runs here. Exceptions propagate naturally - the buyer is not
        # charged for failed runs (we skip settle on non-2xx below).
        response = await call_next(request)

        if not 200 <= response.status_code < 300:
            return response

        # Settle phase. Failures here are logged but do not surface to the
        # client - the buyer already received the value.
        try:
            settlement = self.payments.facilitator.settle_permissions(
                payment_required=payment_required,
                x402_access_token=token,
                max_amount=str(credits_to_charge),
                agent_request_id=verification.agent_request_id,
            )
        except Exception as settle_error:
            logger.error(
                "x402 settlement failed for plan_id=%s after 2xx response: %s",
                route_config.plan_id,
                settle_error,
            )
            return response

        settlement_json = settlement.model_dump_json(by_alias=True)
        settlement_base64 = base64.b64encode(settlement_json.encode()).decode()

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        new_response = Response(
            content=body,
            status_code=response.status_code,
            headers=dict(response.headers),
            media_type=response.media_type,
        )
        new_response.headers[X402_HEADERS["PAYMENT_RESPONSE"]] = settlement_base64
        return new_response


def build_payment_app(
    payments: Any,
    routes: Optional[Dict[str, Union[RouteConfig, dict]]] = None,
) -> Any:
    """Build a FastAPI app pre-wired with PaymentMiddleware for LangSmith Deployment.

    This is the recommended entry point. The returned FastAPI instance is
    intended to be mounted via the http.app field of langgraph.json. FastAPI
    is recommended over a plain Starlette app because langgraph-api 0.5.42
    has an OpenAPI generation bug that crashes the server on plain Starlette
    http.app wrappers - FastAPI takes a clean path through app.openapi().

    Args:
        payments: A configured payments_py.Payments instance.
        routes: Optional map of "METHOD /path" to RouteConfig (or dict).
            When empty, the middleware falls back to env vars (NVM_PLAN_ID,
            NVM_CREDITS_PER_INVOKE, NVM_AGENT_ID) for single-plan deployments.

    Returns:
        A FastAPI app instance with PaymentMiddleware applied globally.

    Example:
        # nvm_app.py
        from payments_py import Payments
        from payments_py.langsmith import build_payment_app, RouteConfig

        app = build_payment_app(
            payments=Payments(api_key=..., environment="staging"),
            routes={
                "POST /runs": RouteConfig(
                    plan_id="plan_...", credits=10, agent_id="agent_..."
                ),
            },
        )

        # langgraph.json
        # { "http": { "app": "./nvm_app.py:app" } }
    """
    from fastapi import FastAPI

    app = FastAPI()
    app.add_middleware(PaymentMiddleware, payments=payments, routes=routes or {})
    return app
