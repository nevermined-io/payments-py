"""Unit tests for X402 token generation with token_options."""

import base64
import json
import warnings
from unittest.mock import patch, MagicMock

import pytest

from payments_py.x402.token import X402TokenAPI, decode_access_token
from payments_py.x402.types import (
    DelegationConfig,
    X402TokenOptions,
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


class TestTokenWithOptions:
    """Tests for token generation with X402TokenOptions."""

    @patch("payments_py.x402.token.requests.post")
    def test_default_scheme_is_erc4337(self, mock_post, mock_options):
        """Test that default scheme sends nvm:erc4337."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "test-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        result = api.get_x402_access_token("plan-123")

        assert result["accessToken"] == "test-token"
        call_args = mock_post.call_args
        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["accepted"]["scheme"] == "nvm:erc4337"
        assert body["accepted"]["network"] == "eip155:84532"

    @patch("payments_py.x402.token.requests.post")
    def test_card_delegation_scheme(self, mock_post, mock_options):
        """Test that card-delegation scheme sends correct body."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "card-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            scheme="nvm:card-delegation",
            delegation_config=DelegationConfig(
                provider_payment_method_id="pm_123",
                spending_limit_cents=10000,
                duration_secs=604800,
                currency="usd",
            ),
        )
        result = api.get_x402_access_token("plan-fiat", token_options=token_options)

        assert result["accessToken"] == "card-token"
        call_args = mock_post.call_args
        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["accepted"]["scheme"] == "nvm:card-delegation"
        assert body["accepted"]["network"] == "stripe"
        assert body["delegationConfig"]["providerPaymentMethodId"] == "pm_123"
        assert body["delegationConfig"]["spendingLimitCents"] == 10000
        assert body["delegationConfig"]["durationSecs"] == 604800
        # sessionKeyConfig should NOT be present for card-delegation
        assert "sessionKeyConfig" not in body

    @patch("payments_py.x402.token.requests.post")
    def test_erc4337_with_delegation_config(self, mock_post, mock_options):
        """Test that erc4337 scheme includes delegationConfig when provided."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "erc-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            delegation_config=DelegationConfig(
                delegation_id="deleg-123",
            ),
        )
        result = api.get_x402_access_token(
            "plan-crypto",
            token_options=token_options,
        )

        call_args = mock_post.call_args
        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["accepted"]["scheme"] == "nvm:erc4337"
        assert body["delegationConfig"]["delegationId"] == "deleg-123"
        assert "sessionKeyConfig" not in body

    @patch("payments_py.x402.token.requests.post")
    def test_erc4337_without_delegation_config(self, mock_post, mock_options):
        """Test that erc4337 without delegation config sends no delegationConfig."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        result = api.get_x402_access_token("plan-crypto")

        call_args = mock_post.call_args
        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["accepted"]["scheme"] == "nvm:erc4337"
        assert "delegationConfig" not in body
        assert "sessionKeyConfig" not in body


class TestInlineCreateDeprecationWarning:
    """The token request must nudge callers off the deprecated inline
    create-on-the-fly path (a delegation_config with no delegation_id) and
    toward the create-first flow (#1674)."""

    @patch("payments_py.x402.token.requests.post")
    def test_inline_create_via_payment_method_warns(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "card-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            scheme="nvm:card-delegation",
            delegation_config=DelegationConfig(
                provider_payment_method_id="pm_123",
                spending_limit_cents=10000,
                duration_secs=604800,
                currency="usd",
            ),
        )

        with pytest.warns(DeprecationWarning, match="create_delegation"):
            api.get_x402_access_token("plan-fiat", token_options=token_options)

        # The request still goes through — the path is deprecated, not removed.
        call_args = mock_post.call_args
        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["delegationConfig"]["providerPaymentMethodId"] == "pm_123"
        # The now-required currency survives serialization onto the wire.
        assert body["delegationConfig"]["currency"] == "usd"

    @patch("payments_py.x402.token.requests.post")
    def test_inline_create_via_card_id_warns(self, mock_post, mock_options):
        """Referencing an enrolled card by its PaymentMethod entity UUID (card_id)
        with no delegation_id still asks the backend to create a delegation on
        the fly — the deprecated path."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "card-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            scheme="nvm:card-delegation",
            delegation_config=DelegationConfig(card_id="card-uuid-1"),
        )

        with pytest.warns(DeprecationWarning, match="create_delegation"):
            api.get_x402_access_token("plan-fiat", token_options=token_options)

    @patch("payments_py.x402.token.requests.post")
    def test_inline_create_via_spending_limits_warns(self, mock_post, mock_options):
        """erc4337 auto-create (spending limits only, no payment method and no
        delegation_id) is also the deprecated inline path."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "erc-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            delegation_config=DelegationConfig(
                spending_limit_cents=10000,
                duration_secs=604800,
            ),
        )

        with pytest.warns(DeprecationWarning, match="create_delegation"):
            api.get_x402_access_token("plan-crypto", token_options=token_options)

    @patch("payments_py.x402.token.requests.post")
    def test_reuse_by_delegation_id_does_not_warn(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "erc-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            delegation_config=DelegationConfig(delegation_id="deleg-123"),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error")  # any warning becomes a test failure
            api.get_x402_access_token("plan-crypto", token_options=token_options)

    @patch("payments_py.x402.token.requests.post")
    def test_delegation_id_with_leftover_inline_fields_does_not_warn(
        self, mock_post, mock_options
    ):
        """Migration footgun guard: a caller who switched to create-first but
        left stale spending limits in their config must stay SILENT — the
        delegation_id takes precedence (reuse), so the inline fields are inert.
        Pins the predicate's early-return against a future refactor."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "erc-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            delegation_config=DelegationConfig(
                delegation_id="deleg-123",
                spending_limit_cents=10000,
                duration_secs=604800,
            ),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            api.get_x402_access_token("plan-crypto", token_options=token_options)

    @patch("payments_py.x402.token.requests.post")
    def test_delegation_id_with_api_key_id_does_not_warn(self, mock_post, mock_options):
        """api_key_id-scoped reuse is a documented pattern: {delegation_id,
        api_key_id} is still a reuse, not an inline create — stays silent."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "erc-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(
            delegation_config=DelegationConfig(
                delegation_id="deleg-123",
                api_key_id="key-1",
            ),
        )

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            api.get_x402_access_token("plan-crypto", token_options=token_options)

    @patch("payments_py.x402.token.requests.post")
    def test_no_delegation_config_does_not_warn(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)

        with warnings.catch_warnings():
            warnings.simplefilter("error")
            api.get_x402_access_token("plan-crypto")


class TestDecodeAccessToken:
    """Tests for decode_access_token."""

    def test_decode_valid_token(self):
        data = {"accepted": {"scheme": "nvm:erc4337", "planId": "plan-1"}}
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        result = decode_access_token(encoded)
        assert result is not None
        assert result["accepted"]["scheme"] == "nvm:erc4337"

    def test_decode_invalid_token(self):
        result = decode_access_token("not-valid-base64-json")
        assert result is None
