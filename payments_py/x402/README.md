# X402 Payment Protocol Module

This module provides comprehensive support for the X402 Payment Protocol, enabling AI agents to implement payment-required services with Nevermined.

## Overview

The X402 protocol extension allows AI agents to:

- Request payment for services using cryptographic access tokens
- Verify subscriber permissions before providing services
- Settle (burn) credits on-chain after service delivery
- Support multiple blockchain networks and payment schemes

## Components

### Types (`types.py`)

Pydantic models for X402 protocol messages:

- **`PaymentRequirements`**: Specifies what payment is needed (plan, agent, amount, network)
- **`NvmPaymentRequiredResponse`**: Payment-required response sent to clients
- **`PaymentPayload`**: Payment credentials sent from client to merchant
- **`SessionKeyPayload`**: Contains the X402 access token
- **`VerifyResponse`**: Result of payment verification
- **`SettleResponse`**: Result of payment settlement

### Networks (`networks.py`)

Supported blockchain networks:

- `base` - Base mainnet
- `base-sepolia` - Base Sepolia testnet

### Schemes (`schemes.py`)

Supported payment schemes:

- `fixed` - Fixed price payments
- `dynamic` - Dynamic pricing
- `contract` - Smart contract-based payments

### Facilitator (`facilitator.py`)

**`NeverminedFacilitator`**: Main class for verifying and settling X402 payments.

```python
from payments_py.x402 import NeverminedFacilitator

# Initialize
facilitator = NeverminedFacilitator(
    nvm_api_key="nvm:your-key",
    environment="sandbox"
)

# Verify payment
verify_result = await facilitator.verify(payment_payload, requirements)

# Settle payment
if verify_result.is_valid:
    settle_result = await facilitator.settle(payment_payload, requirements)
```

### Token API (`token.py`)

**`X402TokenAPI`**: API class for X402 access token generation.

**Helper functions:**

- `generate_x402_access_token()`: Generate token (returns string)
- `get_x402_token_response()`: Generate token (returns full response dict)

```python
from payments_py import Payments, PaymentOptions
from payments_py.x402 import X402TokenAPI, generate_x402_access_token

# Initialize payments
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Option 1: Via payments instance (recommended)
token_result = payments.x402.get_x402_access_token(plan_id, agent_id)
token = token_result["accessToken"]

# Option 2: Direct API access
token_api = X402TokenAPI.get_instance(payments.options)
token = generate_x402_access_token(token_api, plan_id, agent_id)

```

## Usage Example

### Complete Flow

```python
from payments_py import Payments, PaymentOptions
from payments_py.x402 import (
    NeverminedFacilitator,
    generate_x402_access_token,
    PaymentPayload,
    PaymentRequirements,
    SessionKeyPayload,
)

# 1. Initialize (Subscriber Side)
subscriber_payments = Payments.get_instance(
    PaymentOptions(
        nvm_api_key="nvm:subscriber-key",
        environment="sandbox"
    )
)

# 2. Generate X402 access token
token = generate_x402_access_token(
    subscriber_payments,
    plan_id="your-plan-id",
    agent_id="your-agent-id"
)

# 3. Create payment payload
payment_payload = PaymentPayload(
    nvm_version=1,
    scheme="contract",
    network="base-sepolia",
    payload=SessionKeyPayload(session_key=token)
)

# 4. Initialize Facilitator (Merchant Side)
facilitator = NeverminedFacilitator(
    nvm_api_key="nvm:merchant-key",
    environment="sandbox"
)

# 5. Create payment requirements
requirements = PaymentRequirements(
    plan_id="your-plan-id",
    agent_id="your-agent-id",
    max_amount="2",
    network="base-sepolia",
    scheme="contract",
    extra={"subscriber_address": "0x..."}
)

# 6. Verify payment
verify_result = await facilitator.verify(payment_payload, requirements)

if verify_result.is_valid:
    # 7. Provide service
    result = provide_service()

    # 8. Settle payment (burn credits)
    settle_result = await facilitator.settle(payment_payload, requirements)

    if settle_result.success:
        print(f"Payment settled! TX: {settle_result.transaction}")
    else:
        print(f"Settlement failed: {settle_result.error_reason}")
else:
    print(f"Payment invalid: {verify_result.invalid_reason}")
```

