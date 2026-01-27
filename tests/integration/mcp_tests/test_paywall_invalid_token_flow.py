"""
Integration tests for MCP paywall with invalid token flows.

Tests complete authentication flow when tokens are invalid or insufficient.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from payments_py.mcp import build_mcp_integration


def mock_decode_access_token(token: str):
    """Mock x402 token decoder."""
    return {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "plan-basic",
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

    def __init__(self, is_valid: bool, invalid_reason: str = None):
        self.is_valid = is_valid
        self.invalid_reason = invalid_reason


class MockSettleResult:
    """Mock settle permissions result."""

    def __init__(
        self, success: bool, transaction: str = None, credits_redeemed: str = "0"
    ):
        self.success = success
        self.transaction = transaction
        self.credits_redeemed = credits_redeemed


class PaymentsMockWithFailures:
    """Mock Payments that simulates various authentication failure scenarios."""

    def __init__(
        self,
        failure_mode: str = "none",
    ):
        self.calls = []
        self.failure_mode = failure_mode
        self.facilitator = MagicMock()
        self.facilitator.verify_permissions = AsyncMock(
            side_effect=self._verify_permissions
        )
        self.facilitator.settle_permissions = AsyncMock(
            side_effect=self._settle_permissions
        )
        self.agents = MagicMock()
        # get_agent_plans is called synchronously in auth.py (not awaited)
        self.agents.get_agent_plans = MagicMock(side_effect=self._get_agent_plans_sync)

    async def _verify_permissions(self, **kwargs):
        self.calls.append(("verify_permissions", kwargs))
        if self.failure_mode in ("invalid-token", "not-subscriber"):
            return MockVerifyResult(is_valid=False, invalid_reason="Payment required")
        return MockVerifyResult(is_valid=True)

    async def _settle_permissions(self, **kwargs):
        self.calls.append(("settle", kwargs))
        if self.failure_mode == "insufficient-balance":
            raise Exception("Insufficient balance for redemption")
        return MockSettleResult(
            success=True,
            transaction="0xtest123",
            credits_redeemed=str(kwargs.get("max_amount", 0)),
        )

    async def _get_agent_plans(self, agent_id: str):
        self.calls.append(("get_agent_plans", agent_id))
        return {
            "plans": [
                {"planId": "plan-basic", "name": "Basic Plan", "price": 10},
                {"planId": "plan-pro", "name": "Pro Plan", "price": 50},
                {"planId": "plan-enterprise", "name": "Enterprise Plan", "price": 200},
            ]
        }

    def _get_agent_plans_sync(self, agent_id: str):
        """Sync version for non-awaited calls."""
        self.calls.append(("get_agent_plans", agent_id))
        # Format expected by auth.py: metadata.main.name for human-readable names
        return {
            "plans": [
                {"planId": "plan-basic", "metadata": {"main": {"name": "Basic Plan"}}},
                {"planId": "plan-pro", "metadata": {"main": {"name": "Pro Plan"}}},
                {
                    "planId": "plan-enterprise",
                    "metadata": {"main": {"name": "Enterprise Plan"}},
                },
            ]
        }


class TestMcpPaywallInvalidTokenFlow:
    """Tests for MCP paywall invalid token flow."""

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_rejects_with_payment_required_when_token_is_invalid(self):
        """Should reject with payment required when token is invalid."""
        mock_instance = PaymentsMockWithFailures("invalid-token")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {"content": [{"type": "text", "text": f"Weather in {args['city']}"}]}

        wrapped = mcp.with_paywall(
            handler,
            {"kind": "tool", "name": "weather", "credits": 5, "planId": "plan-basic"},
        )

        with pytest.raises(Exception) as exc_info:
            await wrapped(
                {"city": "Madrid"},
                {
                    "requestInfo": {
                        "headers": {"authorization": "Bearer invalid-token-xyz"}
                    }
                },
            )

        error = exc_info.value
        assert hasattr(error, "code") and error.code == -32003
        assert "Payment" in str(error)

        # Should have attempted to verify permissions
        assert any(c[0] == "verify_permissions" for c in mock_instance.calls)

        # Should have fetched available plans for error message
        assert any(c[0] == "get_agent_plans" for c in mock_instance.calls)

        # Should NOT have attempted to settle credits
        assert not any(c[0] == "settle" for c in mock_instance.calls)

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_includes_plan_information_in_error_when_token_is_invalid(self):
        """Should include plan information in error when token is invalid."""
        mock_instance = PaymentsMockWithFailures("invalid-token")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {"content": [{"type": "text", "text": "result"}]}

        wrapped = mcp.with_paywall(
            handler,
            {"kind": "tool", "name": "test", "credits": 1, "planId": "plan-basic"},
        )

        with pytest.raises(Exception) as exc_info:
            await wrapped(
                {"input": "test"},
                {"requestInfo": {"headers": {"authorization": "Bearer bad-token"}}},
            )

        error = exc_info.value
        # Error message should include available plans
        assert "Available plans" in str(error)
        # auth.py uses human-readable names from metadata.main.name, not plan IDs
        assert any(
            plan in str(error) for plan in ["Basic Plan", "Pro Plan", "Enterprise Plan"]
        )

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_rejects_when_user_is_not_a_subscriber(self):
        """Should reject when user is not a subscriber."""
        mock_instance = PaymentsMockWithFailures("not-subscriber")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {"content": [{"type": "text", "text": "result"}]}

        wrapped = mcp.with_paywall(
            handler,
            {"kind": "tool", "name": "test", "credits": 1, "planId": "plan-basic"},
        )

        with pytest.raises(Exception) as exc_info:
            await wrapped(
                {"input": "test"},
                {"requestInfo": {"headers": {"authorization": "Bearer valid-token"}}},
            )

        error = exc_info.value
        assert hasattr(error, "code") and error.code == -32003
        assert "Payment" in str(error)
        assert hasattr(error, "data") and error.data.get("reason") == "invalid"

        # Should have called verify_permissions (which returned isValid: False)
        assert any(c[0] == "verify_permissions" for c in mock_instance.calls)

        # Should NOT have attempted to settle
        assert not any(c[0] == "settle" for c in mock_instance.calls)

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_successfully_processes_with_valid_token_and_sufficient_balance(self):
        """Should successfully process with valid token and sufficient balance."""
        mock_instance = PaymentsMockWithFailures("none")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {
                "content": [{"type": "text", "text": f"Processing {args['action']}"}]
            }

        wrapped = mcp.with_paywall(
            handler,
            {"kind": "tool", "name": "process", "credits": 10, "planId": "plan-basic"},
        )

        result = await wrapped(
            {"action": "analyze"},
            {"requestInfo": {"headers": {"authorization": "Bearer valid-token-123"}}},
        )

        assert result is not None
        assert result["content"][0]["text"] == "Processing analyze"

        # Should have completed full flow
        assert any(c[0] == "verify_permissions" for c in mock_instance.calls)
        assert any(c[0] == "settle" for c in mock_instance.calls)

        # Should NOT have fetched plans (no error)
        assert not any(c[0] == "get_agent_plans" for c in mock_instance.calls)

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_handles_different_tools_with_different_credit_requirements(self):
        """Should handle different tools with different credit requirements."""
        mock_instance = PaymentsMockWithFailures("none")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "multi-tool-server"}
        )

        async def simple_handler(args):
            return {"content": [{"type": "text", "text": "simple"}]}

        async def complex_handler(args):
            return {"content": [{"type": "text", "text": "complex"}]}

        async def premium_handler(args):
            return {"content": [{"type": "text", "text": "premium"}]}

        simple_tool = mcp.with_paywall(
            simple_handler,
            {"kind": "tool", "name": "simple", "credits": 1, "planId": "plan-basic"},
        )
        complex_tool = mcp.with_paywall(
            complex_handler,
            {"kind": "tool", "name": "complex", "credits": 5, "planId": "plan-basic"},
        )
        premium_tool = mcp.with_paywall(
            premium_handler,
            {"kind": "tool", "name": "premium", "credits": 20, "planId": "plan-basic"},
        )

        extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}

        # Execute all tools
        await simple_tool({}, extra)
        await complex_tool({}, extra)
        await premium_tool({}, extra)

        # Verify different credit amounts were settled
        settle_calls = [c for c in mock_instance.calls if c[0] == "settle"]
        assert len(settle_calls) == 3
        assert int(settle_calls[0][1]["max_amount"]) == 1  # simple tool
        assert int(settle_calls[1][1]["max_amount"]) == 5  # complex tool
        assert int(settle_calls[2][1]["max_amount"]) == 20  # premium tool

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_propagates_redemption_errors_when_configured(self):
        """Should propagate redemption errors when configured."""
        mock_instance = PaymentsMockWithFailures("insufficient-balance")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {"content": [{"type": "text", "text": "result"}]}

        wrapped = mcp.with_paywall(
            handler,
            {
                "kind": "tool",
                "name": "test",
                "credits": 100,
                "planId": "plan-basic",
                "onRedeemError": "propagate",
            },
        )

        # Note: verify_permissions succeeds but settle_permissions fails
        with pytest.raises(Exception) as exc_info:
            await wrapped(
                {"input": "test"},
                {"requestInfo": {"headers": {"authorization": "Bearer token"}}},
            )

        error = exc_info.value
        # Should be a misconfiguration error for redemption failure
        assert hasattr(error, "code") and error.code == -32002
        assert "Failed to settle credits" in str(error)

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_ignores_redemption_errors_by_default(self):
        """Should ignore redemption errors by default."""
        mock_instance = PaymentsMockWithFailures("insufficient-balance")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {"content": [{"type": "text", "text": "result"}]}

        # Default behavior: ignore redemption errors
        wrapped = mcp.with_paywall(
            handler,
            {
                "kind": "tool",
                "name": "test",
                "credits": 100,
                "planId": "plan-basic",
                # onRedeemError defaults to 'ignore'
            },
        )

        # Should not throw, even though redemption fails
        result = await wrapped(
            {"input": "test"},
            {"requestInfo": {"headers": {"authorization": "Bearer token"}}},
        )

        assert result is not None
        assert result["content"][0]["text"] == "result"

        # When redemption fails silently, metadata is NOT added (Python behavior)
        # The handler completes successfully without throwing, but no metadata is added
        # because the redemption failed (success=False)
        # This differs from TypeScript where metadata is always added

    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_handles_multiple_authentication_failures_in_sequence(self):
        """Should handle multiple authentication failures in sequence."""
        mock_instance = PaymentsMockWithFailures("invalid-token")
        mcp = build_mcp_integration(mock_instance)
        mcp.configure(
            {"agentId": "integration_agent_id_hex", "serverName": "test-server"}
        )

        async def handler(args):
            return {"content": [{"type": "text", "text": "ok"}]}

        wrapped = mcp.with_paywall(
            handler,
            {"kind": "tool", "name": "test", "credits": 1, "planId": "plan-basic"},
        )

        # Multiple failed attempts
        attempts = 5
        for i in range(attempts):
            with pytest.raises(Exception) as exc_info:
                await wrapped(
                    {},
                    {
                        "requestInfo": {
                            "headers": {"authorization": f"Bearer bad-token-{i}"}
                        }
                    },
                )
            assert exc_info.value.code == -32003

        # Should have attempted to verify permissions for each attempt
        verify_calls = [c for c in mock_instance.calls if c[0] == "verify_permissions"]
        assert len(verify_calls) == attempts

        # Should have fetched plans for each failure
        plan_calls = [c for c in mock_instance.calls if c[0] == "get_agent_plans"]
        assert len(plan_calls) == attempts
