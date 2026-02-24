"""Unit tests for resolve_scheme."""

from unittest.mock import MagicMock

import pytest

from payments_py.x402.resolve_scheme import (
    resolve_scheme,
    clear_scheme_cache,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    """Clear the scheme cache before and after each test."""
    clear_scheme_cache()
    yield
    clear_scheme_cache()


@pytest.fixture
def mock_payments_crypto():
    """Mock Payments that returns a crypto plan."""
    mock = MagicMock()
    mock.plans.get_plan.return_value = {
        "registry": {"price": {"isCrypto": True}},
    }
    return mock


@pytest.fixture
def mock_payments_fiat():
    """Mock Payments that returns a fiat plan."""
    mock = MagicMock()
    mock.plans.get_plan.return_value = {
        "registry": {"price": {"isCrypto": False}},
    }
    return mock


@pytest.fixture
def mock_payments_error():
    """Mock Payments that raises on get_plan."""
    mock = MagicMock()
    mock.plans.get_plan.side_effect = Exception("API error")
    return mock


class TestResolveScheme:
    """Tests for resolve_scheme."""

    def test_explicit_scheme_returns_immediately(self, mock_payments_crypto):
        result = resolve_scheme(
            mock_payments_crypto, "plan-123", explicit_scheme="nvm:card-delegation"
        )
        assert result == "nvm:card-delegation"
        mock_payments_crypto.plans.get_plan.assert_not_called()

    def test_crypto_plan_returns_erc4337(self, mock_payments_crypto):
        result = resolve_scheme(mock_payments_crypto, "plan-123")
        assert result == "nvm:erc4337"
        mock_payments_crypto.plans.get_plan.assert_called_once_with("plan-123")

    def test_fiat_plan_returns_card_delegation(self, mock_payments_fiat):
        result = resolve_scheme(mock_payments_fiat, "plan-fiat")
        assert result == "nvm:card-delegation"
        mock_payments_fiat.plans.get_plan.assert_called_once_with("plan-fiat")

    def test_error_falls_back_to_erc4337(self, mock_payments_error):
        result = resolve_scheme(mock_payments_error, "plan-broken")
        assert result == "nvm:erc4337"

    def test_cache_prevents_repeated_api_calls(self, mock_payments_fiat):
        resolve_scheme(mock_payments_fiat, "plan-cached")
        resolve_scheme(mock_payments_fiat, "plan-cached")
        resolve_scheme(mock_payments_fiat, "plan-cached")
        # Only one API call despite three resolve calls
        mock_payments_fiat.plans.get_plan.assert_called_once()

    def test_different_plan_ids_cached_separately(self, mock_payments_fiat):
        resolve_scheme(mock_payments_fiat, "plan-a")
        resolve_scheme(mock_payments_fiat, "plan-b")
        assert mock_payments_fiat.plans.get_plan.call_count == 2

    def test_missing_registry_defaults_to_erc4337(self):
        """Plan without registry key defaults to erc4337."""
        mock = MagicMock()
        mock.plans.get_plan.return_value = {}
        result = resolve_scheme(mock, "plan-no-registry")
        assert result == "nvm:erc4337"

    def test_missing_price_defaults_to_erc4337(self):
        """Plan with registry but no price defaults to erc4337."""
        mock = MagicMock()
        mock.plans.get_plan.return_value = {"registry": {}}
        result = resolve_scheme(mock, "plan-no-price")
        assert result == "nvm:erc4337"
