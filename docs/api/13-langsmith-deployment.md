# LangSmith Deployment Middleware

A Starlette ASGI middleware (`PaymentMiddleware`) that gates a LangGraph agent deployed to **LangSmith Deployment** (formerly LangGraph Platform) with the Nevermined x402 payment flow. Use the `build_payment_app` factory for one-line wiring via the `http.app` field in `langgraph.json`.

For tool-time gating inside an agent (`@requires_payment` decorator), see [chapter 12](./12-langchain-integration.md). The two integrations are complementary — chapter 12 is for protecting tools the agent calls; this chapter is for protecting the agent's HTTP entry point.

## Installation

```bash
pip install payments-py[langsmith]
```

The `[langsmith]` extra pulls `fastapi`, `starlette`, and `langsmith`.

## Exports

```python
from payments_py.langsmith import (
    PaymentMiddleware,       # Starlette BaseHTTPMiddleware subclass
    RouteConfig,             # dataclass for per-route pricing
    X402_HEADERS,            # dict of x402 v2 header names
    build_payment_app,       # FastAPI app factory (recommended)
)
```

## `build_payment_app`

The recommended entry point — returns a `FastAPI` app pre-wired with `PaymentMiddleware`. Mount the returned app in `langgraph.json`'s `http.app` field.

### Signature

```python
def build_payment_app(
    payments: Payments,
    routes: Optional[Dict[str, Union[RouteConfig, dict]]] = None,
) -> FastAPI: ...
```

### Why FastAPI and not plain Starlette

`langgraph-api` versions prior to a known internal OpenAPI fix crash on plain Starlette `http.app` wrappers — `update_openapi_spec` falls through to Starlette's `SchemaGenerator` which YAML-parses internal endpoint docstrings and chokes on them. `app.openapi()` (FastAPI's own generator) takes a clean path. `build_payment_app` returns a FastAPI app so users do not need to know about this upstream bug.

The middleware class itself (`PaymentMiddleware`) is a `starlette.middleware.base.BaseHTTPMiddleware` and works on both Starlette and FastAPI — only the outer app wrapper matters.

### Example

```python
# nvm_app.py
import os
from payments_py import Payments, PaymentOptions
from payments_py.langsmith import build_payment_app, RouteConfig

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key=os.environ["NVM_API_KEY"],
        environment=os.environ.get("NVM_ENVIRONMENT", "sandbox"),
    )
)

app = build_payment_app(
    payments=payments,
    routes={
        "POST /threads/{thread_id}/runs/wait": RouteConfig(
            plan_id=os.environ["NVM_PLAN_ID"],
            credits=int(os.environ.get("NVM_CREDITS_PER_INVOKE", "1")),
        ),
    },
)
```

```json
// langgraph.json
{
  "graphs": { "my_agent": "./src/agent.py:graph" },
  "http": { "app": "./nvm_app.py:app" },
  "env": ".env"
}
```

`langgraph dev` and `langgraph up` both honor the `http.app` field — the middleware composes around LangSmith Deployment's built-in routes (`/runs`, `/threads/{id}/runs`, `/assistants`, etc.).

## Lifecycle

The middleware implements the canonical x402 verify-then-work-then-settle ordering inside one HTTP cycle:

```
Request in
  ├─ PaymentMiddleware.dispatch:
  │     ├─ resolve scheme + network from plan metadata (cached)
  │     ├─ build the x402 PaymentRequired envelope
  │     ├─ read payment-signature header
  │     │     └─ missing → 402 + envelope in payment-required header
  │     ├─ facilitator.verify_permissions(...)
  │     │     └─ invalid → 402 + envelope in payment-required header
  │     ├─ stash PaymentContext on request.state
  │     ├─ await call_next(request)            ← agent runs
  │     ├─ if response is 2xx:
  │     │     ├─ facilitator.settle_permissions(...)
  │     │     ├─ on success → attach settlement receipt to payment-response header
  │     │     └─ on failure → log + return response unchanged at 200
  │     └─ else: skip settle (no charge for failed runs)
  │
Response out
```

Agent exceptions propagate naturally to the ASGI runtime as 5xx — buyers are not charged for failed runs. Settle failures after a successful 2xx response are logged at `ERROR` and do not surface to the client (the buyer already received the value).

