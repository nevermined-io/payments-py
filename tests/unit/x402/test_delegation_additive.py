"""Unit tests for the additive DelegationAPI surface (payments-py#308 parity):
the ``accessible`` filter on the two list methods and ``update_payment_method`` +
``UpdatePaymentMethodDto``. Mirrors ``src/x402/delegation-api.ts``.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from payments_py.x402.delegation_api import DelegationAPI
from payments_py.x402.types import UpdatePaymentMethodDto


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


class TestAccessibleFilter:
    @patch("payments_py.x402.delegation_api.requests.get")
    def test_payment_methods_accessible_true_sets_param(self, mock_get, mock_options):
        mock_get.return_value = _ok([])
        DelegationAPI(mock_options).list_payment_methods(accessible=True)
        assert mock_get.call_args.kwargs["params"]["accessible"] == "true"

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_payment_methods_default_omits_accessible(self, mock_get, mock_options):
        mock_get.return_value = _ok([])
        DelegationAPI(mock_options).list_payment_methods()
        assert mock_get.call_args.kwargs["params"] is None

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_payment_methods_provider_and_accessible_combine(
        self, mock_get, mock_options
    ):
        mock_get.return_value = _ok([])
        DelegationAPI(mock_options).list_payment_methods(
            provider="stripe", accessible=True
        )
        params = mock_get.call_args.kwargs["params"]
        assert params["provider"] == "stripe"
        assert params["accessible"] == "true"

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_delegations_accessible_true_sets_param(self, mock_get, mock_options):
        mock_get.return_value = _ok([])
        DelegationAPI(mock_options).list_delegations(accessible=True)
        assert mock_get.call_args.kwargs["params"] == {"accessible": "true"}

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_delegations_default_omits_accessible(self, mock_get, mock_options):
        mock_get.return_value = _ok([])
        DelegationAPI(mock_options).list_delegations()
        assert mock_get.call_args.kwargs["params"] is None


class TestUpdatePaymentMethod:
    @patch("payments_py.x402.delegation_api.requests.patch")
    def test_patches_and_returns_summary(self, mock_patch, mock_options):
        mock_patch.return_value = _ok({"id": "pm_1", "brand": "visa", "last4": "4242"})
        result = DelegationAPI(mock_options).update_payment_method(
            "pm_1", UpdatePaymentMethodDto(alias="work card")
        )
        assert result.id == "pm_1"
        url = mock_patch.call_args.args[0]
        assert url.endswith("/api/v1/payment-methods/pm_1")

    @patch("payments_py.x402.delegation_api.requests.patch")
    def test_alias_only_omits_allowed_keys(self, mock_patch, mock_options):
        mock_patch.return_value = _ok({"id": "pm_1", "brand": "visa", "last4": "4242"})
        DelegationAPI(mock_options).update_payment_method(
            "pm_1", UpdatePaymentMethodDto(alias="work card")
        )
        body = json.loads(mock_patch.call_args.kwargs["data"])
        assert body == {"alias": "work card"}  # allowedApiKeyIds not sent (unset)

    @patch("payments_py.x402.delegation_api.requests.patch")
    def test_explicit_none_clears_allow_list(self, mock_patch, mock_options):
        # exclude_unset keeps an EXPLICIT None → sends null to clear the allow-list.
        mock_patch.return_value = _ok({"id": "pm_1", "brand": "visa", "last4": "4242"})
        DelegationAPI(mock_options).update_payment_method(
            "pm_1", UpdatePaymentMethodDto(allowed_api_key_ids=None)
        )
        body = json.loads(mock_patch.call_args.kwargs["data"])
        assert body == {"allowedApiKeyIds": None}

    @patch("payments_py.x402.delegation_api.requests.patch")
    def test_sets_allow_list(self, mock_patch, mock_options):
        mock_patch.return_value = _ok({"id": "pm_1", "brand": "visa", "last4": "4242"})
        DelegationAPI(mock_options).update_payment_method(
            "pm_1", UpdatePaymentMethodDto(allowed_api_key_ids=["k1", "k2"])
        )
        body = json.loads(mock_patch.call_args.kwargs["data"])
        assert body == {"allowedApiKeyIds": ["k1", "k2"]}
