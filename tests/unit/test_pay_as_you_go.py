"""
Unit tests for plan helper functions.
"""

from unittest.mock import MagicMock

import pytest
import requests_mock

import payments_py
from payments_py.api.nvm_api import API_URL_INFO, API_URL_REGISTER_PLAN
from payments_py.api.plans_api import PlansAPI
from payments_py.common.types import PlanMetadata
from payments_py.environments import ZeroAddress
from payments_py.payments import Payments
from payments_py.plans import (
    get_fiat_pay_as_you_go_price_config,
    get_fiat_price_config,
    get_pay_as_you_go_price_config,
    get_pay_as_you_go_credits_config,
)
from tests.unit.test_contracts_accessor import _CONTRACTS, _DEPLOYMENT, _opts

# Test ERC20 token address (USDC on Base Sepolia)
TEST_ERC20_TOKEN = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
RECEIVER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
TEST_RECEIVER = RECEIVER
TEST_TEMPLATE = "0x5e852077b30099106Aa65B4d329FFF9b5C9a8e7C"


class TestPayAsYouGoHelperFunctions:
    """Unit tests for Pay As You Go helper functions."""

    def test_pay_as_you_go_price_config_requires_template_address(self):
        """Test that get_pay_as_you_go_price_config requires template_address parameter."""
        receiver = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"

        # Should raise ValueError when template_address is not provided
        with pytest.raises(ValueError, match="template_address is required"):
            get_pay_as_you_go_price_config(100, receiver)

    def test_pay_as_you_go_price_config_with_template_address(self):
        """Test that get_pay_as_you_go_price_config works with provided template address."""
        receiver = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        template_address = "0x5e852077b30099106Aa65B4d329FFF9b5C9a8e7C"
        price_config = get_pay_as_you_go_price_config(
            100, receiver, template_address=template_address
        )

        assert price_config.template_address == template_address
        assert price_config.is_crypto is True
        assert price_config.amounts == [100]
        assert price_config.receivers == [receiver]
        assert price_config.token_address == ZeroAddress

    def test_pay_as_you_go_price_config_with_erc20(self):
        """Test that get_pay_as_you_go_price_config works with ERC20 tokens."""
        receiver = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        token = TEST_ERC20_TOKEN
        template_address = "0x5e852077b30099106Aa65B4d329FFF9b5C9a8e7C"
        price_config = get_pay_as_you_go_price_config(
            200, receiver, token, template_address=template_address
        )

        assert price_config.template_address == template_address
        assert price_config.token_address == token
        assert price_config.amounts == [200]
        # Crypto whatever the token: the docs send card plans elsewhere
        assert price_config.is_crypto is True

    def test_pay_as_you_go_price_config_invalid_receiver(self):
        """Test that get_pay_as_you_go_price_config raises on invalid receiver."""
        template_address = "0x5e852077b30099106Aa65B4d329FFF9b5C9a8e7C"
        with pytest.raises(ValueError, match="not a valid Ethereum address"):
            get_pay_as_you_go_price_config(
                100, "invalid-address", template_address=template_address
            )

    def test_pay_as_you_go_credits_config_defaults(self):
        """Test that get_pay_as_you_go_credits_config has correct defaults."""
        from payments_py.common.types import PlanRedemptionType

        credits_config = get_pay_as_you_go_credits_config()

        assert credits_config.is_redemption_amount_fixed is False
        assert credits_config.redemption_type == PlanRedemptionType.ONLY_SUBSCRIBER
        assert credits_config.onchain_mirror is False
        assert credits_config.duration_secs == 0
        assert credits_config.amount == "1"
        assert credits_config.min_amount == 1
        assert credits_config.max_amount == 1

    def test_pay_as_you_go_credits_config_values_not_functional(self):
        """Test that get_pay_as_you_go_credits_config returns defaults (values not used)."""
        from payments_py.common.types import PlanRedemptionType

        credits_config = get_pay_as_you_go_credits_config()

        # All values default to 1 - they're required by API/contracts but not functionally used
        # since Pay As You Go doesn't mint credits upfront
        assert credits_config.redemption_type == PlanRedemptionType.ONLY_SUBSCRIBER
        assert credits_config.amount == "1"
        assert credits_config.min_amount == 1
        assert credits_config.max_amount == 1


