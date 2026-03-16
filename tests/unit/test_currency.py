"""Unit tests for EUR/EURC currency support."""

from payments_py.common.types import (
    Currency,
    EURC_TOKEN_ADDRESS,
    EURC_TOKEN_ADDRESS_TESTNET,
)
from payments_py.environments import ZeroAddress
from payments_py.plans import (
    get_fiat_price_config,
    get_eurc_price_config,
    get_erc20_price_config,
)

RECEIVER = "0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d"


class TestGetFiatPriceConfig:
    def test_defaults_to_usd(self):
        config = get_fiat_price_config(1000, RECEIVER)
        assert config.is_crypto is False
        assert config.currency == Currency.USD
        assert config.amounts == [1000]
        assert config.receivers == [RECEIVER]
        assert config.token_address == ZeroAddress

    def test_accepts_eur_currency(self):
        config = get_fiat_price_config(2900, RECEIVER, Currency.EUR)
        assert config.is_crypto is False
        assert config.currency == "EUR"
        assert config.amounts == [2900]

    def test_accepts_string_currency(self):
        config = get_fiat_price_config(500, RECEIVER, "GBP")
        assert config.currency == "GBP"


class TestGetEurcPriceConfig:
    def test_returns_correct_config_with_default_address(self):
        config = get_eurc_price_config(2900, RECEIVER)
        assert config.is_crypto is True
        assert config.currency == Currency.EURC
        assert config.token_address == EURC_TOKEN_ADDRESS
        assert config.amounts == [2900]
        assert config.receivers == [RECEIVER]

    def test_accepts_custom_eurc_address(self):
        config = get_eurc_price_config(100, RECEIVER, EURC_TOKEN_ADDRESS_TESTNET)
        assert config.token_address == EURC_TOKEN_ADDRESS_TESTNET
        assert config.currency == Currency.EURC


class TestBackwardCompatibility:
    def test_erc20_price_config_has_no_currency(self):
        usdc_address = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"
        config = get_erc20_price_config(20, usdc_address, RECEIVER)
        assert config.is_crypto is True
        assert config.currency is None
        assert config.token_address == usdc_address


class TestCurrencyEnum:
    def test_values(self):
        assert Currency.USD == "USD"
        assert Currency.EUR == "EUR"
        assert Currency.USDC == "USDC"
        assert Currency.EURC == "EURC"


class TestEurcTokenAddresses:
    def test_mainnet_address(self):
        assert EURC_TOKEN_ADDRESS == "0x60a3E35Cc302bFA44Cb288Bc5a4F316Fdb1adb42"

    def test_testnet_address(self):
        assert (
            EURC_TOKEN_ADDRESS_TESTNET == "0x808456652fdb597867f38412077A9182bf77359F"
        )
