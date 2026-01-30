# Agents

This guide covers how to register and manage AI agents using the Nevermined Payments Python SDK.

## Overview

AI Agents are services that users can access through payment plans. The Agents API allows you to:

- Register new agents with associated payment plans
- Register agents and plans together in a single operation
- Update agent metadata and endpoints
- Manage plan associations

## Agents API

Access the Agents API through `payments.agents`:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Access agents API
agents_api = payments.agents
```

## Register Agents

### Basic Agent Registration

Register an agent and associate it with existing payment plans:

```python
from payments_py.common.types import AgentMetadata, AgentAPIAttributes

# Define agent metadata
agent_metadata = AgentMetadata(
    name="My AI Assistant",
    description="An intelligent assistant that helps with various tasks",
    tags=["ai", "assistant", "productivity"],
    author="Your Company"
)

# Define API configuration
agent_api = AgentAPIAttributes(
    endpoints=[
        {"POST": "https://your-api.com/api/v1/agents/:agentId/tasks"},
        {"GET": "https://your-api.com/api/v1/agents/:agentId/tasks/:taskId"}
    ],
    agent_definition_url="https://your-api.com/api/v1/openapi.json"
)

# List of plan IDs that grant access to this agent
payment_plans = [plan_id_1, plan_id_2]

# Register the agent
result = payments.agents.register_agent(
    agent_metadata=agent_metadata,
    agent_api=agent_api,
    payment_plans=payment_plans
)
print(f"Agent ID: {result['agentId']}")
```

### Register Agent and Plan Together

Create both an agent and a payment plan in a single operation:

```python
from payments_py.common.types import AgentMetadata, AgentAPIAttributes, PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

# Agent configuration
agent_metadata = AgentMetadata(
    name="AI Code Reviewer",
    description="Automated code review assistant",
    tags=["code", "review", "ai"]
)

agent_api = AgentAPIAttributes(
    endpoints=[{"POST": "https://your-api.com/api/v1/review"}],
    agent_definition_url="https://your-api.com/openapi.json"
)

# Plan configuration
plan_metadata = PlanMetadata(
    name="Code Review Plan",
    description="100 code reviews"
)

price_config = get_erc20_price_config(
    amount=50,
    token_address="0xYourTokenAddress",
    receiver=payments.account_address
)

credits_config = get_fixed_credits_config(credits_granted=100)

# Register both in one call
result = payments.agents.register_agent_and_plan(
    agent_metadata=agent_metadata,
    agent_api=agent_api,
    plan_metadata=plan_metadata,
    price_config=price_config,
    credits_config=credits_config,
    access_limit="credits"  # or "time"
)

print(f"Agent ID: {result['agentId']}")
print(f"Plan ID: {result['planId']}")
print(f"Transaction: {result['txHash']}")
```

## Agent Configuration

### AgentMetadata Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `name` | `str` | Yes | Agent display name |
| `description` | `str` | No | Agent description |
| `author` | `str` | No | Author/company name |
| `tags` | `list[str]` | No | Categorization tags |
| `license` | `str` | No | License information |
| `sample_link` | `str` | No | Link to demo/sample |
| `api_description` | `str` | No | API documentation |

### AgentAPIAttributes Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `endpoints` | `list[dict]` | Yes | List of endpoint configurations |
| `agent_definition_url` | `str` | Yes | URL to OpenAPI/MCP/A2A spec |
| `open_endpoints` | `list[str]` | No | Endpoints without auth |
| `auth_type` | `AuthType` | No | Authentication type |

### Endpoint Configuration

Endpoints are defined as dictionaries with HTTP verb as key and URL as value:

```python
agent_api = AgentAPIAttributes(
    endpoints=[
        {"POST": "https://api.example.com/agents/:agentId/tasks"},
        {"GET": "https://api.example.com/agents/:agentId/tasks/:taskId"},
        {"DELETE": "https://api.example.com/agents/:agentId/tasks/:taskId"}
    ],
    agent_definition_url="https://api.example.com/openapi.json"
)
```

The `:agentId` and `:taskId` placeholders will be replaced with actual values during request validation.

## Retrieve Agents

### Get a Single Agent

```python
agent = payments.agents.get_agent(agent_id="your-agent-id")
print(f"Agent name: {agent['name']}")
print(f"Agent endpoints: {agent['endpoints']}")
```

### Get Plans for an Agent

```python
from payments_py.common.types import PaginationOptions

