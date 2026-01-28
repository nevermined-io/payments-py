# Initializing the Library

This guide explains how to import, configure, and initialize the Nevermined Payments Python SDK.

## Get the NVM API Key

Before using the SDK, you need a Nevermined API Key:

1. Go to the [Nevermined App](https://nevermined.app)
2. Sign in or create an account
3. Navigate to **Settings** > **API Keys**
4. Generate a new API key
5. Copy the key (format: `nvm:xxxxxxxx...`)

!!! warning "Keep your API key secure"
    Never commit your API key to version control. Use environment variables or a secrets manager.

## Import and Initialize

### Basic Initialization

```python
from payments_py import Payments, PaymentOptions

# Initialize with API key and environment
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="nvm:your-api-key-here",
        environment="sandbox"
    )
)

# Verify initialization
print(f"Connected to: {payments.environment.backend}")
print(f"Account: {payments.account_address}")
```

### Using Environment Variables

```python
import os
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key=os.getenv("NVM_API_KEY"),
        environment=os.getenv("NVM_ENVIRONMENT", "sandbox")
    )
)
```

## Configuration Options

The `PaymentOptions` class accepts the following parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nvm_api_key` | `str` | Yes | Your Nevermined API key |
| `environment` | `str` | Yes | Environment name (see below) |
| `app_id` | `str` | No | Application identifier |
| `version` | `str` | No | Application version |
| `headers` | `dict` | No | Additional HTTP headers |
| `return_url` | `str` | No | Return URL (browser mode only) |

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="nvm:your-api-key",
        environment="sandbox",
        app_id="my-app",
        version="1.0.0",
        headers={"X-Custom-Header": "value"}
    )
)
```

## Environments

### Sandbox Environment (Testing)

Use `sandbox` for development and testing:

```python
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="nvm:your-api-key",
        environment="sandbox"
    )
)
```

- Backend: `https://api.sandbox.nevermined.app`
- Proxy: `https://proxy.sandbox.nevermined.app`
- Uses test tokens and test networks

### Live Environment (Production)

Use `live` for production:

```python
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="nvm:your-api-key",
        environment="live"
    )
)
```

- Backend: `https://api.live.nevermined.app`
- Proxy: `https://proxy.live.nevermined.app`
- Uses real tokens and mainnet networks

### Custom Environment

For self-hosted or development setups:

```python
import os

# Set environment variables first
os.environ["NVM_BACKEND_URL"] = "http://localhost:3001"
os.environ["NVM_PROXY_URL"] = "http://localhost:443"

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="nvm:your-api-key",
        environment="custom"
    )
)
```

### Available Environments

| Environment | Description |
|-------------|-------------|
| `sandbox` | Production sandbox (testing) |
| `live` | Production mainnet |
| `staging_sandbox` | Staging sandbox (internal) |
| `staging_live` | Staging mainnet (internal) |
| `custom` | Custom URLs via environment variables |

## Accessing Sub-APIs

The initialized `Payments` object provides access to specialized APIs:

```python
# Plans API - manage payment plans
payments.plans.register_credits_plan(...)
payments.plans.get_plan(plan_id)
payments.plans.get_plan_balance(plan_id)

# Agents API - manage AI agents
payments.agents.register_agent(...)
payments.agents.get_agent(agent_id)

# Facilitator API - x402 verification/settlement
payments.facilitator.verify_permissions(...)
payments.facilitator.settle_permissions(...)

# X402 Token API - generate access tokens
payments.x402.get_x402_access_token(plan_id, agent_id)

# MCP Integration
payments.mcp.register_tool(...)
await payments.mcp.start(config)

# A2A Integration
payments.a2a["start"](agent_card=card, executor=executor)
```

## Error Handling

The SDK raises `PaymentsError` for API errors:

```python
from payments_py.common.payments_error import PaymentsError

try:
    result = payments.plans.get_plan("invalid-id")
except PaymentsError as e:
    print(f"Error: {e.message}")
    print(f"Code: {e.code}")
```

## Next Steps

Now that you have initialized the SDK, proceed to:

- [Payment Plans](03-payment-plans.md) - Create payment plans
- [Agents](04-agents.md) - Register AI agents
