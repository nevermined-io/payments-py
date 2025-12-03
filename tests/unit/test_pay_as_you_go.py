"""
Unit tests for plan helper functions.
"""

import pytest
from payments_py.environments import ZeroAddress, PayAsYouGoTemplateAddress
from payments_py.plans import (
    get_pay_as_you_go_price_config,
    get_pay_as_you_go_credits_config,
)

# Test ERC20 token address (USDC on Base Sepolia)
TEST_ERC20_TOKEN = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


class TestPayAsYouGoHelperFunctions:
    """Unit tests for Pay As You Go helper functions."""

    def test_pay_as_you_go_price_config_has_correct_template(self):
        """Test that get_pay_as_you_go_price_config sets the correct template address."""
        receiver = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        price_config = get_pay_as_you_go_price_config(100, receiver)

        assert price_config.template_address == PayAsYouGoTemplateAddress
        assert price_config.is_crypto is True
        assert price_config.amounts == [100]
        assert price_config.receivers == [receiver]
        assert price_config.token_address == ZeroAddress

    def test_pay_as_you_go_price_config_with_erc20(self):
        """Test that get_pay_as_you_go_price_config works with ERC20 tokens."""
        receiver = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"
        token = TEST_ERC20_TOKEN
        price_config = get_pay_as_you_go_price_config(200, receiver, token)

        assert price_config.template_address == PayAsYouGoTemplateAddress
        assert price_config.token_address == token
        assert price_config.amounts == [200]

    def test_pay_as_you_go_price_config_invalid_receiver(self):
        """Test that get_pay_as_you_go_price_config raises on invalid receiver."""
        with pytest.raises(ValueError, match="not a valid Ethereum address"):
            get_pay_as_you_go_price_config(100, "invalid-address")

    def test_pay_as_you_go_credits_config_defaults(self):
        """Test that get_pay_as_you_go_credits_config has correct defaults."""
        from payments_py.common.types import PlanRedemptionType

        credits_config = get_pay_as_you_go_credits_config()

        assert credits_config.is_redemption_amount_fixed is False
        assert credits_config.redemption_type == PlanRedemptionType.ONLY_SUBSCRIBER
        assert credits_config.proof_required is False
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
