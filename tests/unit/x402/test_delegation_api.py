"""Unit tests for DelegationAPI."""

from unittest.mock import patch, MagicMock

import pytest

from payments_py.x402.delegation_api import DelegationAPI, PaymentMethodSummary
from payments_py.x402.types import CardDelegationConfig


class TestCardDelegationConfigValidator:
    """Tests for CardDelegationConfig model_validator."""

    # --- valid combinations ---

    def test_valid_delegation_id_only(self):
        cfg = CardDelegationConfig(delegation_id="del-abc")
        assert cfg.delegation_id == "del-abc"

    def test_valid_card_id_only(self):
        cfg = CardDelegationConfig(card_id="pm-card-123")
        assert cfg.card_id == "pm-card-123"

    def test_valid_card_id_with_overrides(self):
        cfg = CardDelegationConfig(
            card_id="pm-card-123",
            spending_limit_cents=5000,
            duration_secs=3600,
        )
        assert cfg.card_id == "pm-card-123"
        assert cfg.spending_limit_cents == 5000

    def test_valid_new_delegation_all_three_fields(self):
        cfg = CardDelegationConfig(
            provider_payment_method_id="pm_stripe_123",
            spending_limit_cents=10000,
            duration_secs=604800,
        )
        assert cfg.provider_payment_method_id == "pm_stripe_123"
        assert cfg.spending_limit_cents == 10000
        assert cfg.duration_secs == 604800

    def test_valid_new_delegation_with_extra_fields(self):
        cfg = CardDelegationConfig(
            provider_payment_method_id="pm_stripe_123",
            spending_limit_cents=10000,
            duration_secs=604800,
            currency="eur",
            max_transactions=5,
        )
        assert cfg.currency == "eur"
        assert cfg.max_transactions == 5

    def test_valid_via_alias(self):
        cfg = CardDelegationConfig.model_validate({"delegationId": "del-xyz"})
        assert cfg.delegation_id == "del-xyz"

    # --- invalid combinations ---

    def test_invalid_empty_config_raises(self):
        with pytest.raises(ValueError, match="requires at least one of"):
            CardDelegationConfig()

    def test_invalid_new_delegation_missing_spending_limit(self):
        with pytest.raises(ValueError, match="spending_limit_cents"):
            CardDelegationConfig(
                provider_payment_method_id="pm_stripe_123",
                duration_secs=604800,
            )

    def test_invalid_new_delegation_missing_duration(self):
        with pytest.raises(ValueError, match="duration_secs"):
            CardDelegationConfig(
                provider_payment_method_id="pm_stripe_123",
                spending_limit_cents=10000,
            )

    def test_invalid_new_delegation_missing_provider_method(self):
        with pytest.raises(ValueError, match="provider_payment_method_id"):
            CardDelegationConfig(
                spending_limit_cents=10000,
                duration_secs=604800,
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