## Integration with A2A

The X402 module integrates seamlessly with Google's A2A (Agent-to-Agent) protocol:

```python
from x402.server import x402ServerExecutor
from payments_py.x402 import NeverminedFacilitator

# Initialize facilitator
facilitator = NeverminedFacilitator(
    nvm_api_key="nvm:merchant-key",
    environment="sandbox"
)

# Wrap your agent executor with X402 payment handling
agent_executor = x402ServerExecutor(
    base_executor=your_agent_executor,
    facilitator=facilitator
)
```

## API Reference

### X402TokenAPI

API class for generating X402 access tokens.

#### `get_x402_access_token(plan_id: str, agent_id: str) -> Dict[str, Any]`

Generate X402 access token for a plan and agent.

**Parameters:**

- `plan_id`: Payment plan identifier
- `agent_id`: AI agent identifier

**Returns:** Dictionary with `accessToken` key and metadata

**Usage:**

```python
# Via payments instance
token_result = payments.x402.get_x402_access_token(plan_id, agent_id)

# Direct API usage
token_api = X402TokenAPI.get_instance(options)
token_result = token_api.get_x402_access_token(plan_id, agent_id)
```

### NeverminedFacilitator

High-level facilitator for payment verification and settlement.

#### `__init__(nvm_api_key: str, environment: str = "sandbox")`

Initialize the facilitator.

**Parameters:**

- `nvm_api_key`: Nevermined API key (format: "nvm:...")
- `environment`: Environment name ("sandbox", "staging", "production")

#### `async verify(payload: PaymentPayload, requirements: PaymentRequirements) -> VerifyResponse`

Verify payment without settling.

**Parameters:**

- `payload`: Payment payload with X402 access token
- `requirements`: Payment requirements including subscriber address

**Returns:** `VerifyResponse` with `is_valid` boolean

#### `async settle(payload: PaymentPayload, requirements: PaymentRequirements) -> SettleResponse`

Settle payment by burning credits on-chain.

**Parameters:**

- `payload`: Payment payload with X402 access token
- `requirements`: Payment requirements including subscriber address

**Returns:** `SettleResponse` with `success` boolean and transaction hash

### Token Utility Functions

#### `generate_x402_access_token(token_api: X402TokenAPI, plan_id: str, agent_id: str) -> str`

Generate X402 access token (convenience function).

**Returns:** Token string

**Usage:**

```python
token_api = X402TokenAPI.get_instance(payments.options)
token = generate_x402_access_token(token_api, plan_id, agent_id)
```

#### `get_x402_token_response(token_api: X402TokenAPI, plan_id: str, agent_id: str) -> Dict`

Generate X402 access token with full response.

**Returns:** Response dictionary with token and metadata

**Usage:**

```python
token_api = X402TokenAPI.get_instance(payments.options)
response = get_x402_token_response(token_api, plan_id, agent_id)
token = response["accessToken"]
```

## Environment Variables

- `NVM_API_KEY_SERVER`: Merchant/agent API key for verification and settlement
- `NVM_API_KEY_CLIENT`: Subscriber API key for token generation
- `NVM_ENVIRONMENT`: Environment name (sandbox/staging/production)

## Error Handling

All operations can raise `PaymentsError` on failure:

```python
from payments_py.common.payments_error import PaymentsError

try:
    token = generate_x402_access_token(payments, plan_id, agent_id)
except PaymentsError as e:
    print(f"Token generation failed: {e}")
```

## Migration from x402_a2a.nvm

If migrating from the `x402_a2a.nvm` module:

**Before:**

```python
from x402_a2a.nvm import NeverminedFacilitator, PaymentRequirements
```

**After:**

```python
from payments_py.x402 import NeverminedFacilitator, PaymentRequirements
```

The API is identical, just the import path changed.

## See Also

- [Nevermined Documentation](https://docs.nevermined.io/)
- [X402 Protocol Specification](https://github.com/google-a2a/a2a-x402)
- [A2A Protocol](https://github.com/google-a2a/a2a)
