# Onboarding White-Label Customers

`payments.organizations.onboard_customer(email)` provisions a Nevermined
account for one of your **customers** under your organization — without
consuming a member seat — and returns a usable, scoped API key your
organization can use to act on that customer's behalf (purchase plans, redeem
credits). The customer is recorded in your organization's Customers list.

This is the white-label counterpart to `create_member`: a member is a person
who logs into your organization; a customer is an end user you transact for.
Unlike `create_member` (which returns a non-usable lookup hash), this returns
the **real** usable key.

> Admin-only. The call authenticates with your organization's API key.

## Two outcomes

`onboard_customer` wraps `POST /api/v1/organizations/account` with
`as="customer"` and returns a `CustomerOnboardingResponse` in one of two shapes:

| Outcome | When | Result |
|---------|------|--------|
| **Key issued** | The email is new, or already your organization's customer | `consent_required=False`, plus `nvm_api_key`, `user_id`, `user_wallet`, `is_customer`, `customer_recorded` |
| **Consent required** | The email belongs to an account your organization does **not** own | `consent_required=True` only — no key, no identity. An email challenge is sent to the owner |

The consent path is deliberately opaque: the SDK surfaces neither the key nor
the account's identity, so the call cannot be used to probe which emails have
Nevermined accounts. Once the owner consents (via the emailed challenge), call
`onboard_customer` again with the same email to complete onboarding and receive
the key.

## Usage

```python
from payments_py import Payments, PaymentOptions

payments = Payments.get_instance(
    PaymentOptions(nvm_api_key=ORG_ADMIN_API_KEY)
)

result = payments.organizations.onboard_customer("customer@example.com")

if result.consent_required:
    # Existing account not owned by this org — a consent email was sent.
    # Retry once the owner approves.
    print("Consent pending — ask the customer to check their email.")
else:
    # Store this key; use it to transact for the customer.
    print("Onboarded:", result.user_id)
    customer_payments = Payments.get_instance(
        PaymentOptions(nvm_api_key=result.nvm_api_key)
    )
    # customer_payments can now purchase plans and redeem credits.
```

## Scoped permissions

The issued key is intentionally limited: it can **purchase and redeem credits**,
but cannot register agents or mint credits. This keeps a customer credential
useful for consumption flows while withholding the builder-side capabilities
that belong to your organization's own members.

## Errors

`onboard_customer` raises `PaymentsError` when `email` is empty, when the
backend call fails, or when a completed (non-consent) onboarding returns no
usable key — the SDK fails loudly rather than hand back a result with missing
credentials.

## Next Steps

- [Payments and Balance](06-payments-and-balance.md) - Purchase plans and redeem credits with the issued key
- [Payment Plans](03-payment-plans.md) - The plans a customer can be onboarded onto
