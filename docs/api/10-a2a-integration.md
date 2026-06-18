# A2A Integration

This guide explains how to integrate the Nevermined Payments Python SDK with A2A (Agent-to-Agent) protocol servers.

## Overview

A2A (Agent-to-Agent) is a protocol that enables AI agents to communicate with each other using JSON-RPC. The Nevermined SDK provides A2A integration to:

- Build A2A servers with payment validation
- Automatically verify x402 tokens on incoming requests
- Handle credit redemption for agent tasks

## Building Agent Cards

### With a Single Plan

```python
from payments_py.a2a.agent_card import build_payment_agent_card

agent_card = build_payment_agent_card(
    base_card={
        "name": "Code Review Agent",
        "description": "Automated code review powered by AI",
        "url": "https://localhost:8080",
        "version": "1.0.0",
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
        },
    },
    payment_metadata={
        "paymentType": "fixed",
        "credits": 1,
        "agentId": "your-agent-id",
        "planId": "your-plan-id",
        "costDescription": "1 credit per review",
    },
)
```

### With Multiple Plans

When your agent supports multiple plans (e.g. a basic and a premium tier), use `planIds` instead of `planId`:

```python
agent_card = build_payment_agent_card(
    base_card={
        "name": "Code Review Agent",
        "url": "https://localhost:8080",
        "version": "1.0.0",
        "capabilities": {},
    },
    payment_metadata={
        "paymentType": "dynamic",
        "credits": 5,
        "agentId": "your-agent-id",
        "planIds": ["plan-basic", "plan-premium"],
        "costDescription": "1-5 credits depending on review depth",
    },
)
```

> **Note:** Provide either `planId` or `planIds`, not both. `planIds` must be a non-empty list.

### Agent Card Structure

