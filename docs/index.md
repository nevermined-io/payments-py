# Nevermined Payments Python SDK

The Nevermined Payments Python SDK provides a complete solution for integrating AI agent monetization and access control into your applications.

## Features

- **Payment Plans**: Create and manage credits-based and time-based payment plans
- **AI Agents**: Register and monetize AI agents with flexible pricing models
- **X402 Protocol**: Industry-standard payment verification and settlement
- **MCP Integration**: Build monetized MCP (Model Context Protocol) servers
- **A2A Protocol**: Agent-to-Agent communication with payment support

## Quick Start

```python
from payments_py import Payments, PaymentOptions

# Initialize the SDK
payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="your-nvm-api-key",
        environment="sandbox"
    )
)

# Create a payment plan
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

plan_metadata = PlanMetadata(name="Basic Plan", description="100 credits plan")
price_config = get_erc20_price_config(20, ERC20_TOKEN_ADDRESS, builder_address)
credits_config = get_fixed_credits_config(100)

result = payments.plans.register_credits_plan(plan_metadata, price_config, credits_config)
print(f"Plan created: {result['planId']}")
```

## Documentation Structure

### API Reference

Step-by-step guides for using the SDK:

1. [Installation](api/01-installation.md) - How to install the library
2. [Initializing the Library](api/02-initializing-the-library.md) - Configuration and setup
3. [Payment Plans](api/03-payment-plans.md) - Create and manage payment plans
4. [Agents](api/04-agents.md) - Register and manage AI agents
5. [Publishing Static Resources](api/05-publishing-static-resources.md) - Publish files and datasets
6. [Payments and Balance](api/06-payments-and-balance.md) - Order plans and check balances
7. [Querying an Agent](api/07-querying-an-agent.md) - Get access tokens and make requests
8. [Validation of Requests](api/08-validation-of-requests.md) - Validate incoming requests
9. [MCP Integration](api/09-mcp-integration.md) - Build MCP servers with payments
10. [A2A Integration](api/10-a2a-integration.md) - Agent-to-Agent protocol integration
11. [x402 Protocol](api/11-x402.md) - Payment permissions and settlement

### Reference

Detailed API documentation:

- [Payments Class](reference/payments.md) - Main SDK class reference
- [Data Models](reference/data_models.md) - Type definitions and models
- [Environments](reference/environments.md) - Environment configuration

## Support

- [GitHub Repository](https://github.com/nevermined-io/payments-py)
- [Nevermined Documentation](https://docs.nevermined.app)
- [Nevermined App](https://nevermined.app)
