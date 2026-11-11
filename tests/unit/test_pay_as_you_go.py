"""
Unit tests for plan helper functions.
"""

import pytest
import requests_mock

from payments_py.api.nvm_api import API_URL_INFO, API_URL_REGISTER_PLAN
from payments_py.common.types import PlanMetadata
from payments_py.environments import ZeroAddress
from payments_py.payments import Payments
from payments_py.plans import (
    get_pay_as_you_go_price_config,
    get_pay_as_you_go_credits_config,
)
from tests.unit.test_contracts_accessor import _CONTRACTS, _DEPLOYMENT, _opts

# Test ERC20 token address (USDC on Base Sepolia)
TEST_ERC20_TOKEN = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
RECEIVER = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"


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
    """The two pay-as-you-go recipes in docs/api/03-payment-plans.md
    (nevermined-io/docs#413), run as written against a mocked backend.

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
