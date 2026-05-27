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

import asyncio
import base64
import contextlib
import inspect
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional, Union

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from payments_py.langsmith.spans import (
    add_metadata,
    build_settle_metadata,
    build_verify_metadata,
    settlement_span,
    verify_span,
)
from payments_py.x402.helpers import build_payment_required
from payments_py.x402.resolve_scheme import resolve_network, resolve_scheme
from payments_py.x402.types import PaymentContext, X402PaymentRequired

# LangSmith is a dep of the [langsmith] extra. The sentinel handles the
# (unusual) case where this module is imported via a different extra and
# langsmith isn't present - the parent trace becomes a no-op.
try:
    import langsmith as _ls

    _LANGSMITH_AVAILABLE = True
except ImportError:  # pragma: no cover
    _ls = None  # type: ignore[assignment]
    _LANGSMITH_AVAILABLE = False

logger = logging.getLogger("payments_py.langsmith.middleware")

CreditsCallable = Callable[[Request], Union[int, Awaitable[int]]]

# x402 v2 HTTP transport header names.
X402_HEADERS = {
    "PAYMENT_SIGNATURE": "payment-signature",
    "PAYMENT_REQUIRED": "payment-required",
    "PAYMENT_RESPONSE": "payment-response",
}


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


async def _resolve_credits(
    credits: Union[int, CreditsCallable], request: Request
) -> int:
    if isinstance(credits, int):
        return credits
    result = credits(request)
    if inspect.isawaitable(result):
        return await result
    return result


@contextmanager
def _x402_parent_trace(method: str, path: str, plan_id: str) -> Iterator[Optional[Any]]:
    """Open a top-level LangSmith trace for the x402 lifecycle.

    Yields the underlying RunTree if LangSmith is available and tracing is
    configured, else None. Trace setup errors are swallowed so they cannot
    break the payment flow. Mirrors the ExitStack pattern in
    payments_py.langsmith.spans._open_nvm_span.

    The graph's own trace (emitted by the langgraph runtime when
    LANGSMITH_TRACING is enabled) does NOT nest under this parent - the
    langgraph-api layer initiates its own top-level trace at the
    graph-invocation boundary. They appear as sibling top-level traces.
    """
    if not _LANGSMITH_AVAILABLE:
        yield None
        return
    with contextlib.ExitStack() as stack:
        try:
            parent = stack.enter_context(
                _ls.trace(  # type: ignore[union-attr]
                    name="nvm:x402-request",
                    run_type="chain",
                    inputs={"method": method, "path": path, "plan_id": plan_id},
                )
            )
        except Exception:
            logger.debug(
                "nvm:x402-request parent trace setup failed (ignored)",
                exc_info=True,
            )
            yield None
            return
        yield parent


def _attach_to_span_and_parent(
    span_run: Optional[Any], parent_run: Optional[Any], metadata: dict
) -> None:
    """Attach the same metadata dict to both the nvm child span and the parent trace."""
    add_metadata(span_run, metadata)
    add_metadata(parent_run, metadata)


