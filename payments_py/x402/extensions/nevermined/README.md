# Nevermined Extension for x402 v2

The **Nevermined extension** enables AI agents to use Nevermined's various payment methods with the x402 payment protocol.

This extension follows the x402 v2 extension pattern from the [x402 repository](https://github.com/coinbase/x402/tree/v2-development), specifically the [Bazaar extension](https://github.com/coinbase/x402/tree/v2-development/typescript/packages/extensions/src/bazaar) as a reference implementation.

## Overview

The Nevermined extension allows:

- **Servers** to declare Nevermined payment requirements (single or multiple plans)
- **Clients** to copy extension data in payment payloads
- **Facilitators** to extract and process Nevermined payment info

### Multiple Payment Plans

Servers can offer multiple Nevermined payment plans using **qualified extension keys**:

- `nevermined:credits` - Credits-based plan
- `nevermined:payasyougo` - Pay-as-you-go plan
- `nevermined:credits-basic` - Basic credits plan
- `nevermined:credits-premium` - Premium credits plan

Each plan is a separate extension entry in the `extensions` dictionary.

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

### Single Payment Plan

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
        NEVERMINED: extension  # Single plan
    }
)
```

### Multiple Payment Plans

Offer multiple payment options using **qualified extension keys**:

```python
from payments_py.x402.extensions.nevermined import (
    declare_nevermined_extension,
    nevermined_extension_key
)

# Create extensions for different plans
credits_extension = declare_nevermined_extension(
    plan_id="credits-plan-id",
    agent_id="your-agent-id",
    max_amount="2",
    network="base-sepolia",
    scheme="contract"
)

payasyougo_extension = declare_nevermined_extension(
    plan_id="payasyougo-plan-id",
    agent_id="your-agent-id",
    max_amount="1",
    network="base-sepolia",
    scheme="contract"
)

# Include multiple plans with qualified keys
response = PaymentRequiredResponseV2(
    x402_version=2,
    resource=ResourceInfo(url="https://api.example.com/data"),
    accepts=[...],
    extensions={
        nevermined_extension_key("credits"): credits_extension,
        nevermined_extension_key("payasyougo"): payasyougo_extension
    }
)
```

The `nevermined_extension_key()` helper creates qualified keys like `"nevermined:credits"`, `"nevermined:payasyougo"`, etc.

## For Facilitators

### Single Plan Extraction

Use the **extract helper** to parse extension data:

```python
from payments_py.x402.extensions.nevermined import extract_nevermined_info

# Extract Nevermined info from payment payload (single plan)
nvm_info = extract_nevermined_info(payment_payload, payment_requirements)

if nvm_info:
    plan_id = nvm_info["plan_id"]
    agent_id = nvm_info["agent_id"]
    max_amount = nvm_info["max_amount"]
    network = nvm_info["network"]
    extension_key = nvm_info["extension_key"]  # e.g., "nevermined:credits"

    # Proceed with verification/settlement:
    # 1. Check subscriber balance
    # 2. Order more credits if needed
    # 3. Burn credits on settlement
```

### Multiple Plans Extraction

Extract all available Nevermined plans:

```python
from payments_py.x402.extensions.nevermined import extract_all_nevermined_plans

# Extract all Nevermined plans from payment payload
plans = extract_all_nevermined_plans(payment_payload)

for plan in plans:
    print(f"Plan: {plan['extension_key']}")
    print(f"  Plan ID: {plan['plan_id']}")
    print(f"  Agent ID: {plan['agent_id']}")
    print(f"  Max Amount: {plan['max_amount']}")
    print(f"  Network: {plan['network']}")

# Example output:
# Plan: nevermined:credits
#   Plan ID: 123...
#   Agent ID: 456...
#   Max Amount: 2
#   Network: base-sepolia
# Plan: nevermined:payasyougo
#   Plan ID: 789...
#   Agent ID: 456...
#   Max Amount: 1
#   Network: base-sepolia
```

**Note:** Plan names can be fetched from the Nevermined API using the `plan_id`:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Get plan details including name
plan_details = payments.plans.get_plan(plan_id=plan["plan_id"])
plan_name = plan_details.get("name", "Unnamed Plan")
```

