# A2A Integration

This guide explains how to integrate the Nevermined Payments Python SDK with A2A (Agent-to-Agent) protocol servers.

## Overview

A2A (Agent-to-Agent) is a protocol that enables AI agents to communicate with each other using JSON-RPC. The Nevermined SDK provides A2A integration to:

- Build A2A servers with payment validation
- Automatically verify x402 tokens on incoming requests
- Handle credit redemption for agent tasks

## A2A Integration API

Access the A2A integration through `payments.a2a`:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# A2A integration is available as:
a2a = payments.a2a
```

## Starting an A2A Server

### Basic Server Setup

```python
from payments_py import Payments, PaymentOptions
from payments_py.a2a.agent_card import build_payment_agent_card
from a2a.server.agent_execution import AgentExecutor

# Initialize payments
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Build agent card with payment extension
agent_card = build_payment_agent_card(
    name="My AI Agent",
    description="An AI agent with payment support",
    agent_id="your-agent-id",
    plan_id="your-plan-id",
    url="https://your-agent.com"
)

# Create your agent executor (implements A2A AgentExecutor interface)
class MyAgentExecutor(AgentExecutor):
    async def execute(self, task, context):
        # Your agent logic here
        return {"result": "Task completed"}

executor = MyAgentExecutor()

# Start the A2A server
result = payments.a2a["start"](
    agent_card=agent_card,
    executor=executor,
    port=8080
)

# Run the server
result.server.run()
```

## Building Agent Cards

### With Payment Extension

```python
from payments_py.a2a.agent_card import build_payment_agent_card

agent_card = build_payment_agent_card(
    name="Code Review Agent",
    description="Automated code review powered by AI",
    agent_id="did:nvm:abc123",
    plan_id="plan-456",
    url="https://code-review.example.com",
    version="1.0.0",
    capabilities={
        "streaming": True,
        "pushNotifications": True
    }
)
```

### Agent Card Structure

The agent card includes a payment extension:

```json
{
  "name": "Code Review Agent",
  "description": "Automated code review powered by AI",
  "url": "https://code-review.example.com",
  "version": "1.0.0",
  "capabilities": {
    "streaming": true,
    "pushNotifications": true,
    "extensions": [
      {
        "uri": "urn:nevermined:payment",
        "params": {
          "agentId": "did:nvm:abc123",
          "planId": "plan-456"
        }
      }
    ]
  }
}
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
| `expose_agent_card` | `bool` | No | Expose /.well-known/agent.json |
| `hooks` | `dict` | No | Request lifecycle hooks |
| `async_execution` | `bool` | No | Enable async task execution |

## Request Validation

The A2A server automatically validates payments:

1. Extracts Bearer token from Authorization header
2. Verifies permissions against the agent's plan
3. Rejects requests with 402 if validation fails

```python
# Requests must include:
# Authorization: Bearer <x402-access-token>

# Invalid requests receive:
# HTTP 402 Payment Required
# {"error": {"code": -32001, "message": "Validation error: ..."}}
```

## Complete Example

```python
import asyncio
from payments_py import Payments, PaymentOptions
from payments_py.a2a.agent_card import build_payment_agent_card
from a2a.server.agent_execution import AgentExecutor
from a2a.types import Task, TaskResult, Message

# Initialize payments
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Define your agent executor
class CodeReviewExecutor(AgentExecutor):
    """Agent that performs code reviews."""

    async def execute(self, task: Task, context: dict) -> TaskResult:
        # Extract code from task
        messages = task.get("messages", [])
        code = ""
        for msg in messages:
            if msg.get("role") == "user":
                parts = msg.get("parts", [])
                for part in parts:
                    if part.get("type") == "text":
                        code = part.get("text", "")
                        break

        # Perform code review (your logic here)
        review_result = await self.review_code(code)

        return TaskResult(
            status="completed",
            messages=[
                Message(
                    role="assistant",
                    parts=[{"type": "text", "text": review_result}]
                )
            ]
        )

    async def review_code(self, code: str) -> str:
        # Your code review logic
        return f"Code review completed. Found 3 suggestions for improvement."

# Build agent card
agent_card = build_payment_agent_card(
    name="Code Review Agent",
    description="AI-powered code review service",
    agent_id="did:nvm:code-review-agent",
    plan_id="code-review-plan-id",
    url="https://localhost:8080",
    version="1.0.0"
)

# Start server
async def main():
    executor = CodeReviewExecutor()

    result = payments.a2a["start"](
        agent_card=agent_card,
        executor=executor,
        port=8080,
        expose_agent_card=True,
        async_execution=True
    )

    print(f"A2A Server started on port 8080")
    print(f"Agent card: http://localhost:8080/.well-known/agent.json")

    # Run server
    await result.server.serve()

asyncio.run(main())
```

## Client Usage

Clients interact with the A2A server using the standard A2A protocol:

```python
from payments_py import Payments, PaymentOptions

# Initialize as subscriber
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:subscriber-key", environment="sandbox")
)

# Get access token
token_result = payments.x402.get_x402_access_token(
    plan_id="code-review-plan-id",
    agent_id="did:nvm:code-review-agent"
)
access_token = token_result['accessToken']

# Get A2A client
client = payments.a2a["get_client"](
    agent_url="https://localhost:8080",
    access_token=access_token
)

# Send a task
response = await client.send_task({
    "messages": [{
        "role": "user",
        "parts": [{
            "type": "text",
            "text": "def add(a, b):\n    return a + b"
        }]
    }]
})

print(f"Review result: {response}")
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

result = payments.a2a["start"](
    agent_card=agent_card,
    executor=executor,
    hooks={
        "beforeRequest": before_request,
        "afterRequest": after_request,
        "onError": on_error
    }
)
```

## Error Handling

| Error Code | HTTP Status | Description |
|------------|-------------|-------------|
| -32001 | 401 | Missing Bearer token |
| -32001 | 402 | Payment validation failed |
| -32001 | 402 | Agent ID missing from card |

## Next Steps

- [x402 Protocol](11-x402.md) - Deep dive into x402 payment protocol
- [Validation of Requests](08-validation-of-requests.md) - Manual validation patterns
