"""Unit tests for x402 scheme types and helpers."""

from payments_py.x402.schemes import (
    X402SchemeType,
    X402_SCHEME_NETWORKS,
    is_valid_scheme,
)


class TestIsValidScheme:
    """Tests for is_valid_scheme type guard."""

    def test_erc4337_is_valid(self):
        assert is_valid_scheme("nvm:erc4337") is True

    def test_card_delegation_is_valid(self):
        assert is_valid_scheme("nvm:card-delegation") is True

    def test_unknown_scheme_is_invalid(self):
        assert is_valid_scheme("nvm:unknown") is False

    def test_empty_string_is_invalid(self):
        assert is_valid_scheme("") is False

    def test_none_is_invalid(self):
        assert is_valid_scheme(None) is False

    def test_integer_is_invalid(self):
        assert is_valid_scheme(42) is False


class TestSchemeNetworks:
    """Tests for X402_SCHEME_NETWORKS mapping."""

    def test_erc4337_network(self):
        assert X402_SCHEME_NETWORKS["nvm:erc4337"] == "eip155:84532"

    def test_card_delegation_network(self):
        assert X402_SCHEME_NETWORKS["nvm:card-delegation"] == "stripe"

    def test_has_both_schemes(self):
        assert len(X402_SCHEME_NETWORKS) == 2
