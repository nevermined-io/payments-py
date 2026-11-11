# Payment Plans

This guide covers how to create and manage payment plans using the Nevermined Payments Python SDK.

## Overview

Payment Plans define how users pay to access your AI agents and services. Nevermined supports these types of plans:

- **Credits Plans**: Users purchase a fixed number of credits that are consumed with each request
- **Time Plans**: Users purchase access for a specific duration (e.g., 1 day, 1 month)
- **Pay-As-You-Go Plans**: Users pay on every request, in crypto or by card, without buying credits up front

## Plans API

Access the Plans API through `payments.plans`:

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)

# Access plans API
plans_api = payments.plans
```

## Types of Payment Plans

### Credits Plans

Credits plans grant users a fixed number of credits. Each agent request consumes credits according to the plan configuration.

```python
from payments_py.common.types import PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config

# Plan metadata
plan_metadata = PlanMetadata(
    name="Basic Plan",
    description="100 credits for AI agent access"
)

# Price: 20 tokens (ERC20)
price_config = get_erc20_price_config(
    amount=20,
    token_address="0xYourERC20TokenAddress",
    receiver="0xYourWalletAddress"
)

# Credits: 100 credits, 1 credit per request
credits_config = get_fixed_credits_config(
    credits_granted=100,
    credits_per_request=1
)

# Register the plan
result = payments.plans.register_credits_plan(
    plan_metadata=plan_metadata,
    price_config=price_config,
    credits_config=credits_config
)
print(f"Plan ID: {result['planId']}")
```

### Time Plans

Time plans grant users unlimited access for a specific duration:

```python
from payments_py.plans import get_expirable_duration_config, ONE_DAY_DURATION

# Price configuration
price_config = get_erc20_price_config(
    amount=50,
    token_address="0xYourERC20TokenAddress",
    receiver="0xYourWalletAddress"
)

# Duration: 1 day
credits_config = get_expirable_duration_config(ONE_DAY_DURATION)

result = payments.plans.register_time_plan(
    plan_metadata=PlanMetadata(name="Daily Plan"),
    price_config=price_config,
    credits_config=credits_config
)
```

### Pay-As-You-Go Plans

Pay-as-you-go plans charge the subscriber on every request instead of selling a balance of
credits up front. Subscribers pay either in crypto or by card, and the two use different price
configs: see [Pay-As-You-Go Price](#pay-as-you-go-price).

### Trial Plans

Trial plans can only be purchased once per user. Perfect for free trials:

```python
from payments_py.plans import get_free_price_config

# Free trial with 10 credits
price_config = get_free_price_config()
credits_config = get_fixed_credits_config(credits_granted=10)

result = payments.plans.register_credits_trial_plan(
    plan_metadata=PlanMetadata(name="Free Trial", description="10 free credits"),
    price_config=price_config,
    credits_config=credits_config
)
```

```python
# Free trial with 1 day access
credits_config = get_expirable_duration_config(ONE_DAY_DURATION)

result = payments.plans.register_time_trial_plan(
    plan_metadata=PlanMetadata(name="1-Day Trial"),
    price_config=get_free_price_config(),
    credits_config=credits_config
)
```

## Price Configuration

### ERC20 Token Price

```python
from payments_py.plans import get_erc20_price_config

price_config = get_erc20_price_config(
    amount=100,                           # Amount in token units
    token_address="0xTokenAddress",       # ERC20 token contract
    receiver="0xBuilderAddress"           # Payment receiver
)
```

### Native Token Price (ETH)

```python
from payments_py.plans import get_native_token_price_config

price_config = get_native_token_price_config(
    amount=1000000000000000,  # Amount in wei (0.001 ETH)
    receiver="0xBuilderAddress"
)
```

### Fiat Price (USD)

```python
from payments_py.plans import get_fiat_price_config

price_config = get_fiat_price_config(
    amount=9_990_000,  # $9.99 (6-decimal units, not cents)
    receiver="0xBuilderAddress"
)
```

### Fiat Price (EUR)

```python
from payments_py.plans import get_fiat_price_config
from payments_py.common.types import Currency

price_config = get_fiat_price_config(
    amount=29_000_000,  # €29.00 (6-decimal units, not cents)
    receiver="0xBuilderAddress",
    currency=Currency.EUR
)
```

> Fiat amounts are in **6-decimal units** (the USDC convention used across the Nevermined protocol), **not** cents — `10_000_000` = $10.00. The server-side minimum is **$1.00** (`1_000_000`); smaller amounts are rejected with `BCK.PROTOCOL.0047`.

### EURC Token Price (Euro Stablecoin)

```python
from payments_py.plans import get_eurc_price_config