The agent card declares two extensions: the Nevermined payment extension (pricing metadata) and the official a2a-x402 extension (`https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2`), which signals support for the standards-compliant in-band x402 v2 flow (see [In-Band x402 v2 Payments](#in-band-x402-v2-payments-standards-flow)). Both ship for one release; `urn:nevermined:payment` is dropped once clients use v0.2 only.

```json
{
  "name": "Code Review Agent",
  "url": "https://localhost:8080",
  "version": "1.0.0",
  "capabilities": {
    "extensions": [
      {
        "uri": "urn:nevermined:payment",
        "params": {
          "paymentType": "dynamic",
          "credits": 5,
          "agentId": "your-agent-id",
          "planIds": ["plan-basic", "plan-premium"],
          "costDescription": "1-5 credits depending on review depth"
        }
      },
      {
        "uri": "https://github.com/google-agentic-commerce/a2a-x402/blob/main/spec/v0.2"
      }
    ]
  }
}
```

## Using the `@a2a_requires_payment` Decorator

The simplest way to create a payment-protected A2A agent:

```python
from payments_py import Payments
from payments_py.common.types import PaymentOptions
from payments_py.a2a import AgentResponse, a2a_requires_payment, build_payment_agent_card

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

agent_card = build_payment_agent_card(
    base_card={
        "name": "My Agent",
        "url": "http://localhost:8080",
        "version": "1.0.0",
        "capabilities": {},
    },
    payment_metadata={
        "paymentType": "dynamic",
        "credits": 3,
        "agentId": "your-agent-id",
        "planIds": ["plan-1", "plan-2"],
    },
)

@a2a_requires_payment(
    payments=payments,
    agent_card=agent_card,
    default_credits=1,
)
async def my_agent(context) -> AgentResponse:
    text = context.get_user_input()
    return AgentResponse(text=f"Echo: {text}", credits_used=1)

# Start serving (blocking)
my_agent.serve(port=8080)
```

The decorator handles:

- Payment middleware (verify/settle) automatically
- Publishing task status events with `creditsUsed` metadata
- Credit burning on task completion

### `AgentResponse`

| Field | Type | Description |
|-------|------|-------------|
| `text` | `str` | The agent's text response |
| `credits_used` | `int \| None` | Credits consumed (falls back to `default_credits`) |
| `metadata` | `dict \| None` | Extra metadata for the final event |

## Starting an A2A Server (Advanced)

For more control, use `PaymentsA2AServer.start()` directly:

```python
from payments_py.a2a.server import PaymentsA2AServer
from a2a.server.agent_execution import AgentExecutor
from a2a.server.events.event_queue import EventQueue

class MyExecutor(AgentExecutor):
    async def execute(self, context, event_queue: EventQueue):
        # Your agent logic — publish events to event_queue
        ...

    async def cancel(self, context, event_queue: EventQueue):
        ...

result = PaymentsA2AServer.start(
    agent_card=agent_card,
    executor=MyExecutor(),
    payments_service=payments,
    port=8080,
    base_path="/",
    expose_agent_card=True,
    async_execution=False,
)

# Run the server
import asyncio
asyncio.run(result.server.serve())
```

## Server Configuration Options

| Option | Type | Required | Description |
|--------|------|----------|-------------|
| `agent_card` | `AgentCard` | Yes | A2A agent card with payment extension |
| `executor` | `AgentExecutor` | Yes | Your agent implementation |
| `payments_service` | `Payments` | Yes | Payments instance |
| `port` | `int` | No | Server port (default: 8080) |
| `task_store` | `TaskStore` | No | Task storage implementation |
| `base_path` | `str` | No | Base URL path (default: "/") |
| `expose_agent_card` | `bool` | No | Expose /.well-known/agent-card.json (+ legacy /.well-known/agent.json alias) |
| `hooks` | `dict` | No | Request lifecycle hooks |
| `async_execution` | `bool` | No | Enable async task execution |

## Request Validation

The A2A server automatically validates payments on every POST request:

1. Extracts Bearer token from Authorization header
2. Reads `planId` or `planIds` from the agent card's payment extension
3. Verifies permissions via `build_payment_required_for_plans()`
4. Rejects requests with 402 if validation fails, including a base64-encoded `payment-required` header

When multiple plans are configured, the 402 response includes all plans in `accepts[]`, allowing the client to choose which plan to purchase.

```
HTTP/1.1 402 Payment Required
payment-required: eyJ4NDAy... (base64-encoded X402PaymentRequired)

{"error": {"code": -32001, "message": "Missing bearer token."}}
```

## In-Band x402 v2 Payments (Standards Flow)

Payment is signalled **in band** following the [Coinbase x402 v2 A2A transport spec](https://github.com/coinbase/x402/blob/main/specs/transports-v2/a2a.md) and the official [a2a-x402 extension](https://github.com/google-agentic-commerce/a2a-x402). The `X402A2AUtils` helpers (see [x402 README](https://github.com/nevermined-io/payments-py/blob/main/payments_py/x402/README.md)) now power this live server flow — `PaymentsA2AServer` stamps and reads the metadata automatically, so the executor is unchanged. The handshake rides on A2A task/message metadata, correlated by `taskId` — no HTTP 402 is exchanged.

Lifecycle:

1. **Payment required** — a payment-gated `message/send` arrives with no payment. The server returns a Task with `status.state = "input-required"` and `status.message.metadata`:

   ```json
   {
     "x402.payment.status": "payment-required",
     "x402.payment.required": { "...": "X402PaymentRequired (accepts[] of plans)" }
   }
   ```

2. **Payment submitted** — the client replies with a follow-up `message/send` whose `message.metadata` carries the payload, correlated via `message.taskId`:

   ```json
   {
     "x402.payment.status": "payment-submitted",
     "x402.payment.payload": { "...": "PaymentPayload" }
   }
   ```

3. **Completed / failed** — on success the final Task carries `x402.payment.status: "payment-completed"` plus `x402.payment.receipts`. On failure it is `failed` / `payment-failed` with the error under `x402.payment.error`, and paid content is suppressed.

Metadata keys: `x402.payment.status`, `x402.payment.required`, `x402.payment.payload`, `x402.payment.receipts`, `x402.payment.error`.

> **Note:** The legacy `payment-signature` HTTP header flow still works but is now a **deprecated fallback, kept for one release**. New integrations should use the in-band metadata flow above.

## Client Usage

### Discovering Plans from the Agent Card

Consumers can fetch the agent card to discover available plans:

```python
import httpx

async with httpx.AsyncClient() as client:
    # Canonical path (A2A 0.3+); /.well-known/agent.json still works as a legacy alias
    resp = await client.get("http://agent-url/.well-known/agent-card.json")
    card = resp.json()

extensions = card["capabilities"]["extensions"]
payment_ext = next(e for e in extensions if e["uri"] == "urn:nevermined:payment")
plan_ids = payment_ext["params"].get("planIds") or [payment_ext["params"]["planId"]]
agent_id = payment_ext["params"]["agentId"]
```

### Ordering a Plan and Sending Messages

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:subscriber-key", environment="sandbox")
)

# Order (purchase) the plan
payments.plans.order_plan(plan_ids[0])

# Get x402 access token
token_resp = payments.x402.get_x402_access_token(
    plan_id=plan_ids[0],
    agent_id=agent_id,
)
access_token = token_resp["accessToken"]

# Send A2A JSON-RPC message
async with httpx.AsyncClient() as client:
    resp = await client.post(
        "http://agent-url/",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": {
                    "messageId": "msg-1",
                    "role": "user",
                    "parts": [{"kind": "text", "text": "Review this code"}],
                }
            },
        },
        headers={"Authorization": f"Bearer {access_token}"},
    )
    result = resp.json()
```

## Hooks

Add custom logic at request lifecycle points:

```python
async def before_request(method, params, request):
    print(f"Incoming request: {method}")

async def after_request(method, response, request):
    print(f"Request completed: {method}")

async def on_error(method, error, request):
    print(f"Request failed: {method} - {error}")

result = PaymentsA2AServer.start(
    agent_card=agent_card,
    executor=executor,
    payments_service=payments,
    hooks={
        "beforeRequest": before_request,
        "afterRequest": after_request,
        "onError": on_error,
    },
)
```

## Error Handling

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| -32001 | 402 | Missing Bearer token |
| -32001 | 402 | Payment validation failed |
| -32001 | 402 | Agent ID missing from card |
| -32001 | 402 | Plan ID missing from card |

## Next Steps

- [x402 Protocol](11-x402.md) - Deep dive into x402 payment protocol
- [Request Validation](08-validation-of-requests.md) - Manual validation patterns
