# Querying an Agent

This guide explains how to get x402 access tokens and make authenticated requests to AI agents.

## Overview

To query an AI agent, subscribers need to:

1. Have an active subscription to a plan associated with the agent
2. Generate an x402 access token
3. Include the token in requests to the agent

## Get X402 Access Token

The x402 access token authorizes requests to agents and enables credit verification/settlement.

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:subscriber-key", environment="sandbox")
)

# Generate access token (basic — no delegation config needed for credit/fiat plans)
result = payments.x402.get_x402_access_token(
    plan_id="your-plan-id",
    agent_id="agent-id"  # Optional but recommended
)

access_token = result['accessToken']
print(f"Access Token: {access_token[:50]}...")
print(f"Token version: {result['tokenVersion']}")  # 2 or 3
```

### Token Generation Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | `str` | Yes | The payment plan ID |
| `agent_id` | `str` | No | Target agent ID (recommended) |
| `token_options` | `X402TokenOptions` | No | Scheme, delegation, resource binding and requested token version |

`X402TokenOptions` fields:

| Field | Type | Description |
|-------|------|-------------|
| `scheme` | `str` | x402 scheme (defaults to `nvm:erc4337`) |
| `network` | `str` | Network identifier (auto-derived from the scheme if omitted) |
| `delegation_config` | `DelegationConfig` | Delegation to mint against |
| `resource` | `str` \| `X402Resource` | The protected resource the token is minted for. Signed on v3 |
| `http_verb` | `str` | HTTP verb of that resource (e.g. `"POST"`). Signed on v3 |
| `token_version` | `int` | Access-token version to **request** (`2` or `3`). Never read it back from here — see below |

The result is a dict with:

| Key | Type | Description |
|-----|------|-------------|
| `accessToken` | `str` | The access token to send in `payment-signature` |
| `tokenVersion` | `int` | `2` or `3`, **detected from the returned token**, not from what was requested |

### Token Generation with Delegation

For erc4337 (crypto) plans, token generation uses delegations. The supported
flow is **create-first**: create the delegation once, then reference it by
`delegation_id` on every token request. Delegations are plan-agnostic by
default, so a single delegation can back token requests across many plans.

```python
from payments_py.x402 import X402TokenOptions, DelegationConfig, CreateDelegationPayload

# Step 1 — create the delegation once. `currency` is required.
delegation = payments.delegation.create_delegation(
    CreateDelegationPayload(
        provider="erc4337",
        spending_limit_cents=10000,  # $100
        duration_secs=604800,        # 1 week
        currency="usdc",
    )
)

# Step 2 — request a token referencing the delegation id (reusable across plans).
result = payments.x402.get_x402_access_token(
    plan_id="your-plan-id",
    agent_id="agent-id",
    token_options=X402TokenOptions(
        delegation_config=DelegationConfig(
            delegation_id=delegation.delegation_id
        )
    )
)
```

> **Deprecated:** passing `spending_limit_cents` / `duration_secs` (or a payment
> method) directly to `get_x402_access_token` — inline "create-on-the-fly" —
> still works but emits a `DeprecationWarning` and will be removed in a future
> release. Create the delegation first as shown above.

### Single-Use Tokens (v3)

By default the backend mints a **v2** token: a reusable bearer credential you
can keep for the lifetime of your client. Opt into a **v3** token to get one
that is bound to a single seller endpoint and is **consumed by its first
settle**:

```python
result = payments.x402.get_x402_access_token(
    plan_id="your-plan-id",
    agent_id="agent-id",
    token_options=X402TokenOptions(
        delegation_config=DelegationConfig(delegation_id=delegation.delegation_id),
        resource="https://seller.example/api/v1/tasks",
        http_verb="POST",
        token_version=3,
    ),
)

if result["tokenVersion"] == 3:
    ...  # do NOT reuse: mint a fresh token for the next paid request
```

Requesting v3 is not a guarantee of getting v3 — a backend that predates v3
support drops the field silently and returns v2. Always read
`result["tokenVersion"]` (or `is_single_use_access_token(access_token)`), never the
value you passed in. Full details, including the `BCK.X402.0059`
"already used" error, are in
[x402 Payment Protocol](11-x402.md#access-token-versions-v2-and-v3).

## Make Requests to Agents

### Using the x402 Payment Header

Include the access token in the `payment-signature` header (per [x402 v2 HTTP transport spec](https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md)):

```python
import requests

# Get access token
token_result = payments.x402.get_x402_access_token(
    plan_id=plan_id,
    agent_id=agent_id
)
access_token = token_result['accessToken']

# Make request to the agent
response = requests.post(
    f"https://agent-api.example.com/agents/{agent_id}/tasks",
    headers={
        "payment-signature": access_token,
        "Content-Type": "application/json"
    },
    json={
        "task": "Analyze this data",
        "data": {"key": "value"}
    }
)