plans = payments.agents.get_agent_plans(
    agent_id="your-agent-id",
    pagination=PaginationOptions(page=1, offset=10)
)
print(f"Associated plans: {plans}")
```

## Update Agents

### Update Agent Metadata

```python
updated_metadata = AgentMetadata(
    name="Updated Agent Name",
    description="Updated description with new features",
    tags=["ai", "updated", "v2"]
)

updated_api = AgentAPIAttributes(
    endpoints=[{"POST": "https://new-api.com/v2/tasks"}],
    agent_definition_url="https://new-api.com/v2/openapi.json"
)

result = payments.agents.update_agent_metadata(
    agent_id="your-agent-id",
    agent_metadata=updated_metadata,
    agent_api=updated_api
)
print(f"Update successful: {result}")
```

## Manage Plan Associations

### Add a Plan to an Agent

```python
result = payments.agents.add_plan_to_agent(
    plan_id="plan-to-add",
    agent_id="your-agent-id"
)
print(f"Plan added: {result}")
```

### Remove a Plan from an Agent

```python
result = payments.agents.remove_plan_from_agent(
    plan_id="plan-to-remove",
    agent_id="your-agent-id"
)
print(f"Plan removed: {result}")
```

## Complete Example

```python
from payments_py import Payments, PaymentOptions
from payments_py.common.types import AgentMetadata, AgentAPIAttributes, PlanMetadata
from payments_py.plans import (
    get_erc20_price_config,
    get_fixed_credits_config,
    get_free_price_config
)

# Initialize
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

ERC20_TOKEN = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
builder_address = payments.account_address

# 1. Create a payment plan first
plan_result = payments.plans.register_credits_plan(
    plan_metadata=PlanMetadata(name="AI Agent Plan"),
    price_config=get_erc20_price_config(20, ERC20_TOKEN, builder_address),
    credits_config=get_fixed_credits_config(100)
)
plan_id = plan_result['planId']

# 2. Register an agent with the plan
agent_result = payments.agents.register_agent(
    agent_metadata=AgentMetadata(
        name="My First AI Agent",
        description="A demo AI agent",
        tags=["demo", "ai"]
    ),
    agent_api=AgentAPIAttributes(
        endpoints=[{"POST": "https://api.example.com/agents/:agentId/tasks"}],
        agent_definition_url="https://api.example.com/openapi.json"
    ),
    payment_plans=[plan_id]
)
agent_id = agent_result['agentId']
print(f"Created agent: {agent_id}")

# 3. Or create both together
combo_result = payments.agents.register_agent_and_plan(
    agent_metadata=AgentMetadata(name="Combo Agent"),
    agent_api=AgentAPIAttributes(
        endpoints=[{"POST": "https://api.example.com/combo"}],
        agent_definition_url="https://api.example.com/openapi.json"
    ),
    plan_metadata=PlanMetadata(name="Combo Plan"),
    price_config=get_free_price_config(),
    credits_config=get_fixed_credits_config(10)
)
print(f"Combo Agent: {combo_result['agentId']}, Plan: {combo_result['planId']}")

# 4. Retrieve agent details
agent = payments.agents.get_agent(agent_id)
print(f"Agent details: {agent}")

# 5. Get associated plans
plans = payments.agents.get_agent_plans(agent_id)
print(f"Agent plans: {plans}")

# 6. Update agent metadata
payments.agents.update_agent_metadata(
    agent_id=agent_id,
    agent_metadata=AgentMetadata(name="Updated Agent Name"),
    agent_api=AgentAPIAttributes(
        endpoints=[{"POST": "https://api.example.com/v2/agents/:agentId/tasks"}],
        agent_definition_url="https://api.example.com/v2/openapi.json"
    )
)
```

## Next Steps

- [Publishing Static Resources](05-publishing-static-resources.md) - Publish files and datasets
- [Querying an Agent](07-querying-an-agent.md) - Learn how to access agents
