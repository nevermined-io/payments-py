"""Unit tests for ``payments.orders`` (OrdersAPI) — the SDK client for the
browser-fiat Orders endpoints (nvm-monorepo epic #3238, task #3250):

- ``POST /api/v1/orders`` — merchant, server-to-server, authenticated with an
  org-scoped NVM API key.
- ``GET /api/v1/orders/{id}`` — anonymous; the unguessable id is the access
  control, so the SDK sends NO ``Authorization`` header.

``requests`` is mocked with ``requests_mock`` so we can assert on URLs,
headers and bodies without hitting the network. The mock NVM API key is the
same fixture used in ``test_payments.py``.
"""

import json
import os

import pytest
import requests_mock

from payments_py.common.api_version import API_VERSION_HEADER, LOCKED_API_VERSION
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import CreateOrderResult, Order, PaymentOptions
from payments_py.environments import Environments
from payments_py.payments import Payments

TEST_API_KEY = os.getenv(
    "TEST_PROXY_BEARER_TOKEN",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweEVCNDk3OTU2OTRBMDc1QTY0ZTY2MzdmMUU5MGYwMjE0Mzg5YjI0YTMiLCJqdGkiOiIweGMzYjYyMWJkYTM5ZDllYWQyMTUyMDliZWY0MDBhMDEzYjM1YjQ2Zjc1NzM4YWFjY2I5ZjdkYWI0ZjQ5MmM5YjgiLCJleHAiOjE3OTQ2NTUwNjAsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.YMkQUjGh7_m07nj8SKXZReNKSryg9mTU3qwJr_TKYATUixbYQTte3CKucjqvgAGzJAd1Kq2ubz3b37n5Zsllxs",
)

BACKEND = Environments["staging_sandbox"].backend.rstrip("/")
ORDER_ID = "ord_9f2c1a7e-3b4d-4c8a-9e21-0a5b6c7d8e9f"
CLIENT_SECRET = "pi_3PGh9k_secret_9x8y7z"
CREATED = {
    "orderId": ORDER_ID,
    "status": "requires_payment",
    "clientSecret": CLIENT_SECRET,
}
ORDER = {
    "id": ORDER_ID,
    "amountMinor": 3437,
    "currency": "usd",
    "status": "requires_payment",
    "amountRefundedMinor": 0,
    "description": "Cart checkout — 3 items",
    "buyerRef": None,
    "paymentIntentId": "pi_3PGh9k",
    "expiresAt": None,
    "clientSecret": CLIENT_SECRET,
}


def _make_payments():
    return Payments.get_instance(
        PaymentOptions(nvm_api_key=TEST_API_KEY, environment="staging_sandbox")
    )


def test_orders_is_wired_and_follows_the_org_pin():
    payments = _make_payments()
    assert payments.orders is not None
    payments.set_organization_id("org-abc")
    assert payments.orders.get_organization_id() == "org-abc"


class TestCreateOrder:
    def test_posts_body_with_merchant_key_and_returns_result(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.post(f"{BACKEND}/api/v1/orders", status_code=201, json=CREATED)
            result = payments.orders.create_order(
                3437,
                description="Cart checkout — 3 items",
                idempotency_key="idem-8f2c1a",
                # Opaque merchant data must reach the wire verbatim — the SDK's
                # snake→camel body helper must NOT rewrite these keys.
                metadata={"channel": "web", "unit_price": 3437},
                line_items=[{"sku": "PRO-PLAN", "unit_price": 3437, "quantity": 1}],
            )
            req = m.request_history[0]

        assert isinstance(result, CreateOrderResult)
        assert result.order_id == ORDER_ID
        assert result.status == "requires_payment"
        assert result.client_secret == CLIENT_SECRET
        assert req.headers["Authorization"] == f"Bearer {TEST_API_KEY}"
        assert req.headers[API_VERSION_HEADER] == LOCKED_API_VERSION
        assert json.loads(req.body) == {
            "amountMinor": 3437,
            "currency": "usd",
            "description": "Cart checkout — 3 items",
            "idempotencyKey": "idem-8f2c1a",
            "metadata": {"channel": "web", "unit_price": 3437},
            "lineItems": [{"sku": "PRO-PLAN", "unit_price": 3437, "quantity": 1}],
        }

    def test_sends_only_the_fields_the_caller_set(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.post(f"{BACKEND}/api/v1/orders", status_code=201, json=CREATED)
            payments.orders.create_order(100)
            body = json.loads(m.request_history[0].body)
        assert body == {"amountMinor": 100, "currency": "usd"}

    def test_omits_client_secret_when_backend_withholds_it(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/orders",
                status_code=201,
                json={"orderId": ORDER_ID, "status": "failed"},
            )
            result = payments.orders.create_order(100)
        assert result.status == "failed"
        assert result.client_secret is None

    def test_surfaces_catalogue_code_on_refusal(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/orders",
                status_code=403,
                json={
                    "code": "BCK.ORDER.0003",
                    "message": "Order not initiated by an active organization",
                },
            )
            with pytest.raises(PaymentsError) as exc:
                payments.orders.create_order(3437)
        assert exc.value.code == "BCK.ORDER.0003"
        assert "active organization" in str(exc.value)


class TestGetOrder:
    def test_gets_anonymously_and_returns_buyer_safe_view(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/orders/{ORDER_ID}", json=ORDER)
            order = payments.orders.get_order(ORDER_ID)
            req = m.request_history[0]

        assert isinstance(order, Order)
        assert order.id == ORDER_ID
        assert order.amount_minor == 3437
        assert order.currency == "usd"
        assert order.status == "requires_payment"
        assert order.amount_refunded_minor == 0
        assert order.description == "Cart checkout — 3 items"
        assert order.buyer_ref is None
        assert order.payment_intent_id == "pi_3PGh9k"
        assert order.expires_at is None
        assert order.client_secret == CLIENT_SECRET
        # The id IS the access control — never leak the merchant key on the read.
        assert "Authorization" not in req.headers
        assert req.headers[API_VERSION_HEADER] == LOCKED_API_VERSION

    def test_surfaces_bck_order_0002_on_miss(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/orders/ord_missing",
                status_code=404,
                json={"code": "BCK.ORDER.0002", "message": "No order exists"},
            )
            with pytest.raises(PaymentsError) as exc:
                payments.orders.get_order("ord_missing")
        assert exc.value.code == "BCK.ORDER.0002"