# EURC pricing (Euro stablecoin on Base, 6 decimals)
price_config = get_eurc_price_config(
    amount=29_000_000,          # €29.00 in smallest unit (6 decimals)
    receiver="0xBuilderAddress"
)

# Or use a custom EURC address (e.g., testnet)
from payments_py.common.types import EURC_TOKEN_ADDRESS_TESTNET

testnet_config = get_eurc_price_config(
    amount=29_000_000,
    receiver="0xBuilderAddress",
    eurc_address=EURC_TOKEN_ADDRESS_TESTNET
)
```

### Free Price

```python
from payments_py.plans import get_free_price_config

price_config = get_free_price_config()
```

### Pay-As-You-Go Price

A pay-as-you-go plan charges the subscriber on every request instead of selling a balance of
credits up front. Its price builder decides **how** the subscriber pays, so pick it by rail:

| Rail | Price config | Credits config |
|------|--------------|----------------|
| Crypto | `payments.plans.get_pay_as_you_go_price_config(amount, receiver[, token_address])` | `payments.plans.get_pay_as_you_go_credits_config()` |
| Card | `payments.plans.get_fiat_price_config(amount, receiver[, currency])`, then set its `template_address` to `payments.contracts.get_pay_as_you_go_template_address()` | `payments.plans.get_pay_as_you_go_credits_config()` |

> **`get_pay_as_you_go_price_config` always builds a crypto price** (`is_crypto=True`), whatever
> token you pass. Do not use it for a plan that subscribers pay by card.

What makes either plan pay-as-you-go is the **PayAsYouGoTemplate** address in its price config:
the API reports `billingModel: 'pay-as-you-go'` (in `payments.plans.get_plan(plan_id)`, and as
`billing_model` on each settle) only for a plan registered on that template.
`get_pay_as_you_go_price_config` sets it for you; `get_fiat_price_config` does not, so the card
recipe adds it.

#### Crypto pay-as-you-go

```python
USDC_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"  # USDC on Base Sepolia

# Fetches the PayAsYouGoTemplate address from the API for you
price_config = payments.plans.get_pay_as_you_go_price_config(
    amount=1_000_000,             # Price per request in the token's smallest unit (1 USDC, 6 decimals)
    receiver="0xBuilderAddress",  # Payment receiver
    token_address=USDC_ADDRESS    # ERC20 token (omit for the native token)
)
credits_config = payments.plans.get_pay_as_you_go_credits_config()
```

#### Card pay-as-you-go

```python
# is_crypto=False: the subscriber's card is charged on every request
price_config = payments.plans.get_fiat_price_config(
    amount=1_000_000,            # Price per request in 6-decimal units ($1.00), NOT cents
    receiver="0xBuilderAddress"  # Payment receiver
)
# The PayAsYouGoTemplate is what makes this fiat price pay-as-you-go
price_config.template_address = payments.contracts.get_pay_as_you_go_template_address()
credits_config = payments.plans.get_pay_as_you_go_credits_config()
```

Register either one as a credits plan:

```python
result = payments.plans.register_credits_plan(
    plan_metadata=PlanMetadata(name="Pay per request"),
    price_config=price_config,
    credits_config=credits_config
)
```

A card pay-as-you-go plan:

- is paid **per request through an x402 card delegation**: each settle charges the card the plan
  price, and the settle reports `billing_model == "pay-as-you-go"` with the charge reference in
  `order_tx` (see [Was the buyer charged?](11-x402.md#was-the-buyer-charged));
- is **not sold through checkout**, by design: there is no balance to buy up front, so
  `order_fiat_plan` fails with `BCK.STRIPE.0041`;
- keeps the fiat price floor: the per-request price must be at least **$1.00** (`1_000_000`),
  otherwise registration fails with `BCK.PROTOCOL.0047`.

> **`get_fiat_price_config` + `get_pay_as_you_go_credits_config` alone is NOT a pay-as-you-go
> plan.** Without the template address it registers a one-credit **credits** plan: the API
> reports it as `billingModel: 'credits'`, and each purchase buys a single credit.

## Credits Configuration

### Fixed Credits

Each request consumes a fixed number of credits:

```python
from payments_py.plans import get_fixed_credits_config

