"""Unit tests for DelegationAPI."""

from unittest.mock import patch, MagicMock

import pytest

from payments_py.x402.delegation_api import DelegationAPI, PaymentMethodSummary


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

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_forwards_provider_query_param_when_set(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        api.list_payment_methods(provider="stripe")

        # The provider is forwarded as a ?provider= query param via requests' params.
        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"provider": "stripe"}

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_omits_provider_query_param_when_not_set(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        api.list_payment_methods()

        # No provider → params is None so the default "all methods" behaviour holds.
        _, kwargs = mock_get.call_args
        assert kwargs["params"] is None

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_forwards_erc4337_provider(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = []
        mock_get.return_value = mock_response

        api = DelegationAPI(mock_options)
        api.list_payment_methods(provider="erc4337")

        _, kwargs = mock_get.call_args
        assert kwargs["params"] == {"provider": "erc4337"}