## `RouteConfig`

Per-route pricing. Routes that don't match an incoming request pass through ungated.

### Fields

| Field | Type | Default | Purpose |
|---|---|---|---|
| `plan_id` | `str` | required | The Nevermined plan ID gating this route |
| `credits` | `int` or `Callable[[Request], int \| Awaitable[int]]` | `1` | Static or dynamic credits to charge |
| `agent_id` | `str \| None` | `None` | Optional — surfaces in the envelope and on `nvm.*` metadata for per-agent reconciliation |
| `network` | `str \| None` | `None` | Override the auto-resolved network |
| `scheme` | `str \| None` | `None` | Override the auto-resolved scheme |
| `description` | `str \| None` | `None` | Free-text description for the envelope |
| `mime_type` | `str \| None` | `None` | Expected response MIME type |

### Route matching

Routes are keyed as `"METHOD /path"`. Path parameters can use either Starlette `:param` or FastAPI/LangGraph `{param}` syntax — both match by position against the incoming request path. Examples that all match `POST /threads/abc-123/runs/wait`:

```python
"POST /threads/{thread_id}/runs/wait"
"POST /threads/:thread_id/runs/wait"
```

For LangSmith Deployment specifically, the only path that fits the verify-work-settle lifecycle in one HTTP cycle is `POST /threads/{thread_id}/runs/wait` (or its stateless counterpart `POST /runs/wait`). Background runs (`POST /runs`) return immediately; streaming runs (`POST /runs/stream`) lose streaming due to body buffering (see Limitations).

## `PaymentMiddleware` (direct use)

`build_payment_app` is the recommended entry point. If you need a custom Starlette or FastAPI app (e.g. additional middleware, custom routes), use `PaymentMiddleware` directly:

```python
from fastapi import FastAPI
from starlette.middleware import Middleware
from payments_py.langsmith import PaymentMiddleware, RouteConfig

app = FastAPI(
    middleware=[
        Middleware(
            PaymentMiddleware,
            payments=payments,
            routes={"POST /runs/wait": RouteConfig(plan_id="...", credits=1)},
        ),
    ]
)
```

## Observability

When `LANGSMITH_TRACING=true` is set, the middleware opens a top-level `nvm:x402-request` trace per gated request, with `nvm:verify` and `nvm:settlement` child spans nested under it. Both child spans carry the `nvm.*` metadata from [chapter 12 §Observability](./12-langchain-integration.md#observability) (plan_ids, scheme, network, payer, credits_redeemed, balance.after, tx_hash, payment_token abbreviated, verify/settle durations). The same metadata is also attached to the parent trace.

The graph's own LangGraph-emitted trace appears as a sibling top-level trace, not a child of `nvm:x402-request` — `langgraph-api` initiates the graph trace at the graph-invocation boundary, independent of our middleware's trace context.

Verification failures (missing token, invalid signature, insufficient credits) raise `PaymentRequiredError` inside the `verify_span` so LangSmith marks the parent + child as **failed** via the canonical context-manager exit path. Settle failures after a successful 2xx mark the settle span as failed but leave the parent trace successful (matching the buyer-visible outcome).

## Limitations

- **Streaming responses are buffered.** The middleware reads the downstream response body in full before attaching the `payment-response` settlement header. SSE / `/runs/stream` endpoints become blocking-then-bulk. Gate `/runs/wait` only, or accept the trade-off.
- **Python only.** LangSmith Deployment's custom-app surface is documented as Python-only by LangChain. TypeScript variant tracked in the LangChain integration epic (TS-3).
- **Sync I/O in async dispatch.** The four sync SDK calls (`resolve_scheme`, `resolve_network`, `verify_permissions`, `settle_permissions`) are wrapped in `asyncio.to_thread(...)` so they do not block the event loop. langgraph dev's blocking-call detector treats unwrapped sync HTTP calls as fatal warnings; the wrapping is load-bearing.

## See also

- [Chapter 11 — x402 Protocol](./11-x402.md) for envelope and header semantics.
- [Chapter 12 — LangChain Integration](./12-langchain-integration.md) for the `@requires_payment` decorator (tool-time gating).
- [`payments_py.langsmith.spans`](../reference/langsmith.md) for the observability helpers used internally.
