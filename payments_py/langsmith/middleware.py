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
import importlib.metadata
import inspect
import logging
import posixpath
import re
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, Iterator, Optional, Tuple, Union

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from payments_py.langsmith.spans import (
    attach_metadata_safely,
    build_settle_metadata,
    build_verify_metadata,
    settlement_span,
    verify_span,
)
from payments_py.x402.helpers import build_payment_required
from payments_py.x402.resolve_scheme import resolve_network, resolve_scheme
from payments_py.x402.types import (
    CreditsCallable,
    PaymentContext,
    PaymentRequiredError,
    RouteConfig,
    X402PaymentRequired,
)

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

# x402 v2 HTTP transport header names.
X402_HEADERS = {
    "PAYMENT_SIGNATURE": "payment-signature",
    "PAYMENT_REQUIRED": "payment-required",
    "PAYMENT_RESPONSE": "payment-response",
}


def _extract_token(request: Request) -> Optional[str]:
    return request.headers.get(X402_HEADERS["PAYMENT_SIGNATURE"]) or None


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
        if all(
            seg.startswith(":")
            or (seg.startswith("{") and seg.endswith("}"))
            or seg == path_seg
            for seg, path_seg in zip(route_parts, path_parts)
        ):
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


def _normalise_path(raw_path: str) -> str:
    """Dot-normalise the request path so traversal-encoded URLs (e.g.
    ``/threads/abc/../abc/runs/wait``) cannot skip route matching by
    inflating the segment count. ``request.url.path`` comes from
    ``scope["path"]`` which Starlette/uvicorn (httptools) does NOT
    normalise by default; this is defense-in-depth against any future
    proxy that DOES normalise (CDN, nginx, Cloud Run / Lambda gateway)
    where the request reaching the agent would have fewer segments
    than what the middleware sees. Trailing slash is preserved so
    ``/runs/`` stays distinct from ``/runs``.
    """
    normalised = posixpath.normpath(raw_path)
    if raw_path.endswith("/") and not normalised.endswith("/"):
        normalised += "/"
    return normalised


