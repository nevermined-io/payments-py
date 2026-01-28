# Payment Plans

This guide covers how to create and manage payment plans using the Nevermined Payments Python SDK.

## Overview

Payment Plans define how users pay to access your AI agents and services. Nevermined supports two types of plans:

- **Credits Plans**: Users purchase a fixed number of credits that are consumed with each request
- **Time Plans**: Users purchase access for a specific duration (e.g., 1 day, 1 month)

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
    amount=999,  # $9.99 in cents
    receiver="0xBuilderAddress"
)
```

### Free Price

```python
from payments_py.plans import get_free_price_config

price_config = get_free_price_config()
```

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
