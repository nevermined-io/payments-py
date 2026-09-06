# Orders

This guide covers browser-fiat **Orders**: a merchant-initiated, off-plan charge for an arbitrary amount (the Stripe PaymentIntent analog) that the buyer's browser confirms client-side. No payment plan, no buyer Nevermined account, no delegation.

## Overview

1. `payments.orders.create_order(...)` — the merchant creates the Order server-side and receives a Stripe `client_secret`.
2. The merchant hands the `client_secret` to its checkout page, which confirms the payment with Stripe.js.
3. `payments.orders.get_order(order_id)` — anyone holding the unguessable `order_id` reads the buyer-safe status. No API key is sent on the wire.

## Requirements

`create_order` needs an **organization-scoped** NVM API key: the API resolves the merchant organization from the key's own org tag. A personal key is refused with `BCK.ORDER.0003`, and `payments.set_organization_id(...)` does not substitute for an org-scoped key. The organization must be active and have a Stripe Connect account able to receive card payments.

## Create an Order

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key="nvm:your-org-scoped-key", environment="sandbox")
)

created = payments.orders.create_order(
    3437,  # USD cents: $34.37
    description="Cart checkout - 3 items",
    buyer_ref="merchant-order-4821",
    idempotency_key="merchant-order-4821",
    line_items=[{"sku": "PRO-PLAN", "quantity": 1, "unit_price": 3437}],
    metadata={"channel": "web"},
)

print(created.order_id)       # ord_... - the buyer-facing access control
print(created.status)         # requires_payment
print(created.client_secret)  # hand this to the browser (Stripe.js confirm)
```

| Parameter | Type | Description |
|---|---|---|
| `amount_minor` | `int` | Charge amount in USD cents (at least `100`, i.e. $1.00). The API validates the upper bound (`BCK.ORDER.0001`); a deployment may enforce a lower per-order cap (`BCK.ORDER.0003`). |
| `currency` | `str` | ISO currency, lower-cased. Default and only value in Phase 1: `"usd"`. |
| `description` | `str` | Optional. Human-readable description (max 1024 chars). |
| `buyer_ref` | `str` | Optional. Your own reference for the buyer or cart (max 255 chars). |
| `idempotency_key` | `str` | Optional. A retry with the same key returns the original Order unchanged (and its `client_secret` while the Order is still payable); the other fields of the retry are ignored, not merged. A retry with a different `amount_minor` or `currency` is refused with `BCK.ORDER.0007`. |
| `line_items` | `list[dict]` | Optional. Merchant-defined structure, recorded verbatim (keys are not transformed), opaque to the API. |
| `metadata` | `dict` | Optional. Merchant-defined structure, recorded verbatim (keys are not transformed), opaque to the API. |
| `capture_mode` | `str` | Optional. `"automatic"` only in Phase 1. |
| `payment_provider` | `str` | Optional. `"stripe"` only in Phase 1. |

## Read an Order

```python
order = payments.orders.get_order(created.order_id)

print(order.status)                 # OrderStatus.REQUIRES_PAYMENT, PAID, ...
print(order.amount_minor)           # 3437
print(order.amount_refunded_minor)  # 0
print(order.client_secret)          # present only while the Order is payable
```

The read is anonymous on the wire (the unguessable id is the access control) and returns a buyer-safe projection: it never includes the merchant identity, the Connect account or the fee.

The read endpoint is rate-limited: all anonymous callers behind one IP share a bucket of 60 requests per minute. A throttled call raises `PaymentsError` with code `http_429` and no catalogue code (this is not the create-side `BCK.ORDER.0010`). Poll sparingly and back off on `http_429`.

## Order lifecycle

| Status | Meaning |
|---|---|
| `requires_payment` | Created; the browser has not confirmed yet. `client_secret` is available. |
| `paid` | Payment succeeded. Also the state after a **won** dispute. |
| `failed` | Payment failed, or the PaymentIntent could not be created. No money moved. |
| `refunded` / `partially_refunded` | Refunded in full / in part (see `amount_refunded_minor`). |
| `disputed` | A chargeback is open, or was lost. A won dispute returns the Order to `paid`. |

## Error codes

Errors raise `PaymentsError` with `code` set to the backend catalogue code:

| Code | HTTP | Meaning |
|---|---|---|
| `BCK.ORDER.0001` | 400 | Invalid request (amount out of range, unsupported currency / capture mode / provider). |
| `BCK.ORDER.0002` | 404 | No Order with this id. |
| `BCK.ORDER.0003` | 403 | The key is not an active organization, or the amount exceeds the per-order cap. |
| `BCK.ORDER.0004` | 500 | The merchant has no Connect account able to receive card payments. |
| `BCK.ORDER.0005` | 500 | The PaymentIntent could not be created; the Order is `failed`, no money moved. |
| `BCK.ORDER.0007` | 409 | Idempotency key reused with a different `amount_minor` or `currency`. |
| `BCK.ORDER.0010` | 429 | Velocity cap exceeded on `create_order`. Retry after backoff. |
| `http_429` | 429 | The `get_order` read throttle (no catalogue code). Back off and retry. |

A refusal that carries no catalogue code (a throttle or gateway response) surfaces with code `http_<status>`.

```python
from payments_py import PaymentsError

try:
    created = payments.orders.create_order(3437)
except PaymentsError as e:
    if e.code == "BCK.ORDER.0010":
        ...  # back off and retry
    raise
```
