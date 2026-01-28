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

# Generate access token
result = payments.x402.get_x402_access_token(
    plan_id="your-plan-id",
    agent_id="agent-id"  # Optional but recommended
)

access_token = result['accessToken']
print(f"Access Token: {access_token[:50]}...")
```

### Token Generation Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `plan_id` | `str` | Yes | The payment plan ID |
| `agent_id` | `str` | No | Target agent ID (recommended) |
| `redemption_limit` | `int` | No | Max number of redemptions |
| `order_limit` | `str` | No | Max spend in wei |
| `expiration` | `str` | No | ISO 8601 expiration date |

### Advanced Token Options

```python
from datetime import datetime, timedelta

# Token with limits and expiration
result = payments.x402.get_x402_access_token(
    plan_id="your-plan-id",
    agent_id="agent-id",
    redemption_limit=10,  # Max 10 requests
    order_limit="1000000000000000000",  # Max 1 token in wei
    expiration=(datetime.now() + timedelta(hours=24)).isoformat()
)
```

## Make Requests to Agents

### Using the Access Token

Include the access token in the `Authorization` header:

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
        "Authorization": f"Bearer {access_token}",
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

### Using the X-Payment Header

Alternative header format used by some agents:

```python
response = requests.post(
    agent_endpoint,
    headers={
        "X-Payment": access_token,
        "Content-Type": "application/json"
    },
    json=payload
)
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
    agent_api=AgentAPIAttributes(
        endpoints=[{"POST": "https://api.example.com/tasks"}],
        agent_definition_url="https://api.example.com/openapi.json"
    ),
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
        "Authorization": f"Bearer {access_token}",
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
        new_token = payments.x402.get_x402_access_token(plan_id, agent_id)
```

## Request Flow Diagram

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│  Subscriber  │     │   Nevermined │     │    Agent     │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       │ get_x402_access_token()                 │
       │ ─────────────────► │                    │
       │                    │                    │
       │ ◄───────────────── │                    │
       │   accessToken      │                    │
       │                    │                    │
       │ POST /tasks (Bearer token)              │
       │ ────────────────────────────────────────►
       │                    │                    │
       │                    │  verify_permissions│
       │                    │ ◄────────────────── │
       │                    │ ─────────────────► │
       │                    │                    │
       │                    │  settle_permissions│
       │                    │ ◄────────────────── │
       │                    │ ─────────────────► │
       │                    │                    │
       │ ◄──────────────────────────────────────
       │         Response                       │
       │                    │                    │
```

## Next Steps

- [Validation of Requests](08-validation-of-requests.md) - How agents validate incoming requests
- [x402 Protocol](11-x402.md) - Deep dive into x402 verification and settlement
