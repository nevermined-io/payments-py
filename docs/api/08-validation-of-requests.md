# Request Validation

This guide explains how AI agents can validate incoming requests using the Nevermined Payments Python SDK.

## Overview

When an agent receives a request, it needs to:

1. Extract the x402 access token from the request
2. Verify the subscriber has valid permissions
3. Optionally settle (burn) credits after processing

The SDK provides the Facilitator API for these operations.

## Receiving Requests

Agents receive requests with the x402 access token in the `payment-signature` header (per [x402 v2 HTTP transport spec](https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md)):

```python
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/tasks', methods=['POST'])
def handle_task():
    # Extract x402 token from payment-signature header
    x402_token = request.headers.get('payment-signature', '')

    if not x402_token:
        return jsonify({'error': 'Missing payment-signature header'}), 402

    # Validate and process...
```

## Validating Requests with Facilitator

### Build Payment Required Object

First, build the payment requirement specification:

```python
from payments_py.x402.helpers import build_payment_required

payment_required = build_payment_required(
    plan_id="your-plan-id",
    endpoint="https://your-api.com/tasks",
    agent_id="your-agent-id",
    http_verb="POST"
)
```

### Verify Permissions

Check if the subscriber has valid permissions without burning credits:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:agent-key", environment="sandbox")
)

# Verify the request
verification = payments.facilitator.verify_permissions(
    payment_required=payment_required,
    x402_access_token=access_token,
    max_amount="1"  # Optional: max credits to verify
)

if verification.is_valid:
    print("Request is valid!")
    print(f"Payer: {verification.payer}")
else:
    print(f"Invalid request: {verification.invalid_reason}")
```

### Settle Permissions

After successfully processing a request, burn the credits:

```python
settlement = payments.facilitator.settle_permissions(
    payment_required=payment_required,
    x402_access_token=access_token,
    max_amount="1"  # Credits to burn
)

if settlement.success:
    # Read `billing_model` before the credit fields — see "Was the buyer charged?" below
    if settlement.billing_model == "pay-as-you-go":
        print(f"Charged, reference: {settlement.order_tx or settlement.transaction}")
    else:
        print(f"Credits redeemed: {settlement.credits_redeemed}")
    print(f"Transaction: {settlement.transaction}")
```

### Was the buyer charged?

`settlement.success` tells you the settle worked. What to check **in addition** depends on
`settlement.billing_model`:

| `billing_model` | Success criterion | Credit fields |
| --------------- | ----------------- | ------------- |
| `credits` | `success` and `int(credits_redeemed) > 0` | `credits_redeemed` is the amount burned, `remaining_balance` what is left |
| `pay-as-you-go` | `success` **and** a non-empty `order_tx` (fiat rails) / `transaction` (crypto rails) | always the string `"0"` — no balance exists on this plan shape |

```python
settled = settlement.success and (
    bool(settlement.order_tx or settlement.transaction)
    if settlement.billing_model == "pay-as-you-go"
    else int(settlement.credits_redeemed or "0") > 0
)
```

Two things make this easy to get wrong:

- **Do not gate on `credits_redeemed` without reading `billing_model` first.** A pay-as-you-go
  plan holds no credit balance, so `credits_redeemed > 0` can never hold there — a real charge
  reads as a decline. On a card rail that invites a retry of a payment that already succeeded,
  and repeated attempts feed issuer fraud scoring.
- **These fields are strings.** `"0"` is truthy while `int("0") > 0` is false, so two
  plausible-looking checks disagree. Compare numerically, and only on `credits` plans.

## Complete Example: Flask Agent

```python
from flask import Flask, request, jsonify
from payments_py import Payments, PaymentOptions
from payments_py.x402.helpers import build_payment_required
from payments_py.common.payments_error import PaymentsError

app = Flask(__name__)

# Initialize payments
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:agent-key", environment="sandbox")
)

AGENT_ID = "your-agent-id"
PLAN_ID = "your-plan-id"

@app.route('/api/tasks', methods=['POST'])
def create_task():
    # 1. Extract x402 access token from payment-signature header
    access_token = request.headers.get('payment-signature', '')
    if not access_token:
        return jsonify({'error': 'Missing payment-signature header'}), 402

    # 2. Build payment required object
    payment_required = build_payment_required(
        plan_id=PLAN_ID,
        endpoint=request.url,
        agent_id=AGENT_ID,
        http_verb=request.method
    )

    try:
        # 3. Verify permissions
        verification = payments.facilitator.verify_permissions(
            payment_required=payment_required,
            x402_access_token=access_token,
            max_amount="1"
        )

        if not verification.is_valid:
            return jsonify({
                'error': 'Payment verification failed',
                'details': verification.invalid_reason
            }), 402

        # 4. Process the request
        task_data = request.json
        result = process_task(task_data)

        # 5. Settle (burn credits) after successful processing
        settlement = payments.facilitator.settle_permissions(
            payment_required=payment_required,
            x402_access_token=access_token,
            max_amount="1"
        )

        # Pass `billing_model` through — it is what tells the caller how to read
        # the credit fields (see "Was the buyer charged?" above).
        return jsonify({
            'result': result,
            'billing_model': settlement.billing_model,
            'credits_used': settlement.credits_redeemed,
            'order_tx': settlement.order_tx,
        })

    except PaymentsError as e:
        return jsonify({'error': str(e)}), 402

