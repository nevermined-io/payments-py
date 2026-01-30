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
    print(f"Subscriber: {verification.subscriber_address}")
else:
    print(f"Invalid request: {verification.error}")
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
    print(f"Credits redeemed: {settlement.credits_redeemed}")
    print(f"Transaction: {settlement.tx_hash}")
```

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
                'details': verification.error
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

        return jsonify({
            'result': result,
            'credits_used': settlement.credits_redeemed
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
        "credits_used": settlement.credits_redeemed
    }
```

## Using x402 FastAPI Middleware

For FastAPI applications, use the built-in x402 middleware:

```python
from fastapi import FastAPI
from payments_py.x402.fastapi import X402Middleware

app = FastAPI()

# Add x402 middleware
app.add_middleware(
    X402Middleware,
    nvm_api_key="nvm:agent-key",
    environment="sandbox",
    agent_id="your-agent-id",
    plan_id="your-plan-id"
)

@app.post("/api/tasks")
async def create_task(body: dict):
    # Middleware handles verification automatically
    # Just process the request
    return {"result": "Task completed"}
```

## Verification Response

The `verify_permissions` method returns:

| Field | Type | Description |
|-------|------|-------------|
| `is_valid` | `bool` | Whether the request is authorized |
| `subscriber_address` | `str` | Subscriber's wallet address |
| `plan_id` | `str` | Plan being used |
| `balance` | `int` | Current credit balance |
| `error` | `str` | Error message if invalid |

## Settlement Response

The `settle_permissions` method returns:

| Field | Type | Description |
|-------|------|-------------|
| `success` | `bool` | Whether settlement succeeded |
| `credits_redeemed` | `int` | Number of credits burned |
| `tx_hash` | `str` | Blockchain transaction hash |
| `remaining_balance` | `int` | Credits remaining |

## Best Practices

1. **Always verify before processing**: Don't process expensive operations without verification

2. **Handle errors gracefully**: Return 402 Payment Required with helpful error messages

3. **Settle after completion**: Only burn credits after successfully completing the request

4. **Log transactions**: Keep records of verification and settlement for debugging

5. **Use middleware for consistency**: Apply validation uniformly across all endpoints

## Next Steps

- [MCP Integration](09-mcp-integration.md) - Build MCP servers with payment validation
- [x402 Protocol](11-x402.md) - Deep dive into x402 protocol
