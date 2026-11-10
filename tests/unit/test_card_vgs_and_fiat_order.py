"""Pins the SDK side of two card flows against what the backend accepts and
returns (nvm-monorepo #4990):

1. ``create_delegation`` accepts ``provider="vgs"`` (a card enrolled through the
   credit/debit card form) with its ``CRD…`` card id.
2. ``order_fiat_plan`` posts ``{"planId": …}`` to ``/api/v1/fiat/stripe/payment``
   and returns the Stripe PaymentIntent the backend answers with.

``requests`` is mocked with ``requests_mock``. The NVM API key is a throwaway
JWT minted per test run, never a committed credential.
"""

import json

import jwt
import pytest
import requests_mock

from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions, StripePaymentIntent
from payments_py.environments import Environments
from payments_py.payments import Payments
from payments_py.x402.types import CreateDelegationPayload

TEST_API_KEY = "sandbox-staging:" + jwt.encode(
    {"sub": "0x0000000000000000000000000000000000000001", "o11y": "test-o11y"},
    "unit-test-secret-not-a-real-credential-0123456789",
    algorithm="HS256",
)

BACKEND = Environments["staging_sandbox"].backend.rstrip("/")
PAYMENT_INTENT = {
    "id": "pi_3O4KfNBYvSRKcV42",
    "object": "payment_intent",
    "client_secret": "pi_3O4KfNBYvSRKcV42_secret_ABC",
    "status": "requires_payment_method",
    "amount": 1000,
    "currency": "usd",
    "on_behalf_of": "acct_1SellerConnect",
}


def _make_payments():
    return Payments.get_instance(
        PaymentOptions(nvm_api_key=TEST_API_KEY, environment="staging_sandbox")
    )


def test_create_delegation_posts_a_vgs_payload_with_the_crd_card_id():
    payments = _make_payments()
    with requests_mock.Mocker() as m:
        m.post(
            f"{BACKEND}/api/v1/delegation/create",
            json={"delegationId": "del_vgs_1234", "delegationToken": "tok_xyz"},
        )
        response = payments.delegation.create_delegation(
            CreateDelegationPayload(
                provider="vgs",
                provider_payment_method_id="CRDrX94aaaJz7oTFy2i13964k",
                spending_limit_cents=10_000,
                duration_secs=3_600,
                currency="usd",
            )
        )
        req = m.request_history[0]

    assert json.loads(req.body) == {
        "provider": "vgs",
        "providerPaymentMethodId": "CRDrX94aaaJz7oTFy2i13964k",
        "spendingLimitCents": 10_000,
        "durationSecs": 3_600,
        "currency": "usd",
    }
    assert response.delegation_id == "del_vgs_1234"


class TestOrderFiatPlan:
    def test_posts_plan_id_and_returns_the_payment_intent(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/fiat/stripe/payment",
                status_code=201,
                json=PAYMENT_INTENT,
            )
            result = payments.plans.order_fiat_plan("plan-123")
            req = m.request_history[0]

        assert json.loads(req.body) == {"planId": "plan-123"}
        assert isinstance(result, StripePaymentIntent)
        assert result.model_dump() == {
            "id": "pi_3O4KfNBYvSRKcV42",
            "client_secret": "pi_3O4KfNBYvSRKcV42_secret_ABC",
            "status": "requires_payment_method",
            "amount": 1000,
            "currency": "usd",
        }

    def test_a_4xx_raises_payments_error(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/fiat/stripe/payment",
                status_code=400,
                json={
                    "code": "BCK.STRIPE.0003",
                    "message": "Unable to create Stripe payment intent",
                },
            )
            with pytest.raises(PaymentsError):
                payments.plans.order_fiat_plan("plan-123")