class TestPayAsYouGoRecipesOnTheWire:
    """The pay-as-you-go recipes in docs/api/03-payment-plans.md
    (nevermined-io/docs#413) — the crypto builder, the card recipe (now the
    ``get_fiat_pay_as_you_go_price_config`` shorthand, plus its manual
    ``get_fiat_price_config`` + template form), and the credits-plan trap — run
    against a mocked backend.

    The template address is what makes a plan pay-as-you-go: a fiat price
    without it registers a one-credit credits plan, and nothing errors. So
    these tests assert on the register request itself, not on the builders.
    """

    def _register(self, build_price) -> dict:
        """Build the price against a mocked backend, register it with the
        pay-as-you-go credits config as the docs do, and return the body."""
        payments = Payments.get_instance(_opts())
        backend = payments.plans.environment.backend
        with requests_mock.Mocker() as m:
            m.get(f"{backend}{API_URL_INFO}", json=_DEPLOYMENT)
            m.post(f"{backend}{API_URL_REGISTER_PLAN}", json={"planId": "pl-1"})
            payments.plans.register_credits_plan(
                plan_metadata=PlanMetadata(name="Pay per request"),
                price_config=build_price(payments),
                credits_config=payments.plans.get_pay_as_you_go_credits_config(),
            )
            return m.last_request.json()

    def test_card_recipe_registers_a_fiat_price_on_the_payg_template(self):
        def card_price(payments):
            price_config = payments.plans.get_fiat_price_config(
                amount=1_000_000, receiver=RECEIVER
            )
            price_config.template_address = (
                payments.contracts.get_pay_as_you_go_template_address()
            )
            return price_config

        body = self._register(card_price)

        assert body["priceConfig"]["isCrypto"] is False
        assert body["priceConfig"]["templateAddress"] == (
            _CONTRACTS["PayAsYouGoTemplate"]
        )
        assert body["currency"] == "USD"
        assert body["accessLimit"] == "credits"

    def test_crypto_recipe_registers_a_crypto_price_on_the_same_template(self):
        body = self._register(
            lambda payments: payments.plans.get_pay_as_you_go_price_config(
                amount=1_000_000, receiver=RECEIVER, token_address=TEST_ERC20_TOKEN
            )
        )

        assert body["priceConfig"]["isCrypto"] is True
        assert body["priceConfig"]["templateAddress"] == (
            _CONTRACTS["PayAsYouGoTemplate"]
        )
        assert body["priceConfig"]["tokenAddress"] == TEST_ERC20_TOKEN
        assert body["accessLimit"] == "credits"
        assert "currency" not in body

    def test_fiat_price_alone_is_not_on_the_payg_template(self):
        """The trap the docs warn about: no template, so a credits plan."""
        body = self._register(
            lambda payments: payments.plans.get_fiat_price_config(
                amount=1_000_000, receiver=RECEIVER
            )
        )

        assert body["priceConfig"]["isCrypto"] is False
        assert body["priceConfig"]["templateAddress"] == ZeroAddress

    def test_card_helper_reads_template_from_the_api(self):
        """get_fiat_pay_as_you_go_price_config is the one-call shorthand for the
        card recipe above: a real PlansAPI reads the PayAsYouGoTemplate from the
        API (the deployment's 0x1111…, not a hardcoded address) and carries the
        currency through."""
        payments = Payments.get_instance(_opts())
        backend = payments.plans.environment.backend
        with requests_mock.Mocker() as m:
            info = m.get(f"{backend}{API_URL_INFO}", json=_DEPLOYMENT)
            price_config = payments.plans.get_fiat_pay_as_you_go_price_config(
                amount=1_000_000, receiver=RECEIVER, currency="EUR"
            )

        assert price_config.template_address == _CONTRACTS["PayAsYouGoTemplate"]
        assert price_config.is_crypto is False
        assert price_config.currency == "EUR"
        assert info.call_count == 1

    def test_card_helper_registers_as_payg_over_the_wire(self):
        """The shorthand registers as a card PAYG plan over the wire: the
        register body carries the fiat price (isCrypto False) on the
        PayAsYouGoTemplate — the silent-misconfiguration trap the docs warn
        about — with the currency passed through."""
        body = self._register(
            lambda payments: payments.plans.get_fiat_pay_as_you_go_price_config(
                amount=1_000_000, receiver=RECEIVER, currency="EUR"
            )
        )

        assert body["priceConfig"]["isCrypto"] is False
        assert body["priceConfig"]["templateAddress"] == (
            _CONTRACTS["PayAsYouGoTemplate"]
        )
        assert body["currency"] == "EUR"
        assert body["accessLimit"] == "credits"


