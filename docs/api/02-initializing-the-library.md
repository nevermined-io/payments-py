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

# The environment is derived from your API key's prefix — just pass the key.
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="sandbox:your-api-key-here",
    )
)

# Verify initialization
print(f"Connected to: {payments.environment.backend}")
print(f"Account: {payments.account_address}")
```

!!! note "`environment` is deprecated"
    The `environment` option is **deprecated**. The SDK now derives the
    environment from the API-key prefix (`<prefix>:<jwt>`) — a key minted for
    sandbox starts with `sandbox:`, for production with `live:`, and so on. When
    the prefix is recognized it always wins; passing `environment` is ignored
    (with a warning). It is still accepted only as a fallback for local/custom
    keys whose prefix the SDK doesn't recognize (see
    [Custom Environment](#custom-environment)).

### Using Environment Variables

```python
import os
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key=os.getenv("NVM_API_KEY"),
    )
)
```

## Configuration Options

The `PaymentOptions` class accepts the following parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `nvm_api_key` | `str` | Yes | Your Nevermined API key (its prefix sets the environment) |
| `environment` | `str` | No | **Deprecated.** Derived from the API-key prefix; only used as a fallback for unrecognized (local/custom) prefixes (see below) |
| `app_id` | `str` | No | Application identifier |
| `version` | `str` | No | Application version |
| `api_version` | `str` | No | Backend API version sent as the `Nevermined-Version` header. Defaults to the version this SDK release targets (see below) |
| `headers` | `dict` | No | Additional HTTP headers |
| `return_url` | `str` | No | Return URL (browser mode only) |

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="sandbox:your-api-key",
        app_id="my-app",
        version="1.0.0",
        headers={"X-Custom-Header": "value"}
    )
)
```

### API Version Pinning

Every request the SDK sends to the Nevermined backend carries a
`Nevermined-Version` header declaring which backend API version
(`MAJOR.MINOR`) the SDK was built and tested against. You normally don't
need to touch this — the SDK pins the right version for you. To target a
different backend contract explicitly:

```python
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="sandbox:your-api-key",
        api_version="1.1",  # override the pinned backend API version
    )
)
```

See the [API versioning reference](https://docs.nevermined.app/api-reference/versioning)
for the list of versions and the changes between them.

## Environments

The environment is determined by your API key's prefix — you don't select it
explicitly. The prefix-to-environment mapping is:

| API-key prefix | Environment |
|----------------|-------------|
| `sandbox:` | `sandbox` |
| `live:` | `live` |
| `sandbox-staging:` | `staging_sandbox` |
| `live-staging:` | `staging_live` |

### Sandbox Environment (Testing)

A key minted for sandbox starts with `sandbox:`:

```python
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="sandbox:your-api-key",
    )
)
```

- Backend: `https://api.sandbox.nevermined.app`
- Proxy: `https://proxy.sandbox.nevermined.app`
- Uses test tokens and test networks

### Live Environment (Production)

A key minted for production starts with `live:`:

```python
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="live:your-api-key",
    )
)
```

- Backend: `https://api.live.nevermined.app`
- Proxy: `https://proxy.live.nevermined.app`
- Uses real tokens and mainnet networks

### Custom Environment

For self-hosted or local development setups, the API key's prefix won't be one
the SDK recognizes, so it falls back to the (still-accepted) `environment`
option. Pass `environment="custom"` to point the SDK at URLs from environment
variables:

```python
import os

# Set environment variables first
os.environ["NVM_BACKEND_URL"] = "http://localhost:3001"
os.environ["NVM_PROXY_URL"] = "http://localhost:443"

payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="local:your-api-key",
        environment="custom",  # fallback for unrecognized key prefixes
    )
)
```

### Available Environments

| Environment | Description |
|-------------|-------------|
| `sandbox` | Production sandbox (testing) |
| `live` | Production mainnet |
| `staging_sandbox` | Staging sandbox |
| `staging_live` | Staging mainnet |
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
