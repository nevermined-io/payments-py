# X402 Module Structure

## Complete Module Layout

```
payments_py/x402/
├── __init__.py              # Public API exports
├── types.py                 # X402 protocol Pydantic models
├── networks.py              # Supported blockchain networks
├── schemes.py               # Supported payment schemes  
├── facilitator.py           # NeverminedFacilitator (high-level wrapper)
├── facilitator_api.py       # FacilitatorAPI (low-level HTTP API)
├── token.py                 # X402 token generation utilities
├── README.md                # Complete documentation
└── STRUCTURE.md             # This file
```

## File Descriptions

### `__init__.py` (67 lines)
Public API exports for the entire X402 module. Exposes:
- All types (PaymentRequirements, PaymentPayload, etc.)
- Constants (SupportedNetworks, SupportedSchemes)
- Both facilitator implementations
- Token generation utilities

### `types.py` (132 lines)
Pydantic models for X402 protocol:
- `PaymentRequirements`: What payment is needed
- `NvmPaymentRequiredResponse`: Payment-required response
- `PaymentPayload`: Payment credentials from client
- `SessionKeyPayload`: X402 access token wrapper
- `VerifyResponse`: Verification result
- `SettleResponse`: Settlement result

### `networks.py` (5 lines)
Supported blockchain networks:
```python
SupportedNetworks = Literal["base", "base-sepolia"]
```

### `schemes.py` (5 lines)
Supported payment schemes:
```python
SupportedSchemes = Literal["fixed", "dynamic", "contract"]
```

### `facilitator.py` (228 lines)
**NeverminedFacilitator** - High-level facilitator class:
- Implements `async verify()` and `async settle()`
- Uses FacilitatorAPI internally
- Handles errors gracefully
- Provides clean, typed API for X402 operations
- **Use this for most applications**

### `facilitator_api.py` (203 lines)
**FacilitatorAPI** - Low-level HTTP API class:
- Direct REST API calls to Nevermined backend
- Used by `NeverminedFacilitator` and `Payments.facilitator`
- Returns raw dict responses
- **Use this for advanced/custom integrations**

### `token.py` (104 lines)
Token generation utilities:
- `generate_x402_access_token()`: Get token string (convenience)
- `get_x402_token_response()`: Get full response dict
- Wraps `AgentsAPI.get_x402_access_token()`

### `README.md` (311 lines)
Comprehensive documentation:
- Overview and architecture
- Component descriptions
- Complete usage examples
- API reference
- Migration guide from x402_a2a.nvm
- Integration with A2A protocol

## Usage Patterns

### Pattern 1: High-Level (Recommended)
```python
from payments_py.x402 import NeverminedFacilitator, generate_x402_access_token

# For subscribers: Generate token
token = generate_x402_access_token(payments, plan_id, agent_id)

# For merchants: Verify & settle
facilitator = NeverminedFacilitator(nvm_api_key="nvm:key", environment="sandbox")
verify_result = await facilitator.verify(payload, requirements)
settle_result = await facilitator.settle(payload, requirements)
```

### Pattern 2: Through Payments Instance
```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:key", environment="sandbox")
)

# Low-level API access
verification = payments.facilitator.verify_permissions(
    plan_id, max_amount, token, subscriber_address
)
```

### Pattern 3: Direct API (Advanced)
```python
from payments_py.x402 import FacilitatorAPI
from payments_py.common.types import PaymentOptions

api = FacilitatorAPI.get_instance(
    PaymentOptions(nvm_api_key="nvm:key", environment="sandbox")
)

# Direct API calls (returns dicts)
result = api.verify_permissions(plan_id, max_amount, token, subscriber_address)
```

## Design Principles

1. **Layered Architecture**:
   - `FacilitatorAPI`: HTTP layer (dict I/O)
   - `NeverminedFacilitator`: Business logic layer (typed I/O)
   - Token utilities: Convenience layer

2. **Type Safety**:
   - All models are Pydantic-validated
   - Strong typing throughout
   - Clear error messages

3. **Separation of Concerns**:
   - Token generation: Client-side operation
   - Verification: Merchant checks before service
   - Settlement: Merchant finalizes after service

4. **Framework Agnostic**:
   - No web framework dependencies
   - Works with any async Python application
   - Easy integration with A2A, FastAPI, Flask, etc.

## Integration Points

### With Payments Core
```python
payments.facilitator  # -> FacilitatorAPI instance
```

### With A2A Server
```python
from x402.server import x402ServerExecutor
from payments_py.x402 import NeverminedFacilitator

executor = x402ServerExecutor(base_executor, facilitator)
```

### With A2A Client
```python
from x402.client import x402ClientAgent
from payments_py.x402 import generate_x402_access_token

agent = x402ClientAgent(generate_token_fn)
```

## Backward Compatibility

All previous `payments_py.api.facilitator_api` imports still work:
```python
# Still works (backwards compatible)
from payments_py import FacilitatorAPI

# New preferred way
from payments_py.x402 import FacilitatorAPI
```

## Dependencies

The x402 module only depends on:
- `payments_py.common.*`: Shared types and errors
- `payments_py.api.base_payments`: Base API class
- `payments_py.api.nvm_api`: API URL constants
- External: `requests`, `pydantic`

No dependency on:
- ❌ `x402-a2a` package
- ❌ External facilitator implementations
- ❌ Blockchain SDKs (handled by backend)

## Testing

Test files should be in `tests/x402/`:
```
tests/x402/
├── test_types.py
├── test_facilitator.py
├── test_facilitator_api.py
└── test_token.py
```

## Maintenance

- All X402 code is now in one module
- Easy to version and release
- Clear ownership (payments-py team)
- Documented and tested

