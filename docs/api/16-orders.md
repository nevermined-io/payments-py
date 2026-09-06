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
    3437,  # USD cents: $34.37 ($1.00 - $999,999.99)
    description="Cart checkout - 3 items",
    buyer_ref="merchant-order-4821",
    idempotency_key="merchant-order-4821",
    line_items=[{"sku": "PRO-PLAN", "quantity": 1, "amountMinor": 3437}],
    metadata={"channel": "web"},
)

print(created.order_id)       # ord_... - the buyer-facing access control
print(created.status)         # requires_payment
print(created.client_secret)  # hand this to the browser (Stripe.js confirm)
```

| Parameter | Type | Description |
|---|---|---|
| `amount_minor` | `int` | Charge amount in USD cents, `100` to `99_999_999`. |
| `currency` | `str` | ISO currency, lower-cased. Default and only value in Phase 1: `"usd"`. |
| `description` | `str` | Optional. Human-readable description (max 1024 chars). |
| `buyer_ref` | `str` | Optional. Your own reference for the buyer or cart (max 255 chars). |
| `idempotency_key` | `str` | Optional. A retried create with the same key returns the same Order and `client_secret`; a conflicting body is refused with `BCK.ORDER.0007`. |
| `line_items` | `list[dict]` | Optional. Recorded verbatim, opaque to the API. |
| `metadata` | `dict` | Optional. Recorded verbatim, opaque to the API. |
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

## Order lifecycle

| Status | Meaning |
|---|---|
| `requires_payment` | Created; the browser has not confirmed yet. `client_secret` is available. |
| `paid` | Payment succeeded. |
| `failed` | Payment failed, or the PaymentIntent could not be created. No money moved. |
| `refunded` / `partially_refunded` | Refunded in full / in part (see `amount_refunded_minor`). |
| `disputed` | A chargeback is open. |

## Error codes

Errors raise `PaymentsError` with `code` set to the backend catalogue code:

| Code | HTTP | Meaning |
|---|---|---|
| `BCK.ORDER.0001` | 400 | Invalid request (amount out of range, unsupported currency / capture mode / provider). |
| `BCK.ORDER.0002` | 404 | No Order with this id. |
| `BCK.ORDER.0003` | 403 | The key is not an active organization, or the amount exceeds the per-order cap. |
| `BCK.ORDER.0004` | 500 | The merchant has no Connect account able to receive card payments. |
| `BCK.ORDER.0005` | 500 | The PaymentIntent could not be created; the Order is `failed`, no money moved. |
| `BCK.ORDER.0007` | 409 | Idempotency-key conflict. |
| `BCK.ORDER.0010` | 429 | Velocity cap exceeded. Retry after backoff. |

```python
from payments_py import PaymentsError

try:
    created = payments.orders.create_order(3437)
except PaymentsError as e:
    if e.code == "BCK.ORDER.0010":
        ...  # back off and retry
    raise
```