credits_config = get_fixed_credits_config(
    credits_granted=100,      # Total credits granted
    credits_per_request=1     # Credits consumed per request
)
```

### Dynamic Credits

Each request can consume a variable number of credits:

```python
from payments_py.plans import get_dynamic_credits_config

credits_config = get_dynamic_credits_config(
    credits_granted=100,
    min_credits_per_request=1,   # Minimum credits per request
    max_credits_per_request=10   # Maximum credits per request
)
```

### Duration-Based (Time Plans)

```python
from payments_py.plans import (
    get_expirable_duration_config,
    get_non_expirable_duration_config,
    ONE_DAY_DURATION,
    ONE_WEEK_DURATION,
    ONE_MONTH_DURATION,
    ONE_YEAR_DURATION
)

# Expirable (time-limited)
credits_config = get_expirable_duration_config(ONE_MONTH_DURATION)

# Non-expirable (permanent access)
credits_config = get_non_expirable_duration_config()
```

## Retrieve Plans

### List Your Plans

List the plans **you** published. This is caller-scoped account management — it
returns only the plans the authenticated account created, never other users'
plans (Nevermined is not a marketplace, so there is no global plan search).
Useful for finding and managing your own plans (e.g. spotting duplicates).

```python
from payments_py.common.types import PaginationOptions

# Your own plans
result = payments.plans.get_user_plans(
    pagination=PaginationOptions(page=1, offset=10)
)
print(f"Total: {result['total']}")
for plan in result["plans"]:
    print(plan["id"])

# Every plan in an organization you belong to
org_plans = payments.plans.get_user_plans(org_id="org-acme")
```

For code ported from the TypeScript SDK, `get_plans(page, offset, sort_by, sort_order, org_id)` is a positional-argument alias of `get_user_plans` matching `plans.getPlans(...)` (same defaults: `page=1, offset=100, sort_by="created", sort_order="desc"`).

### Get a Single Plan

```python
plan = payments.plans.get_plan(plan_id="123456")
print(f"Plan name: {plan['name']}")
print(f"Plan type: {plan['planType']}")
```

### Get Plan Balance

Check the balance for a specific account:

```python
balance = payments.plans.get_plan_balance(
    plan_id="123456",
    account_address="0xUserAddress"  # Optional, defaults to current user
)
print(f"Balance: {balance.balance} credits")
print(f"Is subscriber: {balance.is_subscriber}")
```

### Get Agents Associated to a Plan

```python
from payments_py.common.types import PaginationOptions

agents = payments.plans.get_agents_associated_to_plan(
    plan_id="123456",
    pagination=PaginationOptions(page=1, offset=10)
)
print(f"Agents: {agents}")
```

## Complete Example

```python
from payments_py import Payments, PaymentOptions
from payments_py.common.types import PlanMetadata
from payments_py.plans import (
    get_erc20_price_config,
    get_fixed_credits_config,
    get_expirable_duration_config,
    get_free_price_config,
    ONE_DAY_DURATION
)

# Initialize
payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-key", environment="sandbox")
)
builder_address = payments.account_address

# ERC20 token address (use a test token in sandbox)
ERC20_TOKEN = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"

# 1. Create a credits plan
credits_plan = payments.plans.register_credits_plan(
    plan_metadata=PlanMetadata(name="Basic Credits Plan"),
    price_config=get_erc20_price_config(20, ERC20_TOKEN, builder_address),
    credits_config=get_fixed_credits_config(100)
)
print(f"Credits Plan: {credits_plan['planId']}")

# 2. Create a time plan
time_plan = payments.plans.register_time_plan(
    plan_metadata=PlanMetadata(name="Monthly Plan"),
    price_config=get_erc20_price_config(50, ERC20_TOKEN, builder_address),
    credits_config=get_expirable_duration_config(ONE_DAY_DURATION)
)
print(f"Time Plan: {time_plan['planId']}")

# 3. Create a free trial
trial_plan = payments.plans.register_credits_trial_plan(
    plan_metadata=PlanMetadata(name="Free Trial"),
    price_config=get_free_price_config(),
    credits_config=get_fixed_credits_config(10)
)
print(f"Trial Plan: {trial_plan['planId']}")

# 4. Retrieve plan details
plan_details = payments.plans.get_plan(credits_plan['planId'])
print(f"Plan details: {plan_details}")
```

## Next Steps

- [Agents](04-agents.md) - Register AI agents and associate them with plans
- [Payments and Balance](06-payments-and-balance.md) - Order plans and manage balances
