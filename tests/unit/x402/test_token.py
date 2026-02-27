"""Unit tests for X402 token generation with token_options."""

from unittest.mock import patch, MagicMock

import pytest

from payments_py.x402.token import X402TokenAPI, decode_access_token
from payments_py.x402.types import CardDelegationConfig, X402TokenOptions


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
        # Verify the request body
        call_args = mock_post.call_args
        import json

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
            delegation_config=CardDelegationConfig(
                provider_payment_method_id="pm_123",
                spending_limit_cents=10000,
                duration_secs=604800,
                currency="usd",
            ),
        )
        result = api.get_x402_access_token("plan-fiat", token_options=token_options)

        assert result["accessToken"] == "card-token"
        call_args = mock_post.call_args
        import json

        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["accepted"]["scheme"] == "nvm:card-delegation"
        assert body["accepted"]["network"] == "stripe"
        assert body["delegationConfig"]["providerPaymentMethodId"] == "pm_123"
        assert body["delegationConfig"]["spendingLimitCents"] == 10000
        assert body["delegationConfig"]["durationSecs"] == 604800
        # sessionKeyConfig should NOT be present for card-delegation
        assert "sessionKeyConfig" not in body

    @patch("payments_py.x402.token.requests.post")
    def test_erc4337_with_session_key_config(self, mock_post, mock_options):
        """Test that erc4337 scheme includes sessionKeyConfig."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "erc-token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        result = api.get_x402_access_token(
            "plan-crypto",
            redemption_limit=10,
            order_limit="1000",
            expiration="2026-01-01T00:00:00Z",
        )

        call_args = mock_post.call_args
        import json

        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert body["accepted"]["scheme"] == "nvm:erc4337"
        assert body["sessionKeyConfig"]["redemptionLimit"] == 10
        assert body["sessionKeyConfig"]["orderLimit"] == "1000"
        assert body["sessionKeyConfig"]["expiration"] == "2026-01-01T00:00:00Z"
        assert "delegationConfig" not in body

    @patch("payments_py.x402.token.requests.post")
    def test_card_delegation_no_session_key(self, mock_post, mock_options):
        """Test that card-delegation does not send sessionKeyConfig even with limits."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "token"}
        mock_post.return_value = mock_response

        api = X402TokenAPI(mock_options)
        token_options = X402TokenOptions(scheme="nvm:card-delegation")
        result = api.get_x402_access_token(
            "plan-fiat",
            redemption_limit=5,  # Should be ignored for card-delegation
            token_options=token_options,
        )

        call_args = mock_post.call_args
        import json

        body = json.loads(call_args.kwargs.get("data", "{}"))
        assert "sessionKeyConfig" not in body


class TestDecodeAccessToken:
    """Tests for decode_access_token."""

    def test_decode_valid_token(self):
        import base64
        import json

        data = {"accepted": {"scheme": "nvm:erc4337", "planId": "plan-1"}}
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        result = decode_access_token(encoded)
        assert result is not None
        assert result["accepted"]["scheme"] == "nvm:erc4337"

    def test_decode_invalid_token(self):
        result = decode_access_token("not-valid-base64-json")
        assert result is None
