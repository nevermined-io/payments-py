"""
Nevermined Extension for x402 v2

This extension enables payment management using Nevermined's credit-based system
with AI agents following the x402 payment protocol.

## For Resource Servers

Use the declare helper to create extension metadata:

```python
from payments_py.x402.extensions.nevermined import (
    declare_nevermined_extension,
    NEVERMINED
)
from payments_py.x402.types_v2 import PaymentRequiredResponseV2, ResourceInfo

extension = declare_nevermined_extension(
    plan_id="85917684554499762134516240562181895926019634254204202319880150802501990701934",
    agent_id="80918427023170428029540261117198154464497879145267720259488529685089104529015",
    max_amount="2",
    network="base-sepolia",
    scheme="contract"
)

response = PaymentRequiredResponseV2(
    x402_version=2,
    resource=ResourceInfo(url="https://api.example.com/resource"),
    accepts=[...],
    extensions={
        NEVERMINED: extension
    }
)
```

## For Facilitators

Use the extract helper to parse extension data:

```python
from payments_py.x402.extensions.nevermined import extract_nevermined_info

nvm_info = extract_nevermined_info(payment_payload, payment_requirements)

if nvm_info:
    plan_id = nvm_info["plan_id"]
    agent_id = nvm_info["agent_id"]
    max_amount = nvm_info["max_amount"]

    # Proceed with verification/settlement
    # - Check subscriber balance
    # - Order credits if needed
    # - Burn credits on settlement
```

## Extension Flow

```
1. Server declares Nevermined extension in PaymentRequired
   ↓
2. Client copies extension to PaymentPayload
   ↓
3. Facilitator extracts Nevermined info
   ↓
4. Facilitator verifies subscriber has credits
   ↓
5. Facilitator settles by burning credits
```

## Backward Compatibility

This extension supports both v2 (extensions field) and v1 (extra field) formats
for seamless migration.
"""

from .types import (
    NEVERMINED,
    nevermined_extension_key,
    NeverminedInfo,
    NeverminedExtension,
)
from .declare import declare_nevermined_extension
from .extract import extract_nevermined_info, extract_all_nevermined_plans
from .validate import validate_nevermined_extension, ValidationResult

__all__ = [
    # Constants
    "NEVERMINED",
    "nevermined_extension_key",
    # Types
    "NeverminedInfo",
    "NeverminedExtension",
    # Helpers
    "declare_nevermined_extension",
    "extract_nevermined_info",
    "extract_all_nevermined_plans",
    "validate_nevermined_extension",
    "ValidationResult",
]
