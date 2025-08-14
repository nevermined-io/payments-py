[![banner](https://raw.githubusercontent.com/nevermined-io/assets/main/images/logo/banner_logo.png)](https://nevermined.io)

# Library for Activating AI Agent Payments Using the Nevermined Protocol

> Python SDK to interact with the Nevermined Payments Protocol  
> [nevermined.io](https://nevermined.io)

## Motivation

The evolution of AI-native commerce is inevitable, but the infrastructure to support it is currently lacking. Today, AI agents require seamless, automated payment systems for individual transactions. As demand grows, these agents will scale into swarms, transacting and operating autonomously.

Existing solutions are designed for human use with physical money. This does not reflect the new reality, where AI Agents need to make and receive payments quickly and efficiently, without the limitations of traditional payment systems.

Nevermined provides a solution that seamlessly evolves from single-agent needs to complex AI economies, eliminating friction and supporting a fully autonomous, composable future for AI-driven commerce.

## What is the Nevermined Payments Library?

The Nevermined Payments Library is a Python SDK that allows AI Builders and Subscribers to make AI Agents available for querying and use by other agents or humans. It is designed to be used alongside the Nevermined protocol, which provides a decentralized infrastructure for managing AI agents and their interactions.

The Payments Library enables:

- Easy registration and discovery of AI agents and the payment plans required to access them. All agents registered in Nevermined expose their metadata in a generic way, making them searchable and discoverable for specific purposes.
- Flexible definition of pricing options and how AI agents can be queried. This is achieved through payment plans (based on time or credits) and consumption costs (fixed per request or dynamic). All of this can be defined by the AI builder or agent during the registration process.
- Subscribers (humans or other agents) to purchase credits that grant access to AI agent services. Payments can be made in crypto or fiat via Stripe integration. The protocol registers the payment and credits distribution settlement on-chain.
- Agents or users with access credits to query other AI agents. Nevermined authorizes only users with sufficient balance and keeps track of their credit usage.

### Initialize the payments library

```
Payments({"nvm_api_key": nvm_api_key, "environment": "sandbox", "app_id": "your_app_id", "version": "1.0.0"})
```

## A2A Integration (Agents-to-Agents)

The Python SDK can both start an A2A server (FastAPI-based) and act as an A2A client.

### What you need to expose an A2A agent with Nevermined

- Publish an Agent Card at `/.well-known/agent.json` describing the agent.
- Declare `capabilities.streaming: true` if you support `message/stream` and `tasks/resubscribe`.
- Use HTTP auth via headers (e.g., `Authorization: Bearer <token>`), not inside JSON-RPC payloads.
- Include a Nevermined payment extension in the Agent Card to enable authorization and credit burning per request.
- Ensure the Agent Card `url` matches exactly the endpoint where your A2A server listens.

### Nevermined payment extension in the Agent Card

Add the following structure to `capabilities.extensions` of your Agent Card:

```json
{
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "extensions": [
      {
        "uri": "urn:nevermined:payment",
        "description": "Dynamic cost per request",
        "required": false,
        "params": {
          "paymentType": "dynamic",
          "credits": 1,
          "planId": "<planId>",
          "agentId": "<agentId>"
        }
      }
    ]
  },
  "url": "https://your-agent.example.com/a2a/"
}
```

Important:

- The final streaming event of your agent should include `metadata.creditsUsed` to allow Nevermined to burn credits.
- The exact URL (including basePath) must match the registration in Nevermined, otherwise validation will fail.

### Build a payment-enabled Agent Card

```python
from payments_py.payments import Payments

payments_builder = Payments({
    "nvm_api_key": "<BUILDER_API_KEY>",
    "environment": "staging_sandbox",
})

base_agent_card = {
    "name": "Py A2A Agent",
    "description": "A2A test agent",
    "capabilities": {
        "streaming": True,
        "pushNotifications": True,
        "stateTransitionHistory": True,
    },
    "defaultInputModes": ["text"],
    "defaultOutputModes": ["text"],
    "skills": [],
    "url": "https://your-agent.example.com/a2a/",
    "version": "1.0.0",
}

from payments_py.a2a.agent_card import build_payment_agent_card

agent_card = build_payment_agent_card(base_agent_card, {
    "paymentType": "dynamic",
    "credits": 1,
    "costDescription": "Dynamic cost per request",
    "planId": "<planId>",
    "agentId": "<agentId>",
})
```

### Start an A2A server

```python
from payments_py.a2a.server import PaymentsA2AServer

class DummyExecutor:
    async def execute(self, ctx, event_queue):
        event_queue.publish({
            "kind": "status-update",
            "taskId": ctx.taskId,
            "contextId": ctx.userMessage.get("contextId"),
            "status": {"state": "completed"},
            "metadata": {"creditsUsed": 1},
            "final": True,
        })
        event_queue.finished()

server = PaymentsA2AServer.start(
    agent_card=agent_card,
    executor=DummyExecutor(),
    payments_service=payments_builder,
    port=PORT,
    base_path="/a2a/",
)
```

### Use the A2A client

```python
payments_subscriber = Payments({
    "nvm_api_key": "<SUBSCRIBER_API_KEY>",
    "environment": "staging_sandbox",
})

client = payments_subscriber.a2a.get_client(
    agent_base_url="https://your-agent.example.com/a2a/",
    agent_id="<agentId>",
    plan_id="<planId>",
)

# Send a simple request
result = await client.send_message({
    "message": {"kind": "message", "role": "user", "messageId": "123", "parts": [{"kind": "text", "text": "Hello"}]}
})

# Stream events
async for event in client.send_message_stream({
    "message": {"kind": "message", "role": "user", "messageId": "124", "parts": [{"kind": "text", "text": "Stream"}]}
}):
    if event.get("result", {}).get("final"):
        break
```

### Plans helpers as static methods

You can build price and credits configurations through `Payments.plans` static helpers, mirroring `payments_py/plans.py`:

```python
pc = payments_builder.plans.get_erc20_price_config(20, "0x...token...", payments_builder.account_address)
cc = payments_builder.plans.get_fixed_credits_config(100)
```

### Typical API usage (Python)

```python
from payments_py.payments import Payments
from payments_py.common.types import PlanMetadata

payments = Payments({"nvm_api_key": "<KEY>", "environment": "sandbox"})

# Create a plan
plan_metadata = PlanMetadata(name="My Plan")
price = payments.plans.get_erc20_price_config(20, "0x...token...", payments.account_address)
credits = payments.plans.get_fixed_credits_config(100)
plan_res = payments.plans.register_credits_plan(plan_metadata, price, credits)
plan_id = plan_res["planId"]

# Register an agent
agent_res = payments.agents.register_agent(
    {"name": "My Agent"},
    {"endpoints": [{"POST": "https://your-agent.example.com/a2a/"}]},
    [plan_id],
)
agent_id = agent_res["agentId"]

# Order plan
payments.plans.order_plan(plan_id)

# Get plan balance
balance = payments.plans.get_plan_balance(plan_id)

# Get agent access token
access = payments.agents.get_agent_access_token(plan_id, agent_id)
token = access["accessToken"] if isinstance(access, dict) else access.access_token
```
