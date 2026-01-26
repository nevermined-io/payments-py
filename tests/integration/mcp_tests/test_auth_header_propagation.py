"""
Integration tests for MCP handler authentication header propagation.

Tests that HTTP headers are correctly propagated from requests to the paywall.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from payments_py.mcp.core.auth import PaywallAuthenticator


def mock_decode_access_token(token: str):
    """Mock x402 token decoder."""
    return {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "plan-1",
            "extra": {"version": "1"},
        },
        "payload": {
            "signature": "0x123",
            "authorization": {
                "from": "0xabc",
                "sessionKeysProvider": "zerodev",
                "sessionKeys": [],
            },
        },
        "extensions": {},
    }


class MockVerifyResult:
    """Mock verify permissions result."""

    def __init__(self, is_valid: bool):
        self.is_valid = is_valid


class PaymentsMockWithTracking:
    """Mock Payments with call tracking for integration tests."""

    def __init__(self):
        self.calls = []
        self.facilitator = MagicMock()
        self.facilitator.verify_permissions = AsyncMock(
            side_effect=self._verify_permissions
        )
        self.agents = MagicMock()
        # get_agent_plans is called synchronously in auth.py (not awaited)
        self.agents.get_agent_plans = MagicMock(side_effect=self._get_agent_plans_sync)

    async def _verify_permissions(self, **kwargs):
        self.calls.append(("verify_permissions", kwargs))
        return MockVerifyResult(is_valid=True)

    def _get_agent_plans_sync(self, agent_id: str):
        """Sync version for non-awaited calls."""
        self.calls.append(("get_agent_plans", agent_id))
        return {
            "plans": [
                {"planId": "int-plan-1", "name": "Integration Plan"},
                {"planId": "int-plan-2", "name": "Test Plan"},
            ]
        }


class TestMcpHandlerAuthHeaderPropagation:
    """Tests for MCP handler auth header propagation."""

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_propagates_authorization_header_from_extra(self):
        """Should propagate Authorization header from extra to paywall."""
        mock_instance = PaymentsMockWithTracking()
        authenticator = PaywallAuthenticator(mock_instance)

        extra = {
            "requestInfo": {
                "headers": {
                    "authorization": "Bearer integration-token-456",
                    "host": "localhost:3000",
                    "user-agent": "MCP-Client/1.0",
                }
            }
        }

        result = await authenticator.authenticate(
            extra=extra,
            options={"planId": "plan-1"},
            agent_id="integration_agent_id_hex",
            server_name="test-server",
            name="weather",
            kind="tool",
            args_or_vars={"city": "Barcelona"},
        )

        assert result is not None
        assert result["token"] == "integration-token-456"
        assert result["agent_id"] == "integration_agent_id_hex"

        # Verify the token was used in verify_permissions
        verify_calls = [c for c in mock_instance.calls if c[0] == "verify_permissions"]
        assert len(verify_calls) == 1
        assert verify_calls[0][1]["x402_access_token"] == "integration-token-456"

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_works_with_capital_authorization_header(self):
        """Should work with capital Authorization header."""
        mock_instance = PaymentsMockWithTracking()
        authenticator = PaywallAuthenticator(mock_instance)

        extra = {
            "requestInfo": {
                "headers": {
                    "Authorization": "Bearer UPPERCASE-TOKEN",
                    "host": "localhost:3000",
                }
            }
        }

        result = await authenticator.authenticate(
            extra=extra,
            options={"planId": "plan-1"},
            agent_id="integration_agent_id_hex",
            server_name="test-server",
            name="tool1",
            kind="tool",
            args_or_vars={},
        )

        assert result["token"] == "UPPERCASE-TOKEN"

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_handles_missing_authorization_header_with_proper_error(self):
        """Should handle missing Authorization header with proper error."""
        mock_instance = PaymentsMockWithTracking()
        authenticator = PaywallAuthenticator(mock_instance)

        extra = {
            "requestInfo": {
                "headers": {
                    "host": "localhost:3000",
                    "user-agent": "MCP-Client/1.0",
                    # No authorization header
                }
            }
        }

        with pytest.raises(Exception) as exc_info:
            await authenticator.authenticate(
                extra=extra,
                options={},
                agent_id="integration_agent_id_hex",
                server_name="test-server",
                name="tool1",
                kind="tool",
                args_or_vars={},
            )

        error = exc_info.value
        assert hasattr(error, "code") and error.code == -32003
        assert "Authorization required" in str(error)
        assert hasattr(error, "data") and error.data.get("reason") == "missing"

        # Should not have called verify_permissions
        verify_calls = [c for c in mock_instance.calls if c[0] == "verify_permissions"]
        assert len(verify_calls) == 0

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_propagates_headers_through_multiple_authentication_calls(self):
        """Should propagate headers through multiple authentication calls."""
        mock_instance = PaymentsMockWithTracking()
        authenticator = PaywallAuthenticator(mock_instance)

        extra = {
            "requestInfo": {
                "headers": {
                    "authorization": "Bearer session-token-789",
                    "host": "api.example.com",
                    "mcp-session-id": "session-abc-123",
                }
            }
        }

        # First call - initialize (meta)
        result1 = await authenticator.authenticate_meta(
            extra=extra,
            agent_id="integration_agent_id_hex",
            server_name="multi-server",
            method="initialize",
        )
        assert result1["token"] == "session-token-789"

        # Second call - tools/list (meta)
        result2 = await authenticator.authenticate_meta(
            extra=extra,
            agent_id="integration_agent_id_hex",
            server_name="multi-server",
            method="tools/list",
        )
        assert result2["token"] == "session-token-789"

        # Third call - actual tool execution
        result3 = await authenticator.authenticate(
            extra=extra,
            options={"planId": "plan-1"},
            agent_id="integration_agent_id_hex",
            server_name="multi-server",
            name="get_weather",
            kind="tool",
            args_or_vars={"city": "Valencia"},
        )
        assert result3["token"] == "session-token-789"

        # All three calls should have used the same token
        verify_calls = [c for c in mock_instance.calls if c[0] == "verify_permissions"]
        assert len(verify_calls) == 3
        assert all(
            c[1]["x402_access_token"] == "session-token-789" for c in verify_calls
        )

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_extracts_token_from_different_header_containers(self):
        """Should extract token from various header container structures."""
        mock_instance = PaymentsMockWithTracking()
        authenticator = PaywallAuthenticator(mock_instance)

        # Test different header container structures supported by extract_auth_header
        containers = [
            (
                "requestInfo",
                {"requestInfo": {"headers": {"authorization": "Bearer token-a"}}},
            ),
            ("request", {"request": {"headers": {"authorization": "Bearer token-b"}}}),
            ("headers", {"headers": {"authorization": "Bearer token-c"}}),
        ]

        for i, (name, extra) in enumerate(containers):
            result = await authenticator.authenticate(
                extra=extra,
                options={"planId": "plan-1"},
                agent_id="integration_agent_id_hex",
                server_name="test-server",
                name=f"tool{i}",
                kind="tool",
                args_or_vars={},
            )
            expected_token = f"token-{chr(ord('a') + i)}"
            assert result["token"] == expected_token, f"Failed for container '{name}'"