def _send_payment_required(
    payment_required: X402PaymentRequired, message: str
) -> JSONResponse:
    envelope_b64 = base64.b64encode(
        payment_required.model_dump_json(by_alias=True).encode()
    ).decode()
    return JSONResponse(
        status_code=402,
        content={"error": "Payment Required", "message": message},
        headers={
            X402_HEADERS["PAYMENT_REQUIRED"]: envelope_b64,
            # Receipt + envelope carry per-buyer financial metadata
            # (remaining_balance, payer wallet); prevent any CDN in front
            # of LangSmith Deployment from caching them across buyers.
            "Cache-Control": "no-store",
            "Pragma": "no-cache",
        },
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
        self.routes: Dict[str, RouteConfig] = {
            key: (value if isinstance(value, RouteConfig) else RouteConfig(**value))
            for key, value in (routes or {}).items()
        }

    def _resolve_route_config(self, method: str, path: str) -> Optional[RouteConfig]:
        return _match_route(method, path, self.routes)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        method = request.method.upper()
        path = _normalise_path(request.url.path)

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
            # Use the normalised path so the envelope reflects the canonical
            # resource the middleware actually matched against.
            endpoint=path,
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
                # failures raise PaymentRequiredError from inside the span so
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
                        attach_metadata_safely(
                            verify_run,
                            parent_rt,
                            build_verify_metadata,
                            "verify",
                            plan_ids=plan_ids,
                            scheme=resolved_scheme,
                            network=resolved_network,
                            agent_id=route_config.agent_id,
                        )
                        raise PaymentRequiredError(
                            f"Missing x402 payment token. Send token in {X402_HEADERS['PAYMENT_SIGNATURE']} header.",
                            payment_required=payment_required,
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
                    except PaymentRequiredError:
                        raise
                    except Exception as error:
                        logger.error(
                            "x402 verify failed for plan_id=%s: %s",
                            route_config.plan_id,
                            error,
                        )
                        attach_metadata_safely(
                            verify_run,
                            parent_rt,
                            build_verify_metadata,
                            "verify",
                            plan_ids=plan_ids,
                            scheme=resolved_scheme,
                            network=resolved_network,
                            agent_id=route_config.agent_id,
                            token=token,
                        )
                        raise PaymentRequiredError(
                            str(error) or "Payment verification failed",
                            payment_required=payment_required,
                        )

                    verify_duration_ms = (time.monotonic() - verify_start) * 1000
                    attach_metadata_safely(
                        verify_run,
                        parent_rt,
                        build_verify_metadata,
                        "verify",
                        plan_ids=plan_ids,
                        scheme=resolved_scheme,
                        network=resolved_network,
                        agent_id=route_config.agent_id,
                        verification=(verification if verification.is_valid else None),
                        duration_ms=verify_duration_ms,
                        token=token,
                    )

                    if not verification.is_valid:
                        raise PaymentRequiredError(
                            verification.invalid_reason
                            or "Insufficient credits or invalid token",
                            payment_required=payment_required,
                        )

                request.state.payment_context = PaymentContext(
                    token=token,
                    payment_required=payment_required,
                    credits_to_settle=credits_to_charge,
                    verified=True,
                    agent_request_id=verification.agent_request_id,
                    agent_request=verification.agent_request,
                )

                # Strip payment-signature before call_next so the bearer
                # token does not leak to downstream observability layers
                # that auto-capture request headers (Sentry's
                # RequestIntegration, OpenTelemetry HTTP semconv,
                # structlog ASGI processors). Their default denylists
                # cover Authorization / Cookie but NOT payment-signature.
                # The token already lives on request.state.payment_context
                # for any handler that needs it.
                mutable_request_headers = MutableHeaders(scope=request.scope)
                if X402_HEADERS["PAYMENT_SIGNATURE"] in mutable_request_headers:
                    del mutable_request_headers[X402_HEADERS["PAYMENT_SIGNATURE"]]

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
                        attach_metadata_safely(
                            settle_run,
                            parent_rt,
                            build_settle_metadata,
                            "settle",
                            settlement=settlement,
                            plan_ids=plan_ids,
                            agent_id=route_config.agent_id,
                            duration_ms=settle_duration_ms,
                            token=token,
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

                receipt_b64 = base64.b64encode(
                    settlement.model_dump_json(by_alias=True).encode()
                ).decode()

                # Warn loudly if the downstream response looks like SSE -
                # the buffering loop below collapses streaming into a
                # single delivered-at-the-end response and pins the body
                # in worker memory. Documented in the module docstring but
                # silent in logs without this signal.
                if "text/event-stream" in response.headers.get("content-type", ""):
                    logger.warning(
                        "PaymentMiddleware is buffering a text/event-stream response "
                        "for path=%s. Streaming is disabled by this middleware - "
                        "gate /runs/wait instead, or omit this route from the "
                        "middleware's routes dict to let it pass through ungated.",
                        path,
                    )

                body = b""
                async for chunk in response.body_iterator:
                    body += chunk

                new_response = Response(
                    content=body,
                    status_code=response.status_code,
                    media_type=response.media_type,
                )
                # Preserve multi-value headers from the original response
                # via MutableHeaders.append (dict(response.headers) silently
                # keeps only the first value of repeated keys like
                # Set-Cookie). Skip content-length / transfer-encoding so
                # the Response constructor's freshly recomputed
                # content-length stays in place and we drop chunked
                # encoding we no longer use.
                new_headers = new_response.headers
                for key, value in response.headers.items():
                    if key.lower() in ("content-length", "transfer-encoding"):
                        continue
                    new_headers.append(key, value)
                new_headers.append(X402_HEADERS["PAYMENT_RESPONSE"], receipt_b64)
                # Force no-store so any CDN in front of LangSmith
                # Deployment cannot cache a buyer's settlement receipt
                # (remaining_balance + payer wallet) and serve it to a
                # later requester.
                new_headers["Cache-Control"] = "no-store"
                new_headers["Pragma"] = "no-cache"
                return new_response
        except PaymentRequiredError as rejection:
            # Verify span + parent trace both saw the exception and are
            # marked failed in LangSmith. Convert to a 402 response.
            return _send_payment_required(payment_required, rejection.message)


# langgraph-api version that fixed the OpenAPI-docstring crash on non-FastAPI
# http.app wrappers. In <0.6.15, ``SchemaGenerator.get_schema`` caught only
# ``AssertionError`` around ``parse_docstring``, so a YAML ``ScannerError`` from
# an internal endpoint docstring with an unsafe colon propagated and crashed
# startup. 0.6.15 broadened the catch to ``except Exception`` (degrades to a
# plain description + a logged warning), so a plain Starlette ``http.app`` boots
# cleanly. Empirically bisected (0.6.14 crashes, 0.6.15 boots) and verified
# end-to-end on 0.8.7 — see nevermined-io/nvm-monorepo#1762.
_LANGGRAPH_API_DOCSTRING_FIX: Tuple[int, int, int] = (0, 6, 15)


def _langgraph_api_version() -> Optional[Tuple[int, ...]]:
    """Return the installed ``langgraph-api`` version as an int tuple, or None.

    Best-effort and fully defensive: returns ``None`` if the package is absent
    or the version string can't be parsed (e.g. an exotic pre-release). Only the
    leading integer of each of the first three dot components is used, so
    ``"0.6.15"`` → ``(0, 6, 15)`` and ``"0.6.15rc1"`` → ``(0, 6, 15)``.
    """
    try:
        raw = importlib.metadata.version("langgraph-api")
        parts = []
        for component in raw.split(".")[:3]:
            match = re.match(r"\d+", component)
            parts.append(int(match.group()) if match else 0)
        return tuple(parts)
    except Exception:
        return None


def build_payment_app(
    payments: Any,
    routes: Optional[Dict[str, Union[RouteConfig, dict]]] = None,
) -> Any:
    """Build a FastAPI app pre-wired with PaymentMiddleware for LangSmith Deployment.

    Convenience factory. The returned FastAPI instance is intended to be mounted
    via the ``http.app`` field of ``langgraph.json``.

    Not required on ``langgraph-api >= 0.6.15``. ``langgraph-api`` 0.5.x–0.6.14
    crashed on plain Starlette ``http.app`` wrappers because its
    ``update_openapi_spec`` fell through to Starlette's ``SchemaGenerator``,
    which YAML-parses every endpoint docstring; internal endpoint docstrings with
    YAML-unsafe colons tripped the parser, and ``get_schema`` only caught
    ``AssertionError`` — so the ``ScannerError`` crashed startup. FastAPI dodged
    this via ``app.openapi()``. 0.6.15 broadened that catch to
    ``except Exception`` (the bad docstring degrades to a plain description and a
    logged warning), so a **plain Starlette** ``http.app`` now boots cleanly:

        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from payments_py.langsmith import PaymentMiddleware, RouteConfig

        app = Starlette(middleware=[
            Middleware(PaymentMiddleware, payments=payments, routes={...}),
        ])

    On ``langgraph-api >= 0.6.15`` this factory emits a ``DeprecationWarning``
    pointing at the plain-Starlette form above. It remains useful on older
    ``langgraph-api`` (where the FastAPI wrapper is still load-bearing). The
    middleware class itself (``PaymentMiddleware``) is a Starlette
    ``BaseHTTPMiddleware`` subclass and works on both Starlette and FastAPI —
    only the outer app wrapper ever mattered for the upstream bug.

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
    detected = _langgraph_api_version()
    if detected is not None and detected >= _LANGGRAPH_API_DOCSTRING_FIX:
        fix = ".".join(str(p) for p in _LANGGRAPH_API_DOCSTRING_FIX)
        warnings.warn(
            f"build_payment_app's FastAPI wrapper is no longer required on "
            f"langgraph-api >= {fix} (detected "
            f"{'.'.join(str(p) for p in detected)}). Mount PaymentMiddleware "
            f"directly on a plain Starlette http.app instead: "
            f"app.add_middleware(PaymentMiddleware, payments=..., routes=...).",
            DeprecationWarning,
            stacklevel=2,
        )
    app = FastAPI()
    app.add_middleware(PaymentMiddleware, payments=payments, routes=routes or {})
    return app