if response.status_code == 200:
    result = response.json()
    print(f"Agent response: {result}")
elif response.status_code == 402:
    print("Payment required - check plan balance")
else:
    print(f"Error: {response.status_code}")
```

## Decode Access Token

You can decode the token to inspect its contents:

```python
from payments_py.x402.token import decode_access_token

decoded = decode_access_token(access_token)

if decoded:
    payload = decoded.get('payload', {})
    authorization = payload.get('authorization', {})

    print(f"Subscriber: {authorization.get('from')}")
    print(f"Plan ID: {authorization.get('planId')}")
    print(f"Agent ID: {authorization.get('agentId')}")

    # v3 tokens additionally carry the signed binding and a one-time nonce.
    print(f"Resource URL: {authorization.get('resourceUrl')}")
    print(f"HTTP verb: {authorization.get('httpVerb')}")
    print(f"Nonce: {authorization.get('nonce')}")
```

The `nonce` is what distinguishes the two versions — but use the helpers rather
than reading it yourself:

```python
from payments_py.x402 import detect_access_token_version, is_single_use_access_token

detect_access_token_version(access_token)  # 2 or 3
is_single_use_access_token(access_token)        # True / False
```

## Complete Example

```python
from payments_py import Payments, PaymentOptions
from payments_py.common.types import PlanMetadata, AgentMetadata, AgentAPIAttributes
from payments_py.plans import get_free_price_config, get_fixed_credits_config
import requests

# Initialize as builder
builder = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:builder-key", environment="sandbox")
)

# Initialize as subscriber
subscriber = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:subscriber-key", environment="sandbox")
)

# 1. Builder creates plan and agent
plan_result = builder.plans.register_credits_plan(
    plan_metadata=PlanMetadata(name="API Access Plan"),
    price_config=get_free_price_config(),  # Free for demo
    credits_config=get_fixed_credits_config(100)
)
plan_id = plan_result['planId']

agent_result = builder.agents.register_agent(
    agent_metadata=AgentMetadata(name="Demo Agent"),
    # AgentAPIAttributes() with no args registers a minimal agent — your
    # Payments library middleware handles per-route gating. See
    # docs/api/04-agents.md for opt-in Additional Security.
    agent_api=AgentAPIAttributes(),
    payment_plans=[plan_id]
)
agent_id = agent_result['agentId']

# 2. Subscriber orders the plan
subscriber.plans.order_plan(plan_id)

# 3. Subscriber generates access token
token_result = subscriber.x402.get_x402_access_token(
    plan_id=plan_id,
    agent_id=agent_id
)
access_token = token_result['accessToken']

# 4. Subscriber makes request to agent
response = requests.post(
    "https://api.example.com/tasks",
    headers={
        "payment-signature": access_token,
        "Content-Type": "application/json"
    },
    json={"prompt": "Hello, agent!"}
)

print(f"Status: {response.status_code}")
print(f"Response: {response.json()}")

# 5. Check updated balance
balance = subscriber.plans.get_plan_balance(plan_id)
print(f"Remaining credits: {balance.balance}")
```

## Error Handling

### 402 Payment Required

```python
response = requests.post(agent_endpoint, headers=headers, json=payload)

if response.status_code == 402:
    error = response.json()
    print(f"Payment required: {error}")

    # Check balance
    balance = payments.plans.get_plan_balance(plan_id)
    if balance.balance <= 0:
        print("No credits remaining - order more credits")
    elif not balance.is_subscriber:
        print("Not subscribed - order the plan first")
```

### Token Expired or Invalid

```python
try:
    response = requests.post(agent_endpoint, headers=headers, json=payload)
    response.raise_for_status()
except requests.HTTPError as e:
    if e.response.status_code == 401:
        print("Token expired or invalid - generate a new token")
        # Regenerate token
        new_token = payments.x402.get_x402_access_token(plan_id, agent_id, token_options=token_options)
```

## Request Flow Diagram

```mermaid
sequenceDiagram
    participant Subscriber
    participant Nevermined
    participant Agent

    Subscriber->>Nevermined: get_x402_access_token()
    Nevermined-->>Subscriber: accessToken

    Subscriber->>Agent: POST /tasks<br/>payment-signature: token

    Agent->>Nevermined: verify_permissions()
    Nevermined-->>Agent: {isValid: true}

    Agent->>Nevermined: settle_permissions()
    Nevermined-->>Agent: {success: true}

    Agent-->>Subscriber: Response
```

## Next Steps

- [Request Validation](08-validation-of-requests.md) - How agents validate incoming requests
- [x402 Protocol](11-x402.md) - Deep dive into x402 verification and settlement