def process_task(data):
    # Your AI logic here
    return {"status": "completed", "output": "Task result"}

if __name__ == '__main__':
    app.run(port=8080)
```

## FastAPI Example with Manual Validation

```python
from fastapi import FastAPI, Request, HTTPException
from payments_py import Payments, PaymentOptions
from payments_py.x402.helpers import build_payment_required

app = FastAPI()

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:agent-key", environment="sandbox")
)

AGENT_ID = "your-agent-id"
PLAN_ID = "your-plan-id"

async def validate_payment(request: Request) -> dict:
    """Validate payment and return verification result."""
    # Extract x402 token from payment-signature header
    access_token = request.headers.get('payment-signature', '')
    if not access_token:
        raise HTTPException(status_code=402, detail="Missing payment-signature header")

    payment_required = build_payment_required(
        plan_id=PLAN_ID,
        endpoint=str(request.url),
        agent_id=AGENT_ID,
        http_verb=request.method
    )

    verification = payments.facilitator.verify_permissions(
        payment_required=payment_required,
        x402_access_token=access_token,
        max_amount="1"
    )

    if not verification.is_valid:
        raise HTTPException(status_code=402, detail="Payment verification failed")

    return {
        "access_token": access_token,
        "payment_required": payment_required,
        "verification": verification
    }

@app.post("/api/tasks")
async def create_task(request: Request, body: dict):
    # Validate payment
    payment_info = await validate_payment(request)

    # Process task
    result = {"output": f"Processed: {body}"}

    # Settle credits
    settlement = payments.facilitator.settle_permissions(
        payment_required=payment_info["payment_required"],
        x402_access_token=payment_info["access_token"],
        max_amount="1"
    )

    return {
        "result": result,
        "billing_model": settlement.billing_model,
        "credits_used": settlement.credits_redeemed,
        "order_tx": settlement.order_tx,
    }
```

## Using x402 FastAPI Middleware

For FastAPI applications, use the built-in x402 middleware:

```python
from fastapi import FastAPI
from payments_py import Payments, PaymentOptions
from payments_py.x402.fastapi import PaymentMiddleware

app = FastAPI()

# Initialize payments
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:agent-key", environment="sandbox")
)

# Add x402 middleware
app.add_middleware(
    PaymentMiddleware,
    payments=payments,
    routes={
        "/api/tasks": {
            "plan_id": "your-plan-id",
            "agent_id": "your-agent-id",
        }
    }
)

@app.post("/api/tasks")
async def create_task(body: dict):
    # Middleware handles verification automatically
    # Just process the request
    return {"result": "Task completed"}
```

## Verification Response

The `verify_permissions` method returns a `VerifyResponse`:

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | `bool` | Whether the request is authorized |
| `invalid_reason` | `str` | Reason for invalidity (if `is_valid` is false) |
| `payer` | `str` | Payer's wallet address |
| `agent_request_id` | `str` | Agent request ID for observability tracking |

## Settlement Response

The `settle_permissions` method returns a `SettleResponse`:

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether settlement succeeded |
| `error_reason` | `str` | Reason for settlement failure (if `success` is false) |
| `payer` | `str` | Payer's wallet address |
| `transaction` | `str` | Blockchain transaction hash. Also the charge reference on crypto pay-as-you-go plans |
| `network` | `str` | The rail: a CAIP-2 chain id for crypto, or the settling PSP (`stripe`, `braintree`, `visa`) for fiat |
| `billing_model` | `str` | How the request was priced: `credits` or `pay-as-you-go`. Read this before the two credit fields |
| `credits_redeemed` | `str` | Number of credits burned. **Always `"0"` on `pay-as-you-go`**, including on a successful charge |
| `remaining_balance` | `str` | Credits remaining. **Always `"0"` on `pay-as-you-go`** |
| `order_tx` | `str` | Order / per-request charge reference. On fiat pay-as-you-go this is the PSP transaction id |

## Best Practices

1. **Always verify before processing**: Don't process expensive operations without verification

2. **Handle errors gracefully**: Return 402 Payment Required with helpful error messages

3. **Settle after completion**: Only burn credits after successfully completing the request

4. **Branch on `billing_model`**: Never decide "was the buyer charged?" from `credits_redeemed`
   alone — see [Was the buyer charged?](#was-the-buyer-charged) above

5. **Log transactions**: Keep records of verification and settlement for debugging

6. **Use middleware for consistency**: Apply validation uniformly across all endpoints

## Next Steps

- [MCP Integration](09-mcp-integration.md) - Build MCP servers with payment validation
- [x402 Protocol](11-x402.md) - Deep dive into x402 protocol