class TestFiatPayAsYouGoHelperFunction:
    """Unit tests for the CARD (fiat) Pay As You Go price builder (docs#413)."""

    def test_fiat_payg_is_not_crypto_and_sets_template(self):
        """Fiat PAYG uses the card rail (is_crypto False) with the PAYG template."""
        price_config = get_fiat_pay_as_you_go_price_config(
            2_000_000, TEST_RECEIVER, template_address=TEST_TEMPLATE
        )

        assert price_config.is_crypto is False
        assert price_config.template_address == TEST_TEMPLATE
        assert price_config.amounts == [2_000_000]
        assert price_config.receivers == [TEST_RECEIVER]
        # Fiat is off-chain: no token, zeroed contract addresses.
        assert price_config.token_address == ZeroAddress
        assert price_config.contract_address == ZeroAddress
        assert price_config.fee_controller == ZeroAddress
        assert price_config.external_price_address == ZeroAddress

    def test_fiat_payg_defaults_to_usd(self):
        """Currency defaults to USD, matching get_fiat_price_config."""
        price_config = get_fiat_pay_as_you_go_price_config(
            1_000_000, TEST_RECEIVER, template_address=TEST_TEMPLATE
        )

        assert price_config.currency == "USD"

    def test_fiat_payg_explicit_eur(self):
        """An explicit EUR currency is carried through."""
        price_config = get_fiat_pay_as_you_go_price_config(
            5_000_000, TEST_RECEIVER, currency="EUR", template_address=TEST_TEMPLATE
        )

        assert price_config.currency == "EUR"
        assert price_config.is_crypto is False
        assert price_config.template_address == TEST_TEMPLATE

    def test_fiat_payg_requires_template_address(self):
        """Missing template_address raises, same as the crypto PAYG builder."""
        with pytest.raises(ValueError, match="template_address is required"):
            get_fiat_pay_as_you_go_price_config(1_000_000, TEST_RECEIVER)

    def test_fiat_payg_invalid_receiver(self):
        """An invalid receiver address is rejected."""
        with pytest.raises(ValueError, match="not a valid Ethereum address"):
            get_fiat_pay_as_you_go_price_config(
                1_000_000, "invalid-address", template_address=TEST_TEMPLATE
            )

    def test_fiat_payg_sets_template_plain_fiat_config_does_not(self):
        """The fiat PAYG builder sets the PayAsYouGoTemplate address; a plain
        get_fiat_price_config leaves template_address at ZeroAddress."""
        base = get_fiat_price_config(1_000_000, TEST_RECEIVER)
        payg = get_fiat_pay_as_you_go_price_config(
            1_000_000, TEST_RECEIVER, template_address=TEST_TEMPLATE
        )

        assert base.template_address == ZeroAddress
        assert payg.template_address == TEST_TEMPLATE

    def test_plans_api_resolves_template_from_contracts(self):
        """PlansAPI.get_fiat_pay_as_you_go_price_config resolves the template
        from the contracts API, exactly like the crypto method."""
        api = MagicMock()
        api.contracts_api.contracts.pay_as_you_go_template = TEST_TEMPLATE

        price_config = PlansAPI.get_fiat_pay_as_you_go_price_config(
            api, 3_000_000, TEST_RECEIVER
        )

        assert price_config.template_address == TEST_TEMPLATE
        assert price_config.is_crypto is False
        assert price_config.currency == "USD"
        assert price_config.amounts == [3_000_000]

    def test_fiat_payg_builder_is_exported_at_package_root(self):
        """`from payments_py import get_fiat_pay_as_you_go_price_config` works:
        the name __all__ advertises is actually bound on the package."""
        assert "get_fiat_pay_as_you_go_price_config" in payments_py.__all__
        assert hasattr(payments_py, "get_fiat_pay_as_you_go_price_config")

    def test_crypto_payg_builder_output_unchanged(self):
        """The crypto PAYG builder still produces an on-chain (is_crypto True)
        config — the fiat addition must not alter it."""
        crypto = get_pay_as_you_go_price_config(
            100, TEST_RECEIVER, template_address=TEST_TEMPLATE
        )

        assert crypto.is_crypto is True
        assert crypto.template_address == TEST_TEMPLATE
        assert crypto.token_address == ZeroAddress


class TestPlanCreditsConfigCamelCaseAlias:
    """Verify the wire-format compatibility added in #1281: API JSON
    speaks camelCase (`onchainMirror`); the snake_case Python field
    `onchain_mirror` resolves both names via `populate_by_name=True` +
    `Field(alias="onchainMirror")`. Without this contract, plans
    returned from the API would fail to deserialize."""

    def test_model_validate_accepts_camel_case_onchain_mirror(self):
        """The API emits camelCase; PlanCreditsConfig must accept it."""
        from payments_py.common.types import PlanCreditsConfig, PlanRedemptionType

        config = PlanCreditsConfig.model_validate(
            {
                "is_redemption_amount_fixed": True,
                "redemption_type": PlanRedemptionType.ONLY_SUBSCRIBER,
                "onchainMirror": True,  # camelCase wire format
                "duration_secs": 0,
                "amount": "100",
                "min_amount": 1,
                "max_amount": 1,
            }
        )
        assert config.onchain_mirror is True

    def test_model_validate_accepts_snake_case_onchain_mirror(self):
        """populate_by_name=True keeps snake_case construction working."""
        from payments_py.common.types import PlanCreditsConfig, PlanRedemptionType

        config = PlanCreditsConfig.model_validate(
            {
                "is_redemption_amount_fixed": True,
                "redemption_type": PlanRedemptionType.ONLY_SUBSCRIBER,
                "onchain_mirror": True,  # snake_case
                "duration_secs": 0,
                "amount": "100",
                "min_amount": 1,
                "max_amount": 1,
            }
        )
        assert config.onchain_mirror is True

    def test_model_validate_defaults_to_false_when_field_omitted(self):
        """Legacy API responses that omit the field must parse cleanly."""
        from payments_py.common.types import PlanCreditsConfig, PlanRedemptionType

        config = PlanCreditsConfig.model_validate(
            {
                "is_redemption_amount_fixed": True,
                "redemption_type": PlanRedemptionType.ONLY_SUBSCRIBER,
                # onchainMirror intentionally omitted
                "duration_secs": 0,
                "amount": "100",
                "min_amount": 1,
                "max_amount": 1,
            }
        )
        assert config.onchain_mirror is False
