<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `plans`
Utility functions for creating and managing payment plans. 

**Global Variables**
---------------
- **ZeroAddress**
- **ONE_DAY_DURATION**
- **ONE_WEEK_DURATION**
- **ONE_MONTH_DURATION**
- **ONE_YEAR_DURATION**

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L23"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_fiat_price_config`

```python
get_fiat_price_config(amount: int, receiver: str) → PlanPriceConfig
```

Get a fixed fiat price configuration for a plan. 



**Args:**
 
 - <b>`amount`</b>:  The amount in the smallest unit of the fiat currency 
 - <b>`receiver`</b>:  The address that will receive the payment 



**Returns:**
 A PlanPriceConfig object configured for fiat payments 



**Raises:**
 
 - <b>`ValueError`</b>:  If the receiver address is not a valid Ethereum address 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L51"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_crypto_price_config`

```python
get_crypto_price_config(
    amount: int,
    receiver: str,
    token_address: str = '0x0000000000000000000000000000000000000000'
) → PlanPriceConfig
```

Get a fixed crypto price configuration for a plan. 



**Args:**
 
 - <b>`amount`</b>:  The amount in the smallest unit of the token 
 - <b>`receiver`</b>:  The address that will receive the payment 
 - <b>`token_address`</b>:  The address of the token to use for payment (defaults to native token) 



**Returns:**
 A PlanPriceConfig object configured for crypto payments 



**Raises:**
 
 - <b>`ValueError`</b>:  If the receiver address is not a valid Ethereum address 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L82"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_erc20_price_config`

```python
get_erc20_price_config(
    amount: int,
    token_address: str,
    receiver: str
) → PlanPriceConfig
```

Get a fixed ERC20 token price configuration for a plan. 



**Args:**
 
 - <b>`amount`</b>:  The amount in the smallest unit of the ERC20 token 
 - <b>`token_address`</b>:  The address of the ERC20 token 
 - <b>`receiver`</b>:  The address that will receive the payment 



**Returns:**
 A PlanPriceConfig object configured for ERC20 token payments 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L99"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_free_price_config`

```python
get_free_price_config() → PlanPriceConfig
```

Get a free price configuration for a plan. 



**Returns:**
  A PlanPriceConfig object configured for free plans 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L118"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_native_token_price_config`

```python
get_native_token_price_config(amount: int, receiver: str) → PlanPriceConfig
```

Get a fixed native token price configuration for a plan. 



**Args:**
 
 - <b>`amount`</b>:  The amount in the smallest unit of the native token 
 - <b>`receiver`</b>:  The address that will receive the payment 



**Returns:**
 A PlanPriceConfig object configured for native token payments 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L132"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_expirable_duration_config`

```python
get_expirable_duration_config(duration_of_plan: int) → PlanCreditsConfig
```

Get an expirable duration configuration for a plan. 



**Args:**
 
 - <b>`duration_of_plan`</b>:  The duration of the plan in seconds 



**Returns:**
 A PlanCreditsConfig object configured for expirable duration 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L153"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_non_expirable_duration_config`

```python
get_non_expirable_duration_config() → PlanCreditsConfig
```

Get a non-expirable duration configuration for a plan. 



**Returns:**
  A PlanCreditsConfig object configured for non-expirable duration 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L163"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_fixed_credits_config`

```python
get_fixed_credits_config(
    credits_granted: int,
    credits_per_request: int = 1
) → PlanCreditsConfig
```

Get a fixed credits configuration for a plan. 



**Args:**
 
 - <b>`credits_granted`</b>:  The total number of credits granted 
 - <b>`credits_per_request`</b>:  The number of credits consumed per request (default: 1) 



**Returns:**
 A PlanCreditsConfig object configured for fixed credits 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L187"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_dynamic_credits_config`

```python
get_dynamic_credits_config(
    credits_granted: int,
    min_credits_per_request: int = 1,
    max_credits_per_request: int = 1
) → PlanCreditsConfig
```

Get a dynamic credits configuration for a plan. 



**Args:**
 
 - <b>`credits_granted`</b>:  The total number of credits granted 
 - <b>`min_credits_per_request`</b>:  The minimum number of credits consumed per request (default: 1) 
 - <b>`max_credits_per_request`</b>:  The maximum number of credits consumed per request (default: 1) 



**Returns:**
 A PlanCreditsConfig object configured for dynamic credits 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L214"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `set_redemption_type`

```python
set_redemption_type(
    credits_config: PlanCreditsConfig,
    redemption_type: PlanRedemptionType
) → PlanCreditsConfig
```

Set the redemption type for a credits configuration. 



**Args:**
 
 - <b>`credits_config`</b>:  The credits configuration to modify 
 - <b>`redemption_type`</b>:  The new redemption type 



**Returns:**
 A new PlanCreditsConfig with the updated redemption type 


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/plans.py#L238"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `set_proof_required`

```python
set_proof_required(
    credits_config: PlanCreditsConfig,
    proof_required: bool = True
) → PlanCreditsConfig
```

Set whether proof is required for a credits configuration. 



**Args:**
 
 - <b>`credits_config`</b>:  The credits configuration to modify 
 - <b>`proof_required`</b>:  Whether proof is required (default: True) 



**Returns:**
 A new PlanCreditsConfig with the updated proof requirement 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
