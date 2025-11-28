# Nevermined Extension for x402 v2

The **Nevermined extension** enables AI agents to use Nevermined's credit-based payment system with the x402 payment protocol.

This extension follows the x402 v2 extension pattern from the [x402 repository](https://github.com/coinbase/x402/tree/v2-development), specifically the [Bazaar extension](https://github.com/coinbase/x402/tree/v2-development/typescript/packages/extensions/src/bazaar) as a reference implementation.

## Overview

The Nevermined extension allows:
- **Servers** to declare Nevermined payment requirements
- **Clients** to copy extension data in payment payloads
- **Facilitators** to extract and process Nevermined payment info

## Extension Pattern

Like all x402 v2 extensions, Nevermined follows the `info` + `schema` pattern:

```python
{
    "info": {
        "plan_id": "...",
        "agent_id": "...",
        "max_amount": "2",
        "network": "base-sepolia",
        "scheme": "contract"
    },
    "schema": {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {...},
        "required": [...]
    }
}
```

## For Resource Servers

Use the **declare helper** to create extension metadata:

```python
from payments_py.x402.extensions.nevermined import (
    declare_nevermined_extension,
    NEVERMINED
)
from payments_py.x402.types_v2 import (
    PaymentRequiredResponseV2,
    ResourceInfo
)

# Create Nevermined extension
extension = declare_nevermined_extension(
    plan_id="85917684554499762134516240562181895926019634254204202319880150802501990701934",
    agent_id="80918427023170428029540261117198154464497879145267720259488529685089104529015",
    max_amount="2",
    network="base-sepolia",
    scheme="contract",
    environment="sandbox"
)

# Include in PaymentRequired response
response = PaymentRequiredResponseV2(
    x402_version=2,
    resource=ResourceInfo(url="https://api.example.com/data"),
    accepts=[...],  # List of payment requirements
    extensions={
        NEVERMINED: extension
    }
)
```

## For Facilitators

Use the **extract helper** to parse extension data:

```python
from payments_py.x402.extensions.nevermined import extract_nevermined_info

# Extract Nevermined info from payment payload
nvm_info = extract_nevermined_info(payment_payload, payment_requirements)

if nvm_info:
    plan_id = nvm_info["plan_id"]
    agent_id = nvm_info["agent_id"]
    max_amount = nvm_info["max_amount"]
    network = nvm_info["network"]
    
    # Proceed with verification/settlement:
    # 1. Check subscriber balance
    # 2. Order more credits if needed
    # 3. Burn credits on settlement
```

## Extension Flow

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Server Declares Nevermined Extension                        │
└────────────────────────────────────────────────────────────────┘

  declare_nevermined_extension(plan_id, agent_id, max_amount)
  
  PaymentRequired Response:
  {
    "x402Version": 2,
    "resource": {"url": "..."},
    "accepts": [...],
    "extensions": {
      "nevermined": {info, schema}  // ← Extension attached here
    }
  }

┌────────────────────────────────────────────────────────────────┐
│ 2. Client Copies Extension to PaymentPayload                   │
└────────────────────────────────────────────────────────────────┘

  PaymentPayload:
  {
    "x402Version": 2,
    "scheme": "exact",
    "network": "base-sepolia",
    "payload": {...},
    "extensions": {
      "nevermined": {info, schema}  // ← Client copied from PaymentRequired
    }
  }

┌────────────────────────────────────────────────────────────────┐
│ 3. Facilitator Extracts and Processes                          │
└────────────────────────────────────────────────────────────────┘

  nvm_info = extract_nevermined_info(payment_payload)
  
  if nvm_info:
      # Verify subscriber has credits
      # Order more if needed
      # Burn credits on settlement
```

## Backward Compatibility

The extension helpers support both formats:

- **V2**: Extensions in `PaymentPayload.extensions`
- **V1**: Nevermined data in `PaymentRequirements.extra`

This enables seamless migration from v1 to v2.

## API Reference

### Constants

- **`NEVERMINED`**: Extension identifier constant (`"nevermined"`)

### Types

- **`NeverminedInfo`**: Extension info structure
- **`NeverminedExtension`**: Complete extension (info + schema)

### Helpers

#### `declare_nevermined_extension()`

Server helper to create extension metadata.

**Parameters:**
- `plan_id` (str): Nevermined pricing plan ID
- `agent_id` (str): Nevermined AI agent ID
- `max_amount` (str): Maximum credits to burn
- `network` (str): Blockchain network (default: "base-sepolia")
- `scheme` (str): Payment scheme (default: "contract")
- `environment` (str, optional): Nevermined environment
- `subscriber_address` (str, optional): Subscriber address

**Returns:** `NeverminedExtension`

#### `extract_nevermined_info()`

Facilitator helper to extract extension data.

**Parameters:**
- `payment_payload` (dict): Payment payload from client
- `payment_requirements` (dict, optional): For v1 fallback
- `validate` (bool): Whether to validate (default: True)

**Returns:** `NeverminedInfo | None`

#### `validate_nevermined_extension()`

Validation helper using JSON Schema.

**Parameters:**
- `extension` (NeverminedExtension): Extension to validate

**Returns:** `ValidationResult`

## Implementation Notes

This implementation:
- ✅ Follows the x402 v2 extension pattern from TypeScript/Go implementations
- ✅ Provides first-class Python support for x402 extensions
- ✅ Can be contributed back to the x402 ecosystem
- ✅ Maintains backward compatibility with v1

## Contributing

When x402 v2 Python support is officially released, we can contribute this extension implementation upstream. The code is structured to align with the official pattern.

## References

- [x402 v2 Extensions (TypeScript)](https://github.com/coinbase/x402/tree/v2-development/typescript/packages/extensions)
- [Bazaar Extension (Go)](https://github.com/coinbase/x402/tree/v2-development/go/extensions/bazaar)
- [x402 Protocol Specification](https://github.com/coinbase/x402)

