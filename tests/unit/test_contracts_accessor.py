"""Unit tests for the ``payments.contracts`` accessor + ContractsAPI parity
(payments-py#308). Mirrors ``src/api/contracts-api.ts`` and ``src/payments.ts``:
TS exposes the ``ContractsAPI`` on ``payments.contracts`` with
``getContractAddress`` / ``getPayAsYouGoTemplateAddress``.
"""

from unittest.mock import MagicMock, patch

import pytest

from payments_py.api.contracts_api import ContractsAPI
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions

# Real deployments return every contract; the strict Contracts model requires
# all of them, so the fixture carries the full set (PayAsYouGo / Fixed get the
# addresses the tests assert on, the rest a placeholder).
_PLACEHOLDER = "0x0000000000000000000000000000000000000000"
_CONTRACT_NAMES = [
    "AccessManager",
    "AgreementsStore",
    "AssetsRegistry",
    "DistributePaymentsCondition",
    "FiatPaymentTemplate",
    "FiatSettlementCondition",
    "FixedPaymentTemplate",
    "LinearPricing",
    "LockPaymentCondition",
    "NFT1155Credits",
    "NFT1155ExpirableCredits",
    "NFT1155ExpirableCreditsV2",
    "NVMConfig",
    "OneTimeCreatorHook",
    "PayAsYouGoTemplate",
    "PaymentsVault",
    "ProtocolStandardFees",
    "TokenUtils",
    "TransferCreditsCondition",
]
_CONTRACTS = {name: _PLACEHOLDER for name in _CONTRACT_NAMES}
_CONTRACTS["PayAsYouGoTemplate"] = "0x1111111111111111111111111111111111111111"
_CONTRACTS["FixedPaymentTemplate"] = "0x2222222222222222222222222222222222222222"

_DEPLOYMENT = {"deployment": {"version": "3.0.0", "contracts": _CONTRACTS}}


def _opts():
    return PaymentOptions(
        nvm_api_key=(
            "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
            "eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJ0ZXN0In0.fake"
        ),
        environment="sandbox",
    )


def _ok(body):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = body
    return resp


class TestContractsAPIMethods:
    @patch("payments_py.api.contracts_api.requests.get")
    def test_get_contract_address(self, mock_get):
        mock_get.return_value = _ok(_DEPLOYMENT)
        api = ContractsAPI(_opts())
        assert (
            api.get_contract_address("FixedPaymentTemplate")
            == "0x2222222222222222222222222222222222222222"
        )

    @patch("payments_py.api.contracts_api.requests.get")
    def test_get_pay_as_you_go_template_address(self, mock_get):
        mock_get.return_value = _ok(_DEPLOYMENT)
        api = ContractsAPI(_opts())
        assert (
            api.get_pay_as_you_go_template_address()
            == "0x1111111111111111111111111111111111111111"
        )

    @patch("payments_py.api.contracts_api.requests.get")
    def test_unknown_contract_raises(self, mock_get):
        mock_get.return_value = _ok(_DEPLOYMENT)
        api = ContractsAPI(_opts())
        with pytest.raises(PaymentsError):
            api.get_contract_address("NopeDoesNotExist")


class TestPaymentsContractsAccessor:
    def test_contracts_is_the_api_not_the_model(self):
        from payments_py.payments import Payments

        payments = Payments.get_instance(_opts())
        # TS parity: payments.contracts IS the ContractsAPI.
        assert isinstance(payments.contracts, ContractsAPI)
        # Methods are reachable straight off the accessor.
        assert hasattr(payments.contracts, "get_contract_address")
        assert hasattr(payments.contracts, "get_pay_as_you_go_template_address")
        # The address data-model stays reachable (one hop in, like the API's
        # shape). Check the class so we don't trigger the network-fetching
        # property in a unit test.
        assert isinstance(type(payments.contracts).contracts, property)
        # Back-compat alias still resolves to the same API.
        assert payments.contracts is payments.contracts_api

    @patch("payments_py.api.contracts_api.requests.get")
    def test_deprecated_snake_address_still_resolves(self, mock_get):
        # Back-compat: the snake_case address access still works (via
        # __getattr__ → the Contracts model) but warns. A missing name raises
        # AttributeError without touching the network. payments.contracts IS a
        # ContractsAPI, so the shim applies there too.
        mock_get.return_value = _ok(_DEPLOYMENT)
        api = ContractsAPI(_opts())
        with pytest.warns(DeprecationWarning):
            addr = api.pay_as_you_go_template
        assert addr == "0x1111111111111111111111111111111111111111"
        with pytest.raises(AttributeError):
            _ = api.not_a_real_contract
