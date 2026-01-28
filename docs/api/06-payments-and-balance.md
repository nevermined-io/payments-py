# Payments and Balance

This guide covers how to order payment plans and manage balances using the Nevermined Payments Python SDK.

## Overview

As a subscriber, you need to order payment plans to gain access to AI agents and resources. This guide explains:

- How to check plan balances
- How to order plans (crypto payments)
- How to mint and burn credits (for plan owners)

## Check Plan Balance

Before ordering or using a plan, check the current balance:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Check balance for current user
balance = payments.plans.get_plan_balance(plan_id="your-plan-id")

print(f"Plan ID: {balance.plan_id}")
print(f"Plan Name: {balance.plan_name}")
print(f"Plan Type: {balance.plan_type}")
print(f"Balance: {balance.balance}")
print(f"Is Subscriber: {balance.is_subscriber}")
print(f"Price per Credit: {balance.price_per_credit}")
```

### Check Balance for Another User

```python
balance = payments.plans.get_plan_balance(
    plan_id="your-plan-id",
    account_address="0xOtherUserAddress"
)
```

### Balance Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `plan_id` | `str` | Plan identifier |
| `plan_name` | `str` | Plan display name |
| `plan_type` | `str` | "credits" or "time" |
| `balance` | `int` | Current credit balance |
| `is_subscriber` | `bool` | Whether user has access |
| `holder_address` | `str` | Wallet address checked |
| `price_per_credit` | `float` | Cost per credit |

## Order Plans

### Order with Crypto

Order a plan using cryptocurrency (ERC20 or native tokens):

```python
# Order a plan (requires sufficient token balance)
result = payments.plans.order_plan(plan_id="your-plan-id")

print(f"Success: {result['success']}")
print(f"Order details: {result}")
```

!!! note "Token Approval Required"
    For ERC20 token payments, ensure you have approved the Nevermined contract to spend your tokens before ordering.

### Order Fiat Plans

For plans priced in fiat (USD), use Stripe checkout:

```python
# Get Stripe checkout session
checkout = payments.plans.order_fiat_plan(plan_id="fiat-plan-id")

print(f"Checkout URL: {checkout['checkoutUrl']}")
print(f"Session ID: {checkout['sessionId']}")

# Redirect user to checkout['checkoutUrl'] to complete payment
```

## Mint Credits (Plan Owners)

Plan owners can mint additional credits for subscribers:

```python
# Mint credits to a user
result = payments.plans.mint_plan_credits(
    plan_id="your-plan-id",
    credits_amount=50,
    credits_receiver="0xSubscriberAddress"
)

print(f"Minted: {result}")
```

### Mint Expirable Credits

For time-limited plans, mint credits with an expiration:

```python
result = payments.plans.mint_plan_expirable(
    plan_id="your-plan-id",
    credits_amount=100,
    credits_receiver="0xSubscriberAddress",
    credits_duration=86400  # 1 day in seconds
)
```

## Burn Credits (Plan Owners)

Plan owners can burn credits from the plan:

```python
result = payments.plans.burn_credits(
    plan_id="your-plan-id",
    credits_amount="10"
)

print(f"Burned: {result}")
```

## Redeem Credits

Agents can redeem credits from subscribers for completed work:

```python
result = payments.plans.redeem_credits(
    agent_request_id="request-123",
    plan_id="plan-id",
    redeem_from="0xSubscriberAddress",
    credits_amount_to_redeem="5"
)
```

## Complete Example

```python
from payments_py import Payments, PaymentOptions
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

# Initialize as builder (plan owner)
payments_builder = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:builder-key", environment="sandbox")
)

# Initialize as subscriber
payments_subscriber = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:subscriber-key", environment="sandbox")
)

ERC20_TOKEN = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"
builder_address = payments_builder.account_address

# 1. Builder creates a plan
plan_result = payments_builder.plans.register_credits_plan(
    plan_metadata=PlanMetadata(name="Premium Plan"),
    price_config=get_erc20_price_config(20, ERC20_TOKEN, builder_address),
    credits_config=get_fixed_credits_config(100)
)
plan_id = plan_result['planId']
print(f"Created plan: {plan_id}")

# 2. Subscriber checks initial balance (should be 0 or not subscribed)
initial_balance = payments_subscriber.plans.get_plan_balance(plan_id)
print(f"Initial balance: {initial_balance.balance}")
print(f"Is subscriber: {initial_balance.is_subscriber}")

# 3. Subscriber orders the plan
order_result = payments_subscriber.plans.order_plan(plan_id)
print(f"Order success: {order_result['success']}")

# 4. Subscriber checks balance after ordering
final_balance = payments_subscriber.plans.get_plan_balance(plan_id)
print(f"Final balance: {final_balance.balance}")
print(f"Is subscriber: {final_balance.is_subscriber}")

# 5. Builder can mint additional credits
if final_balance.is_subscriber:
    mint_result = payments_builder.plans.mint_plan_credits(
        plan_id=plan_id,
        credits_amount=50,
        credits_receiver=payments_subscriber.account_address
    )
    print(f"Minted 50 additional credits")

    # Check updated balance
    updated_balance = payments_subscriber.plans.get_plan_balance(plan_id)
    print(f"Updated balance: {updated_balance.balance}")
```

## Workflow Summary

```
┌──────────────────────────────────────────────────────────┐
│                     BUILDER                               │
│  1. Create Plan (register_credits_plan)                  │
│  2. Register Agent with Plan                             │
│  3. Optionally mint credits to users                     │
└──────────────────────────────────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│                    SUBSCRIBER                             │
│  1. Check Balance (get_plan_balance)                     │
│  2. Order Plan (order_plan)                              │
│  3. Get Access Token (get_x402_access_token)             │
│  4. Query Agent (with access token)                      │
└──────────────────────────────────────────────────────────┘
```

## Next Steps

- [Querying an Agent](07-querying-an-agent.md) - Get access tokens and make requests
- [Validation of Requests](08-validation-of-requests.md) - How agents validate requests