class _X402Rejection(Exception):
    """Internal control-flow exception raised inside verify_span when payment
    verification doesn't pass, so the span (and its parent trace) propagate
    failed status to LangSmith via the canonical context-manager __exit__
    path. Always caught at the dispatch level and converted to a 402 response.

    Without this, returning from inside the with block exits the span normally
    and LangSmith records the run as success even though the buyer got a 402.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


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
       parameterized match). If no route matches, the request passes
       through ungated.
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

    def _resolve_route_config(self, method: str, path: str) -> Optional[RouteConfig]:
        return _match_route(method, path, self.routes)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method.upper()
        path = request.url.path

        route_config = self._resolve_route_config(method, path)
        if not route_config:
            return await call_next(request)

        # resolve_scheme + resolve_network hit `payments.plans.get_plan`
        # internally (sync HTTP). Run them in a thread so we don't block the
        # event loop - langgraph dev's blocking-call detector treats sync
        # I/O in the dispatch task as a fatal warning and the SDK's
        # except-Exception path silently falls back to defaults.
        resolved_scheme = await asyncio.to_thread(
            resolve_scheme, self.payments, route_config.plan_id, route_config.scheme
        )
        resolved_network = await asyncio.to_thread(
            resolve_network, self.payments, route_config.plan_id, route_config.network
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

        plan_ids = [route_config.plan_id]
        token = _extract_token(request)

        # Parent trace - opened around the full payment lifecycle. Verify
        # and settle child spans nest under it. The graph's own trace
        # (when LANGSMITH_TRACING is enabled) appears as a sibling.
        try:
            with _x402_parent_trace(method, path, route_config.plan_id) as parent_rt:
                # Verify phase - opened BEFORE the token check so failed
                # discovery probes (no token) still emit an identifiable
                # nvm:verify run with static nvm.* metadata. Verification
                # failures raise _X402Rejection from inside the span so
                # LangSmith marks the run as failed via the standard __exit__
                # propagation path; the exception is caught below the parent
                # trace and converted to a 402 response.
                verify_start = time.monotonic()
                with verify_span(
                    plan_ids=plan_ids,
                    scheme=resolved_scheme,
                    network=resolved_network,
                    agent_id=route_config.agent_id,
                ) as verify_run:
                    if not token:
                        _attach_to_span_and_parent(
                            verify_run,
                            parent_rt,
                            build_verify_metadata(
                                plan_ids=plan_ids,
                                scheme=resolved_scheme,
                                network=resolved_network,
                                agent_id=route_config.agent_id,
                            ),
                        )
                        raise _X402Rejection(
                            f"Missing x402 payment token. Send token in {X402_HEADERS['PAYMENT_SIGNATURE']} header."
                        )

                    try:
                        credits_to_charge = await _resolve_credits(
                            route_config.credits, request
                        )
                        verification = await asyncio.to_thread(
                            self.payments.facilitator.verify_permissions,
                            payment_required=payment_required,
                            x402_access_token=token,
                            max_amount=str(credits_to_charge),
                        )
                    except _X402Rejection:
                        raise
                    except Exception as error:
                        logger.error(
                            "x402 verify failed for plan_id=%s: %s",
                            route_config.plan_id,
                            error,
                        )
                        _attach_to_span_and_parent(
                            verify_run,
                            parent_rt,
                            build_verify_metadata(
                                plan_ids=plan_ids,
                                scheme=resolved_scheme,
                                network=resolved_network,
                                agent_id=route_config.agent_id,
                                token=token,
                            ),
                        )
                        raise _X402Rejection(
                            str(error) or "Payment verification failed"
                        )

                    verify_duration_ms = (time.monotonic() - verify_start) * 1000
                    _attach_to_span_and_parent(
                        verify_run,
                        parent_rt,
                        build_verify_metadata(
                            plan_ids=plan_ids,
                            scheme=resolved_scheme,
                            network=resolved_network,
                            agent_id=route_config.agent_id,
                            verification=(
                                verification if verification.is_valid else None
                            ),
                            duration_ms=verify_duration_ms,
                            token=token,
                        ),
                    )

                    if not verification.is_valid:
                        raise _X402Rejection(
                            verification.invalid_reason
                            or "Insufficient credits or invalid token"
                        )

                request.state.payment_context = PaymentContext(
                    token=token,
                    payment_required=payment_required,
                    credits_to_settle=credits_to_charge,
                    verified=True,
                    agent_request_id=verification.agent_request_id,
                    agent_request=verification.agent_request,
                )

                # Agent runs here. Exceptions propagate naturally - the buyer
                # is not charged for failed runs (we skip settle on non-2xx
                # below). The parent trace will also see the exception via
                # __exit__ and be marked failed in LangSmith.
                response = await call_next(request)

                if not 200 <= response.status_code < 300:
                    return response

                # Settle phase. Settlement failures raise from inside the
                # settle span (so LangSmith marks it failed) but are caught
                # IMMEDIATELY OUTSIDE the span - the parent trace stays
                # success because the buyer-visible outcome is still a 200
                # with value delivered.
                settle_start = time.monotonic()
                try:
                    with settlement_span(
                        plan_ids=plan_ids,
                        agent_id=route_config.agent_id,
                    ) as settle_run:
                        settlement = await asyncio.to_thread(
                            self.payments.facilitator.settle_permissions,
                            payment_required=payment_required,
                            x402_access_token=token,
                            max_amount=str(credits_to_charge),
                            agent_request_id=verification.agent_request_id,
                        )
                        settle_duration_ms = (time.monotonic() - settle_start) * 1000
                        _attach_to_span_and_parent(
                            settle_run,
                            parent_rt,
                            build_settle_metadata(
                                settlement=settlement,
                                plan_ids=plan_ids,
                                agent_id=route_config.agent_id,
                                duration_ms=settle_duration_ms,
                                token=token,
                            ),
                        )
                except Exception as settle_error:
                    # Settle span saw the exception in its __exit__ and is
                    # marked failed in LangSmith. Suppress here so the parent
                    # trace stays success - buyer received value at 200.
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
                new_response.headers[X402_HEADERS["PAYMENT_RESPONSE"]] = (
                    settlement_base64
                )
                return new_response
        except _X402Rejection as rejection:
            # Verify span + parent trace both saw the exception and are
            # marked failed in LangSmith. Convert to a 402 response.
            return _send_payment_required(payment_required, rejection.message)


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
        routes: Map of "METHOD /path" to RouteConfig (or dict). Routes
            that do not match an incoming request pass through ungated.

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