## Extension Flow

### Single Plan Flow

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
    "scheme": "contract",
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

### Multiple Plans Flow

```
┌────────────────────────────────────────────────────────────────┐
│ 1. Server Declares Multiple Nevermined Extensions              │
└────────────────────────────────────────────────────────────────┘

  PaymentRequired Response:
  {
    "x402Version": 2,
    "resource": {"url": "..."},
    "accepts": [...],
    "extensions": {
      "nevermined:credits": {info, schema},      // ← Plan 1
      "nevermined:payasyougo": {info, schema}    // ← Plan 2
    }
  }

┌────────────────────────────────────────────────────────────────┐
│ 2. Client Selects and Copies ONE Extension                     │
└────────────────────────────────────────────────────────────────┘

  // User selects "pay-as-you-go" plan

  PaymentPayload:
  {
    "x402Version": 2,
    "scheme": "contract",
    "network": "base-sepolia",
    "payload": {...},
    "extensions": {
      "nevermined:payasyougo": {info, schema}  // ← Only selected plan
    }
  }

┌────────────────────────────────────────────────────────────────┐
│ 3. Facilitator Extracts Selected Plan                          │
└────────────────────────────────────────────────────────────────┘

  nvm_info = extract_nevermined_info(payment_payload)
  # Returns info for "nevermined:payasyougo" plan

  # Or extract all available plans from PaymentRequired
  all_plans = extract_all_nevermined_plans(payment_required_response)
  # Returns list of all plan options for display to user
```

## Backward Compatibility

The extension helpers support both formats:

- **V2**: Extensions in `PaymentPayload.extensions`
- **V1**: Nevermined data in `PaymentRequirements.extra`

This enables seamless migration from v1 to v2.

## API Reference

### Constants

- **`NEVERMINED`**: Base extension identifier constant (`"nevermined"`)

### Types

- **`NeverminedInfo`**: Extension info structure (TypedDict)

  - `plan_id` (str): Nevermined pricing plan ID
  - `agent_id` (str): Nevermined AI agent ID
  - `max_amount` (str): Maximum credits to burn
  - `network` (str): Blockchain network
  - `scheme` (str): Payment scheme
  - `environment` (str, optional): Nevermined environment
  - `subscriber_address` (str, optional): Subscriber address
  - `extension_key` (str): Qualified extension key (e.g., "nevermined:credits")

- **`NeverminedExtension`**: Complete extension (info + schema)

### Helpers

#### `nevermined_extension_key(plan_type: str) -> str`

Generate a qualified extension key for a specific plan type.

```python
key = nevermined_extension_key("credits")       # "nevermined:credits"
key = nevermined_extension_key("payasyougo")    # "nevermined:payasyougo"
key = nevermined_extension_key("credits-basic") # "nevermined:credits-basic"
```

**Parameters:**

- `plan_type` (str): Plan type identifier (e.g., "credits", "payasyougo")

**Returns:** Qualified extension key string

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

**Note:** Plan name is NOT included in the extension. Fetch it from the Nevermined API using `payments.plans.get_plan(plan_id)`.

#### `extract_nevermined_info()`

Facilitator helper to extract extension data (single plan).

**Parameters:**

- `payment_payload` (dict): Payment payload from client
- `payment_requirements` (dict, optional): For v1 fallback
- `validate` (bool): Whether to validate (default: True)

**Returns:** `NeverminedInfo | None`

**Behavior:**

- Looks for any extension key starting with `"nevermined:"` or `"nevermined"` exactly
- Returns the first match found
- Includes `extension_key` in returned info

#### `extract_all_nevermined_plans()`

Extract all Nevermined plans from a payment response (multiple plans).

```python
plans = extract_all_nevermined_plans(payment_required_response)
# Returns: List[NeverminedInfo]
```

**Parameters:**

- `payment_response` (dict): PaymentRequired response with extensions

**Returns:** `List[NeverminedInfo]` - List of all Nevermined plans found

**Use Case:** Present multiple payment options to users for selection.

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
