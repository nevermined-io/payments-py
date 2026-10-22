"""Unit tests for the DelegationAPI model/envelope realignment (payments-py#308).

The backend ``GET /delegation`` returns a **paginated envelope**
(``DelegationListDto`` in nvm-monorepo:
``apps/api/src/delegation/dto/delegation-response.dto.ts``) —
``{delegations, totalResults, page, offset}`` — not a bare array, and
``DelegationSummaryDto`` uses ``delegationId`` / ``providerPaymentMethodId`` /
``amountSpentCents`` / ``remainingBudgetCents`` / ``transactionCount`` /
``apiKeyId`` with the cents figures as **strings**. These tests pin the Python
models to that wire shape and mirror ``src/x402/delegation-api.ts``.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from payments_py.x402.delegation_api import (
    DelegationAPI,
    DelegationListResponse,
    DelegationSummary,
    PaymentMethodSummary,
    PurchasingPower,
)


@pytest.fixture
def mock_options():
    mock = MagicMock()
    mock.nvm_api_key = (
        "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
    )
    mock.environment = "sandbox"
    mock.return_url = ""
    mock.app_id = None
    mock.version = None
    return mock


def _ok(json_body):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.ok = True
    resp.json.return_value = json_body
    return resp


# A delegation exactly as the backend serializes it (camelCase, cents as strings).
_WIRE_DELEGATION = {
    "delegationId": "a1b2c3d4-e5f6-4a90-8bcd-ef1234567890",
    "provider": "stripe",
    "providerPaymentMethodId": "pm_1Abc2Def3Ghi4Jkl",
    "status": "Active",
    "spendingLimitCents": "10000",
    "amountSpentCents": "2500",
    "remainingBudgetCents": "7500",
    "currency": "usd",
    "transactionCount": 12,
    "expiresAt": "2026-02-20T00:00:00Z",
    "createdAt": "2026-02-13T10:30:00Z",
    "apiKeyId": None,
}

_WIRE_ENVELOPE = {
    "delegations": [_WIRE_DELEGATION],
    "totalResults": 1,
    "page": 1,
    "offset": 0,
}


class TestDelegationSummaryWireShape:
    def test_parses_backend_camelcase_fields(self):
        d = DelegationSummary.model_validate(_WIRE_DELEGATION)
        assert d.delegation_id == "a1b2c3d4-e5f6-4a90-8bcd-ef1234567890"
        assert d.provider == "stripe"
        assert d.provider_payment_method_id == "pm_1Abc2Def3Ghi4Jkl"
        assert d.status == "Active"
        assert d.transaction_count == 12
        assert d.api_key_id is None

    def test_cents_are_strings_not_coerced(self):
        # TS types these as `string`; the backend sends strings. Keep them
        # strings so the micros-rounded figures survive untouched.
        d = DelegationSummary.model_validate(_WIRE_DELEGATION)
        assert d.spending_limit_cents == "10000"
        assert d.amount_spent_cents == "2500"
        assert d.remaining_budget_cents == "7500"


class TestListDelegationsEnvelope:
    @patch("payments_py.x402.delegation_api.requests.get")
    def test_returns_paginated_envelope(self, mock_get, mock_options):
        mock_get.return_value = _ok(_WIRE_ENVELOPE)
        result = DelegationAPI(mock_options).list_delegations()
        assert isinstance(result, DelegationListResponse)
        assert result.total_results == 1
        assert result.page == 1
        assert result.offset == 0
        assert len(result.delegations) == 1
        assert result.delegations[0].remaining_budget_cents == "7500"

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_tolerates_bare_list_during_rollout(self, mock_get, mock_options):
        # A backend that has not yet shipped the envelope returns a bare array;
        # wrap it so the SDK keeps working across the deployment window.
        mock_get.return_value = _ok([_WIRE_DELEGATION])
        result = DelegationAPI(mock_options).list_delegations()
        assert isinstance(result, DelegationListResponse)
        assert result.total_results == 1
        assert len(result.delegations) == 1

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_malformed_body_raises_not_silently_empty(self, mock_get, mock_options):
        # A glitch body with no `delegations` key must raise, not read as zero.
        from payments_py.common.payments_error import PaymentsError

        mock_get.return_value = _ok({})
        with pytest.raises(PaymentsError):
            DelegationAPI(mock_options).list_delegations()


class TestPaymentMethodSummaryAddedFields:
    def test_parses_alias_status_allowed_keys(self):
        pm = PaymentMethodSummary.model_validate(
            {
                "id": "pm_1",
                "type": "card",
                "brand": "visa",
                "last4": "4242",
                "expMonth": 12,
                "expYear": 2027,
                "alias": "work card",
                "provider": "stripe",
                "status": "Active",
                "allowedApiKeyIds": ["k1", "k2"],
            }
        )
        assert pm.alias == "work card"
        assert pm.status == "Active"
        assert pm.allowed_api_key_ids == ["k1", "k2"]


class TestGetPurchasingPower:
    @patch("payments_py.x402.delegation_api.requests.get")
    def test_sums_remaining_budget_and_filters_accessible(self, mock_get, mock_options):
        cards = [{"id": "pm_1", "brand": "visa", "last4": "4242"}]
        envelope = {
            "delegations": [
                {**_WIRE_DELEGATION, "remainingBudgetCents": "7500"},
                {**_WIRE_DELEGATION, "remainingBudgetCents": "2500"},
            ],
            "totalResults": 2,
            "page": 1,
            "offset": 0,
        }
        # First GET → payment-methods, second GET → delegation
        mock_get.side_effect = [_ok(cards), _ok(envelope)]

        power = DelegationAPI(mock_options).get_purchasing_power()

        assert isinstance(power, PurchasingPower)
        assert power.total_remaining_budget_cents == 10000
        assert power.currency == "usd"
        assert len(power.cards) == 1
        assert len(power.delegations) == 2
        # Both underlying calls must request only accessible items.
        first_params = mock_get.call_args_list[0].kwargs["params"]
        second_params = mock_get.call_args_list[1].kwargs["params"]
        assert first_params["accessible"] == "true"
        assert second_params == {"accessible": "true"}

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_non_numeric_budget_counts_as_zero(self, mock_get, mock_options):
        # Mirrors JS `parseInt(x, 10) || 0`: a missing/garbage figure is 0, not a
        # crash. Exercises BOTH except branches: None (TypeError) and a
        # non-numeric string (ValueError) — a real backend could send either.
        envelope = {
            "delegations": [
                {**_WIRE_DELEGATION, "remainingBudgetCents": None},
                {**_WIRE_DELEGATION, "remainingBudgetCents": "not-a-number"},
                {**_WIRE_DELEGATION, "remainingBudgetCents": "500"},
            ],
            "totalResults": 3,
            "page": 1,
            "offset": 0,
        }
        mock_get.side_effect = [_ok([]), _ok(envelope)]
        power = DelegationAPI(mock_options).get_purchasing_power()
        assert power.total_remaining_budget_cents == 500

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_falsy_currency_on_present_delegation_defaults_to_usd(
        self, mock_get, mock_options
    ):
        # delegations are present but the first one's currency is falsy (None) —
        # the fallback must still yield 'usd', not None.
        envelope = {
            "delegations": [{**_WIRE_DELEGATION, "currency": None}],
            "totalResults": 1,
            "page": 1,
            "offset": 0,
        }
        mock_get.side_effect = [_ok([]), _ok(envelope)]
        power = DelegationAPI(mock_options).get_purchasing_power()
        assert power.currency == "usd"
        assert len(power.delegations) == 1

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_non_default_currency_label_and_sum(self, mock_get, mock_options):
        # A real non-'usd' currency must drive BOTH the label and the sum —
        # pins that the fallback isn't just hardcoded to 'usd'.
        envelope = {
            "delegations": [
                {**_WIRE_DELEGATION, "currency": "eur", "remainingBudgetCents": "300"},
                {**_WIRE_DELEGATION, "currency": "eur", "remainingBudgetCents": "200"},
            ],
            "totalResults": 2,
            "page": 1,
            "offset": 0,
        }
        mock_get.side_effect = [_ok([]), _ok(envelope)]
        power = DelegationAPI(mock_options).get_purchasing_power()
        assert power.currency == "eur"
        assert power.total_remaining_budget_cents == 500

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_mixed_currency_totals_only_the_label_currency(
        self, mock_get, mock_options
    ):
        # Label = first delegation's currency; the total sums only that
        # currency (a EUR delegation must not inflate a USD total).
        envelope = {
            "delegations": [
                {**_WIRE_DELEGATION, "currency": "usd", "remainingBudgetCents": "7500"},
                {**_WIRE_DELEGATION, "currency": "eur", "remainingBudgetCents": "9999"},
            ],
            "totalResults": 2,
            "page": 1,
            "offset": 0,
        }
        mock_get.side_effect = [_ok([]), _ok(envelope)]
        power = DelegationAPI(mock_options).get_purchasing_power()
        assert power.currency == "usd"
        assert power.total_remaining_budget_cents == 7500

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_empty_defaults_to_usd(self, mock_get, mock_options):
        empty = {"delegations": [], "totalResults": 0, "page": 1, "offset": 0}
        mock_get.side_effect = [_ok([]), _ok(empty)]
        power = DelegationAPI(mock_options).get_purchasing_power()
        assert power.total_remaining_budget_cents == 0
        assert power.currency == "usd"
        assert power.delegations == []
