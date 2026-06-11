# LangChain Integration

This guide covers the LangChain and LangGraph integration shipped in the `[langchain]` optional extra of `payments-py`. The module `payments_py.x402.langchain` provides the decorator, helpers, and exceptions for monetizing LangChain tools with the x402 protocol.

For the conceptual walk-through (two integration approaches, the discovery-first flow, dynamic credits patterns), see the [LangChain integration guide](/docs/integrate/add-to-your-agent/langchain). For a runnable end-to-end demo, see the [`langchain-paid-agent-py`](https://github.com/nevermined-io/tutorials/tree/main/langchain-paid-agent-py) tutorial.

> Looking to gate a **LangSmith Deployment** entry point (`/threads/{id}/runs/wait` etc.) rather than individual tools? See [LangSmith Deployment Middleware](./13-langsmith-deployment.md). The two integrations are complementary: the decorator covered here protects tools the agent calls; the LangSmith Deployment middleware protects the agent's HTTP entry point.

## Installation

```bash
pip install payments-py[langchain] langgraph langchain-openai
```

The `[langchain]` extra installs `langchain-core`. `langgraph` and `langchain-openai` are optional — needed only if you build a LangGraph agent.

## Exports

| Symbol | Purpose |
|--------|---------|
| `requires_payment` | Decorator that gates a `@tool` on an x402 access token |
| `PaymentRequiredError` | Exception raised when the token is missing or verification fails |
| `last_settlement` | Read the most recent settlement receipt from outside the agent's call stack |
| `create_paid_react_agent` | LangGraph ReAct agent builder that lets `PaymentRequiredError` propagate intact |

All four are exported from `payments_py.x402.langchain`:

```python
from payments_py.x402.langchain import (
    requires_payment,
    PaymentRequiredError,
    last_settlement,
    create_paid_react_agent,
)
```

## `requires_payment`

Decorator that protects a LangChain `@tool` with x402 payment verification and settlement. Pulls the access token from `RunnableConfig.configurable["payment_token"]`, verifies it, runs the tool body, then settles credits.

### Signature

```python
def requires_payment(
    payments: Payments,
    plan_id: str | None = None,
    plan_ids: list[str] | None = None,
    credits: int | Callable[[dict], int] = 1,
    agent_id: str | None = None,
    network: str | None = None,
    scheme: str | None = None,
) -> Callable
```

| Parameter | Description |
|-----------|-------------|
| `payments` | A `Payments` instance with `payments.facilitator` configured. |
| `plan_id` / `plan_ids` | The plan(s) the tool charges against. Pass one of the two; `plan_id` is a convenience for the single-plan case. |
| `credits` | How many credits to charge. Sent to the facilitator as `max_amount`. See [credits semantics](#credits-semantics) for fixed-vs-range plans. |
| `agent_id` | Optional agent identifier propagated to the receipt. |
| `network` | Optional CAIP-2 network ID. Auto-resolved from the plan when omitted. |
| `scheme` | Optional x402 scheme (`nvm:erc4337` or `nvm:card-delegation`). Auto-resolved when omitted. |

### Decorator order

`@tool` **outside**, `@requires_payment` **inside**:

```python
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from payments_py import Payments, PaymentOptions
from payments_py.x402.langchain import requires_payment

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:builder-key", environment="sandbox")
)

@tool
@requires_payment(payments=payments, plan_id="plan-123", credits=1)
def get_market_insight(topic: str, config: RunnableConfig = None) -> str:
    """Return a short market insight. Costs 1 credit per call."""
    return f"Market insight for '{topic}': demand is up 12% QoQ."
```

The protected function **must** accept a `config: RunnableConfig` parameter — that is how the decorator reads the payment token at call time.

### Dynamic credits

`credits` accepts three forms:

- **Static int** — `credits=1` (fixed cost per call).
- **Lambda** — `credits=lambda ctx: max(1, len(ctx["result"]) // 100)`.
- **Named function** — `credits=my_fn` where `my_fn(ctx) -> int`.

When callable, `ctx` is `{"args": <tool kwargs>, "result": <tool return>}`. Dynamic credits resolve **after** execution so the result is available.

### Credits semantics

The `credits` argument is sent to the facilitator as `max_amount`. The actual amount redeemed depends on the plan's server-side credit configuration:

- **Fixed plans** (`plan.credits.minAmount == plan.credits.maxAmount`) always burn `plan.credits.maxAmount`. The decorator's `credits=N` is then effectively a no-op (per [nevermined-io/nvm-monorepo#1568](https://github.com/nevermined-io/nvm-monorepo/issues/1568)).
- **Range plans** clamp the supplied value into `[plan.credits.minAmount, plan.credits.maxAmount]`.

If you want predictable per-call cost, configure the plan as fixed; the decorator value is then a client-side declaration.

## `PaymentRequiredError`

Raised by `@requires_payment` when the token is missing from `config["configurable"]["payment_token"]`, or when the facilitator rejects the token (expired, invalid signature, insufficient balance, etc.). Carries the full `X402PaymentRequired` payload so callers can run the x402 discovery flow.

```python
from payments_py.x402.langchain import PaymentRequiredError

try:
    agent.invoke({"messages": [("human", "...")]}, config={"configurable": {}})
except PaymentRequiredError as err:
    accepts = err.payment_required.accepts[0]
    # accepts.scheme    → "nvm:erc4337" or "nvm:card-delegation"
    # accepts.network   → CAIP-2 chain or provider name (stripe, braintree, visa)
    # accepts.plan_id   → which plan to acquire a token against
```

### Attributes

| Attribute | Type | Description |
|-----------|------|-------------|
| `payment_required` | `X402PaymentRequired \| None` | The full x402 v2 payment-required payload. `accepts[0]` carries scheme / network / plan_id / agent_id. |

For the discovery → acquire → retry flow, see the [LangChain integration guide](/docs/integrate/add-to-your-agent/langchain).

## `last_settlement`

Returns the most recent `SettleResponse` produced by `@requires_payment` in this process. Use this after invoking a LangGraph runnable to recover the settlement receipt — `credits_redeemed`, `remaining_balance`, `transaction`, `network`, `payer` — without threading it back through `RunnableConfig.configurable` (which LangGraph copies per node, so the SDK's in-place write is not visible to the outer caller).

### Signature

```python
def last_settlement() -> SettleResponse | None
```

Returns `None` if no settlement has happened yet in this process, or if the most recent invocation raised before reaching the settle phase.

### Example

```python
from payments_py.x402.langchain import last_settlement

result = agent.invoke(
    {"messages": [("human", "...")]},
    config={"configurable": {"payment_token": token}},
)

receipt = last_settlement()
if receipt:
    print(f"  credits_redeemed: {receipt.credits_redeemed}")
    print(f"  remaining_balance: {receipt.remaining_balance}")
    print(f"  transaction: {receipt.transaction}")
```

!!! warning "Single-tenant"

    `last_settlement()` reads from a module-level slot. In multi-tenant processes (e.g. a server handling concurrent settlements), the value reflects whichever invocation settled most recently — there is no per-call isolation. For multi-tenant scenarios, surface settlement via a callback or observability layer instead.

## `create_paid_react_agent`

Thin wrapper over [`langgraph.prebuilt.create_react_agent`](https://langchain-ai.github.io/langgraph/reference/prebuilt/#create_react_agent) that constructs the underlying `ToolNode` with `handle_tool_errors=False`. That single change is what lets `PaymentRequiredError` propagate all the way back to `agent.invoke()`'s caller with its `X402PaymentRequired` payload intact — the default `ToolNode` behaviour stringifies the exception into a `ToolMessage` for the LLM and **loses the payload**.

### Signature

```python
def create_paid_react_agent(
    model: Any,
    tools: Sequence[Any],
    **kwargs: Any,
) -> CompiledStateGraph
```

| Parameter | Description |
|-----------|-------------|
| `model` | Anything accepted by `create_react_agent`'s `model` argument (a `BaseChatModel`, a string, a runnable, etc.). |
| `tools` | Sequence of LangChain tools — typically functions decorated with `@tool` and `@requires_payment`. |
| `**kwargs` | Forwarded verbatim to `create_react_agent` (`prompt`, `state_schema`, `checkpointer`, …). Unknown kwargs raise `TypeError` from LangGraph at call time. |

`langgraph` is imported lazily so the `[langchain]` extra need not pull it in. Install LangGraph yourself (`pip install langgraph`) to use this helper.

### Example

```python
from langchain_openai import ChatOpenAI
from payments_py.x402.langchain import create_paid_react_agent, requires_payment

@tool
@requires_payment(payments=payments, plan_id=PLAN_ID, credits=1)
def get_market_insight(topic: str, config=None) -> str:
    return f"Market insight for {topic} ..."

agent = create_paid_react_agent(
    ChatOpenAI(model="gpt-4o-mini", temperature=0),
    [get_market_insight],
    prompt="You are a market data assistant. Always call get_market_insight.",
)
```

## End-to-end usage

The canonical x402 flow uses all four symbols together — discovery, acquisition, retry, receipt read:

```python
import os
from dotenv import load_dotenv
from payments_py import Payments, PaymentOptions
from payments_py.x402.langchain import (
    PaymentRequiredError,
    create_paid_react_agent,
    last_settlement,
    requires_payment,
)
from payments_py.x402.types import (
    CreateDelegationPayload,
    DelegationConfig,
    X402TokenOptions,
)

load_dotenv()
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key=os.environ["NVM_API_KEY"],
        environment=os.getenv("NVM_ENVIRONMENT", "sandbox"),
    )
)

# 1. Build the agent (see the LangChain integration guide for the protected tool).
agent = create_paid_react_agent(model, [get_market_insight], prompt=prompt)

# 2. Discover what the agent's tool charges by invoking without a token.
try:
    agent.invoke({"messages": [("human", QUERY)]}, config={"configurable": {}})
except PaymentRequiredError as err:
    accept = err.payment_required.accepts[0]

# 3. Create a delegation once (currency is required), then acquire a token
#    against the discovered plan by referencing the delegation id.
pm = next(m for m in payments.delegation.list_payment_methods()
          if m.provider == accept.network)
delegation = payments.delegation.create_delegation(
    CreateDelegationPayload(
        provider=pm.provider,
        provider_payment_method_id=pm.id,
        spending_limit_cents=10000,
        duration_secs=3600,
        currency="usd",
    )
)
token = payments.x402.get_x402_access_token(
    accept.plan_id,
    token_options=X402TokenOptions(
        scheme=accept.scheme,
        delegation_config=DelegationConfig(delegation_id=delegation.delegation_id),
    ),
)["accessToken"]

# 4. Retry with the token and read the settlement.
result = agent.invoke(
    {"messages": [("human", QUERY)]},
    config={"configurable": {"payment_token": token}},
)
receipt = last_settlement()
```

For the full, runnable version see [`tutorials/langchain-paid-agent-py`](https://github.com/nevermined-io/tutorials/tree/main/langchain-paid-agent-py).

## Observability with LangSmith

When the optional `[langsmith]` extra is installed and a LangSmith run is active in the calling context, `@requires_payment` automatically emits two child spans nested under the active tool span:

- **`nvm:verify`** — opens around the verify-permissions call, with attributes describing the scheme, plan, payer, and verify duration.
- **`nvm:settlement`** — opens around the settle-permissions call, with attributes describing credits redeemed, remaining balance, transaction hash, network, and settle duration.

The same `nvm.*` metadata is also attached to the parent tool span so the trace is searchable from either level. The per-call child spans are always authoritative; the parent copy is best-effort and can be overwritten when two protected tools run in the same node — see [Known limitations](#known-limitations).

### Install

```bash
pip install "payments-py[langchain,langsmith]"
```

### Enable

```bash
export LANGSMITH_TRACING=true
export LANGSMITH_API_KEY=<your-langsmith-api-key>
export LANGSMITH_PROJECT=<your-project-name>  # optional
```

No code changes are needed beyond the existing `@requires_payment` decorator — the spans are emitted automatically when LangSmith is active. If `langsmith` is not installed or `LANGSMITH_TRACING` is unset, span emission is a silent no-op.

#### Regional endpoint

LangSmith hosts accounts across several regions. The SDK defaults to GCP US (`https://api.smith.langchain.com`); accounts in any other region must set `LANGSMITH_ENDPOINT` or the trace POST will fail with `403 Forbidden` on `/runs/multipart`.

| Region   | Endpoint                                      |
| -------- | --------------------------------------------- |
| GCP US   | `https://api.smith.langchain.com` *(default)* |
| GCP EU   | `https://eu.api.smith.langchain.com`          |
| GCP APAC | `https://apac.api.smith.langchain.com`        |
| AWS US   | `https://aws.api.smith.langchain.com`         |

```bash
export LANGSMITH_ENDPOINT=https://eu.api.smith.langchain.com
```

The payment flow itself is unaffected by trace-shipping failures — verify, tool execution, and settle proceed normally. Only the LangSmith trace ingestion fails, surfaced as `langsmith.utils.LangSmithError` warnings.

### Span attributes

| Span             | Attribute                  | Source                                            |
| ---------------- | -------------------------- | ------------------------------------------------- |
| `nvm:verify`     | `nvm.plan_ids`             | configured `plan_id` / `plan_ids`                 |
| `nvm:verify`     | `nvm.scheme`               | resolved scheme (`nvm:erc4337` or `nvm:card-delegation`) |
| `nvm:verify`     | `nvm.network`              | CAIP-2 chain or provider name                     |
| `nvm:verify`     | `nvm.agent_id`             | configured `agent_id`                             |
| `nvm:verify`     | `nvm.payer`                | from `VerifyResponse.payer`                       |
| `nvm:verify`     | `nvm.agent_request_id`     | from `VerifyResponse.agent_request_id`            |
| `nvm:verify`     | `nvm.payment_token`        | first 16 chars + `…` + last 4 chars of the x402 access token |
| `nvm:verify`     | `nvm.verify.duration_ms`   | measured                                          |
| `nvm:settlement` | `nvm.credits_redeemed`     | from `SettleResponse.credits_redeemed`            |
| `nvm:settlement` | `nvm.balance.after`        | from `SettleResponse.remaining_balance`           |
| `nvm:settlement` | `nvm.tx_hash`              | from `SettleResponse.transaction`                 |
| `nvm:settlement` | `nvm.network`              | from `SettleResponse.network`                     |
| `nvm:settlement` | `nvm.payer`                | from `SettleResponse.payer`                       |
| `nvm:settlement` | `nvm.payment_token`        | first 16 chars + `…` + last 4 chars of the x402 access token |
| `nvm:settlement` | `nvm.settle.duration_ms`   | measured                                          |

### Sensitive data in traces

The `payment_token` that the buyer passes via `config["configurable"]["payment_token"]` is captured by LangChain into the parent tool span's metadata, and would normally be inherited by any child span — including the `nvm:verify` and `nvm:settlement` spans the decorator emits. The full token grants access to the protected tool until it expires, so the decorator **proactively strips `payment_token` from the parent tool span's metadata** before opening any child span. The full credential never reaches a Nevermined span attribute.

For correlation across spans the decorator surfaces an abbreviated `nvm.payment_token` attribute (`eyJ4NDAyVmVyc2lv…bsig`, first 16 chars + ellipsis + last 4) on both `nvm:verify` and `nvm:settlement`. That gives you "which token was this?" without exposing the credential itself.

A real x402 access token is a JWT, which is far longer than 20 chars. If a token of **20 characters or fewer** is passed — almost always a misconfiguration (a plan id or opaque handle where the JWT was expected) — it is **redacted, not exported**: `nvm.payment_token` shows at most the first 4 chars plus a `…(short)` marker (e.g. `eyJ4…(short)`), and a runtime warning is logged. For a token of 4 chars or fewer, nothing is revealed at all — it collapses to just `…(short)`. The full short value never reaches a span attribute, so a misrouted secret cannot leak into a durable trace store even when it is shorter than the abbreviation threshold.

The active redaction covers the documented LangChain-via-configurable path. If you're surfacing the token through a different channel (custom callbacks, an explicit `add_metadata({"payment_token": ...})`, raw inputs to a tool whose signature contains the token), the decorator can't see those — strip them yourself or set `export LANGSMITH_HIDE_INPUTS=true` for blanket coverage.

Other `nvm.*` attributes that may be considered sensitive depending on your context:

- `nvm.payer` — the payer's wallet address (public on-chain, but a stable identifier).
- `nvm.tx_hash` — the settlement transaction id.
- `nvm.agent_request_id` — Nevermined-internal correlation id.
- `nvm.balance.after` — the payer's remaining credit balance after this settlement. Reveals per-payer depletion patterns to anyone with trace read access on the operator's LangSmith project. Suppress with `LANGSMITH_HIDE_OUTPUTS=true` or post-filter.

None of these grant access on their own.

### Known limitations

#### Parent metadata is last-writer-wins across tools in one node

`@requires_payment` attaches its `nvm.*` metadata to **two** places: the per-call **child** spans (`nvm:verify` / `nvm:settlement`) and, as a convenience for searchability, the **parent** LangSmith run tree.

The child spans are isolated per call, so they are always correct. The parent copy is **not** namespaced per tool: the bare `nvm.*` keys (`nvm.tx_hash`, `nvm.credits_redeemed`, `nvm.payment_token`, …) are written directly onto the parent run's metadata. When an agent calls **two `@requires_payment` tools within the same LangGraph `ToolNode`** — the common pattern, since a single ReAct step can dispatch multiple tool calls into one node — both decorators target the **same** parent run tree, and the second `add_metadata` **silently overwrites** the first's `nvm.*` values. The parent therefore reflects only the **last** tool that settled in that node; the earlier tool's parent-level `nvm.*` is lost.

What this means in practice:

- **Per-call billing fidelity lives on the child spans, not the parent.** For accurate per-tool accounting (which token, which tx hash, how many credits each call redeemed), filter and aggregate on the `nvm:verify` / `nvm:settlement` **child** spans. Each child carries the values for exactly one call.
- **Treat parent `nvm.*` as best-effort.** It is convenient for "did this trace touch Nevermined at all?" searches, but do not rely on it for last-writer-sensitive fields when multiple paid tools can run in one node.
- This is a **last-writer-wins** behaviour, not a correctness bug in settlement — every call still verifies and settles independently and correctly. Only the parent's *denormalized copy* of the metadata is affected.

This matches the cross-SDK **observability spans v1** contract (the SDK-neutral span spec maintained in `nvm-monorepo`, which both `payments-py` and `@nevermined-io/payments` emit against): child spans are authoritative per tool; parent `nvm.*` is best-effort / last-writer-wins.

### Manual use (non-LangChain paths)

The same context managers are also exported for code that wants to emit Nevermined-flavored spans without going through `@requires_payment` (e.g. the FastAPI middleware path):

```python
from payments_py.langsmith import (
    settlement_span,
    verify_span,
    build_settle_metadata,
)

with settlement_span(plan_ids=["plan-1"]) as span:
    settlement = payments.facilitator.settle_permissions(...)
    if span is not None:
        span.add_metadata(build_settle_metadata(settlement, ["plan-1"]))
```

Span emission failures are caught internally — observability is best-effort and will not interfere with the payment flow.

## Related

- [LangChain integration guide](/docs/integrate/add-to-your-agent/langchain) — conceptual walk-through, the two integration approaches (decorator vs. HTTP middleware), and the TypeScript variant.
- [x402 Protocol](11-x402.md) — token generation, delegation config, scheme resolution.
- [`tutorials/langchain-paid-agent-py`](https://github.com/nevermined-io/tutorials/tree/main/langchain-paid-agent-py) — the minimal end-to-end demo.
