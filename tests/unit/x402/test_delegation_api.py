"""Unit tests for DelegationAPI."""

from unittest.mock import patch, MagicMock

import pytest
import requests

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.delegation_api import (
    DelegationAPI,
    DelegationSummary,
    PaymentMethodSummary,
)


@pytest.fixture
def mock_options():
    """Create mock PaymentOptions."""
    mock = MagicMock()
    mock.nvm_api_key = "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
    mock.environment = "sandbox"
    mock.return_url = ""
    mock.app_id = None
    mock.version = None
    return mock


class TestPaymentMethodSummary:
    """Tests for PaymentMethodSummary model."""

    def test_from_camel_case(self):
        data = {
            "id": "pm_123",
            "brand": "visa",
            "last4": "4242",
            "expMonth": 12,
            "expYear": 2028,
        }
        pm = PaymentMethodSummary.model_validate(data)
        assert pm.id == "pm_123"
        assert pm.brand == "visa"
        assert pm.last4 == "4242"
        assert pm.exp_month == 12
        assert pm.exp_year == 2028

    def test_from_snake_case(self):
        pm = PaymentMethodSummary(
            id="pm_456",
            brand="mastercard",
            last4="5555",
            exp_month=6,
            exp_year=2027,
        )
        assert pm.id == "pm_456"
        assert pm.brand == "mastercard"

    def test_serialization(self):
        pm = PaymentMethodSummary(
            id="pm_789",
            brand="amex",
            last4="0001",
            exp_month=1,
            exp_year=2030,
        )
        data = pm.model_dump(by_alias=True)
        assert data["expMonth"] == 1
        assert data["expYear"] == 2030


class TestDelegationAPIListPaymentMethods:
    """Tests for DelegationAPI.list_payment_methods."""

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_success(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "id": "pm_1",
                "brand": "visa",
                "last4": "4242",
                "expMonth": 12,
                "expYear": 2028,
            },
            {
                "id": "pm_2",
                "brand": "mastercard",
                "last4": "5555",
                "expMonth": 6,
                "expYear": 2027,
            },
        ]
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        methods = api.list_payment_methods()

        assert len(methods) == 2
        assert methods[0].id == "pm_1"
        assert methods[0].brand == "visa"
        assert methods[1].id == "pm_2"
        assert methods[1].brand == "mastercard"


class TestDelegationSummary:
    """Tests for DelegationSummary model."""

    def test_from_camel_case(self):
        data = {
            "id": "del_abc",
            "cardId": "card_xyz",
            "spendingLimitCents": 5000,
            "spentCents": 1200,
            "durationSecs": 604800,
            "currency": "usd",
            "status": "active",
            "createdAt": "2024-01-01T00:00:00Z",
            "expiresAt": "2024-01-08T00:00:00Z",
        }
        d = DelegationSummary.model_validate(data)
        assert d.id == "del_abc"
        assert d.card_id == "card_xyz"
        assert d.spending_limit_cents == 5000
        assert d.spent_cents == 1200
        assert d.duration_secs == 604800
        assert d.currency == "usd"
        assert d.status == "active"
        assert d.created_at == "2024-01-01T00:00:00Z"
        assert d.expires_at == "2024-01-08T00:00:00Z"

    def test_optional_fields_default_to_none(self):
        d = DelegationSummary(id="del_min")
        assert d.card_id is None
        assert d.spending_limit_cents is None
        assert d.spent_cents is None
        assert d.duration_secs is None
        assert d.currency is None
        assert d.status is None
        assert d.created_at is None
        assert d.expires_at is None

    def test_serialization(self):
        d = DelegationSummary(
            id="del_ser",
            card_id="card_1",
            spending_limit_cents=1000,
            spent_cents=500,
            duration_secs=3600,
            currency="usd",
            status="active",
            created_at="2024-06-01T00:00:00Z",
            expires_at="2024-06-02T00:00:00Z",
        )
        data = d.model_dump(by_alias=True)
        assert data["cardId"] == "card_1"
        assert data["spendingLimitCents"] == 1000
        assert data["spentCents"] == 500
        assert data["durationSecs"] == 3600
        assert data["createdAt"] == "2024-06-01T00:00:00Z"
        assert data["expiresAt"] == "2024-06-02T00:00:00Z"


class TestDelegationAPIListDelegations:
    """Tests for DelegationAPI.list_delegations."""

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_success(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "id": "del_1",
                "cardId": "card_a",
                "spendingLimitCents": 10000,
                "spentCents": 0,
                "durationSecs": 604800,
                "currency": "usd",
                "status": "active",
                "createdAt": "2024-01-01T00:00:00Z",
                "expiresAt": "2024-01-08T00:00:00Z",
            },
            {
                "id": "del_2",
                "cardId": "card_b",
                "spendingLimitCents": 2000,
                "spentCents": 500,
                "durationSecs": 86400,
                "currency": "usd",
                "status": "expired",
                "createdAt": "2024-02-01T00:00:00Z",
                "expiresAt": "2024-02-02T00:00:00Z",
            },
        ]
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        delegations = api.list_delegations()

        assert len(delegations) == 2
        assert delegations[0].id == "del_1"
        assert delegations[0].card_id == "card_a"
        assert delegations[0].spending_limit_cents == 10000
        assert delegations[0].spent_cents == 0
        assert delegations[0].status == "active"
        assert delegations[1].id == "del_2"
        assert delegations[1].status == "expired"

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_http_error_with_json_message(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.json.return_value = {"message": "Forbidden"}
        http_err = requests.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_err
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        with pytest.raises(PaymentsError) as exc_info:
            api.list_delegations()

        assert "Forbidden" in str(exc_info.value)
        assert "403" in str(exc_info.value)
        assert exc_info.value.code == "internal"

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_http_error_without_json(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.json.side_effect = ValueError("no JSON")
        http_err = requests.HTTPError(response=mock_response)
        mock_response.raise_for_status.side_effect = http_err
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        with pytest.raises(PaymentsError) as exc_info:
            api.list_delegations()

        assert "Failed to list delegations" in str(exc_info.value)
        assert "500" in str(exc_info.value)
        assert exc_info.value.code == "internal"

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_network_error(self, mock_get, mock_options):
        mock_get.side_effect = requests.ConnectionError("connection refused")

        api = DelegationAPI(mock_options)
        with pytest.raises(PaymentsError) as exc_info:
            api.list_delegations()

        assert "Network error while listing delegations" in str(exc_info.value)
        assert exc_info.value.code == "internal"
