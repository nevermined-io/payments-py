"""
Unit tests for Strands x402 payment decorator.
"""

from unittest.mock import MagicMock

import pytest

from payments_py.x402.strands import (
    requires_payment,
    extract_payment_required,
    PaymentContext,
)
from payments_py.x402.strands.decorator import (
    _error_result,
    _is_error_result,
    _build_payment_required_for_plans,
    _payment_required_result,
    _resolve_credits,
)
from payments_py.x402.types import VerifyResponse, SettleResponse


@pytest.fixture
def mock_payments():
    """Create a mock Payments instance with facilitator."""
    mock = MagicMock()

    verify_response = VerifyResponse(
        is_valid=True,
        invalid_reason=None,
        payer="0x1234567890abcdef",
        agent_request_id="test-request-id-123",
    )
    mock.facilitator.verify_permissions.return_value = verify_response

    settle_response = SettleResponse(
        success=True,
        error_reason=None,
        payer="0x1234567890abcdef",
        transaction="0xabc123",
        network="eip155:84532",
        credits_redeemed="1",
        remaining_balance="99",
    )
    mock.facilitator.settle_permissions.return_value = settle_response

    return mock


@pytest.fixture
def mock_tool_context():
    """Create a mock tool_context with invocation_state."""
    ctx = MagicMock()
    ctx.invocation_state = {"payment_token": "test-x402-token"}
    return ctx


class TestErrorHelpers:
    """Tests for error helper functions."""

    def test_error_result_format(self):
        """Test _error_result returns Strands-compatible error."""
        result = _error_result("Something went wrong")
        assert result["status"] == "error"
        assert len(result["content"]) == 1
        assert result["content"][0]["text"] == "Something went wrong"

    def test_payment_required_result_includes_x402_object(self):
        """Test _payment_required_result includes PaymentRequired as JSON block."""
        from payments_py.x402.types import (
            X402PaymentRequired,
            X402Resource,
            X402Scheme,
        )

        pr = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="my_tool"),
            accepts=[
                X402Scheme(
                    scheme="nvm:erc4337",
                    network="eip155:84532",
                    plan_id="plan-123",
                )
            ],
            extensions={},
        )
        result = _payment_required_result("Payment required", pr)
        assert result["status"] == "error"
        assert len(result["content"]) == 2
        assert result["content"][0]["text"] == "Payment required"
        # Second block is the structured PaymentRequired JSON
        json_block = result["content"][1]["json"]
        assert json_block["x402Version"] == 2
        assert json_block["accepts"][0]["planId"] == "plan-123"
        assert json_block["accepts"][0]["scheme"] == "nvm:erc4337"

    def test_is_error_result_true(self):
        """Test _is_error_result identifies errors."""
        assert _is_error_result({"status": "error", "content": []}) is True

    def test_is_error_result_false_for_success(self):
        """Test _is_error_result returns False for success."""
        assert _is_error_result({"status": "success", "content": []}) is False

    def test_is_error_result_false_for_non_dict(self):
        """Test _is_error_result handles non-dict values."""
        assert _is_error_result("string result") is False
        assert _is_error_result(42) is False
        assert _is_error_result(None) is False


class TestBuildPaymentRequiredMulti:
    """Tests for _build_payment_required_for_plans."""

    def test_single_plan_id(self):
        """Test building payment required with single plan."""
        pr = _build_payment_required_for_plans(
            plan_ids=["plan-1"],
            endpoint="test_tool",
        )
        assert pr.x402_version == 2
        assert len(pr.accepts) == 1
        assert pr.accepts[0].plan_id == "plan-1"
        assert pr.accepts[0].scheme == "nvm:erc4337"
        assert pr.accepts[0].network == "eip155:84532"

    def test_multiple_plan_ids(self):
        """Test building payment required with multiple plans."""
        pr = _build_payment_required_for_plans(
            plan_ids=["plan-basic", "plan-premium", "plan-enterprise"],
            endpoint="test_tool",
        )
        assert len(pr.accepts) == 3
        assert pr.accepts[0].plan_id == "plan-basic"
        assert pr.accepts[1].plan_id == "plan-premium"
        assert pr.accepts[2].plan_id == "plan-enterprise"

    def test_with_agent_id(self):
        """Test building payment required with agent_id."""
        pr = _build_payment_required_for_plans(
            plan_ids=["plan-1"],
            endpoint="test_tool",
            agent_id="agent-123",
        )
        assert pr.accepts[0].extra is not None
        assert pr.accepts[0].extra.agent_id == "agent-123"

    def test_custom_network(self):
        """Test building payment required with custom network."""
        pr = _build_payment_required_for_plans(
            plan_ids=["plan-1"],
            endpoint="test_tool",
            network="eip155:1",
        )
        assert pr.accepts[0].network == "eip155:1"


class TestResolveCredits:
    """Tests for _resolve_credits."""

    def test_static_credits(self):
        """Test resolving static int credits."""
        assert _resolve_credits(5, {}) == 5

    def test_callable_credits(self):
        """Test resolving callable credits."""

        def calc(kwargs):
            return kwargs.get("complexity", 1) * 2

        assert _resolve_credits(calc, {"complexity": 3}) == 6

    def test_callable_credits_default(self):
        """Test callable credits with default."""

        def calc(kwargs):
            return kwargs.get("complexity", 1) * 2

        assert _resolve_credits(calc, {}) == 2


class TestRequiresPaymentValidation:
    """Tests for requires_payment parameter validation."""

    def test_no_plan_id_raises(self, mock_payments):
        """Test that missing plan_id/plan_ids raises ValueError."""
        with pytest.raises(ValueError, match="Either plan_id or plan_ids"):

            @requires_payment(payments=mock_payments)
            def my_tool():
                pass

    def test_plan_id_convenience_alias(self, mock_payments):
        """Test that plan_id convenience alias works."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_tool(tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        # Should not raise
        assert callable(my_tool)


class TestRequiresPaymentSync:
    """Tests for sync tool decoration."""

    def test_missing_token_returns_error_with_payment_required(self, mock_payments):
        """Test that missing payment token returns error with x402 PaymentRequired."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        # No payment_token in kwargs or tool_context
        result = my_tool("test")
        assert result["status"] == "error"
        assert "missing payment_token" in result["content"][0]["text"]
        # x402 spec: error MUST include the PaymentRequired object
        json_block = result["content"][1]["json"]
        assert json_block["x402Version"] == 2
        assert json_block["accepts"][0]["planId"] == "plan-123"

    def test_successful_verify_execute_settle(self, mock_payments, mock_tool_context):
        """Test the full verify-execute-settle flow."""

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=2)
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": f"Result: {query}"}]}

        result = my_tool("test query", tool_context=mock_tool_context)

        assert result["status"] == "success"
        assert "Result: test query" in result["content"][0]["text"]

        # Verify was called
        mock_payments.facilitator.verify_permissions.assert_called_once()
        call_kwargs = mock_payments.facilitator.verify_permissions.call_args.kwargs
        assert call_kwargs["max_amount"] == "2"
        assert call_kwargs["x402_access_token"] == "test-x402-token"

        # Settle was called
        mock_payments.facilitator.settle_permissions.assert_called_once()
        settle_kwargs = mock_payments.facilitator.settle_permissions.call_args.kwargs
        assert settle_kwargs["max_amount"] == "2"
        assert settle_kwargs["agent_request_id"] == "test-request-id-123"

    def test_verification_failure_no_settlement(self, mock_payments, mock_tool_context):
        """Test that verification failure returns error with PaymentRequired."""
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False,
            invalid_reason="Insufficient credits",
            payer=None,
            agent_request_id=None,
        )

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "should not execute"}]}

        result = my_tool("test", tool_context=mock_tool_context)

        assert result["status"] == "error"
        assert "Insufficient credits" in result["content"][0]["text"]
        # x402 spec: error MUST include the PaymentRequired object
        json_block = result["content"][1]["json"]
        assert json_block["x402Version"] == 2
        assert json_block["accepts"][0]["planId"] == "plan-123"
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_tool_error_no_settlement(self, mock_payments, mock_tool_context):
        """Test that tool returning error prevents settlement."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_tool(query: str, tool_context=None):
            return {"status": "error", "content": [{"text": "Tool failed"}]}

        result = my_tool("test", tool_context=mock_tool_context)

        assert result["status"] == "error"
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_settlement_failure_still_returns_result(
        self, mock_payments, mock_tool_context
    ):
        """Test that settlement failure doesn't fail the tool result."""
        mock_payments.facilitator.settle_permissions.side_effect = Exception(
            "Settlement API down"
        )

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "Tool succeeded"}]}

        result = my_tool("test", tool_context=mock_tool_context)

        assert result["status"] == "success"
        assert "Tool succeeded" in result["content"][0]["text"]

    def test_payment_context_stored_in_invocation_state(
        self, mock_payments, mock_tool_context
    ):
        """Test that PaymentContext is stored in invocation_state."""

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=3)
        def my_tool(query: str, tool_context=None):
            ctx = tool_context.invocation_state.get("payment_context")
            assert ctx is not None
            assert isinstance(ctx, PaymentContext)
            assert ctx.token == "test-x402-token"
            assert ctx.credits_to_settle == 3
            assert ctx.verified is True
            assert ctx.agent_request_id == "test-request-id-123"
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", tool_context=mock_tool_context)
        assert result["status"] == "success"

    def test_multiple_plan_ids_creates_multiple_schemes(
        self, mock_payments, mock_tool_context
    ):
        """Test that multiple plan_ids creates multiple X402Scheme entries."""

        captured_pr = {}

        @requires_payment(
            payments=mock_payments,
            plan_ids=["plan-basic", "plan-premium"],
        )
        def my_tool(query: str, tool_context=None):
            ctx = tool_context.invocation_state.get("payment_context")
            captured_pr["payment_required"] = ctx.payment_required
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", tool_context=mock_tool_context)
        assert result["status"] == "success"

        pr = captured_pr["payment_required"]
        assert len(pr.accepts) == 2
        assert pr.accepts[0].plan_id == "plan-basic"
        assert pr.accepts[1].plan_id == "plan-premium"

    def test_dynamic_credits_callable(self, mock_payments, mock_tool_context):
        """Test dynamic credits via callable."""

        def calc_credits(kwargs):
            return kwargs.get("complexity", 1) * 2

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            credits=calc_credits,
        )
        def my_tool(query: str, complexity: int = 1, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", complexity=5, tool_context=mock_tool_context)
        assert result["status"] == "success"

        call_kwargs = mock_payments.facilitator.verify_permissions.call_args.kwargs
        assert call_kwargs["max_amount"] == "10"

    def test_token_fallback_from_kwargs(self, mock_payments):
        """Test that payment_token can be passed directly in kwargs."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", payment_token="direct-token")
        assert result["status"] == "success"

        call_kwargs = mock_payments.facilitator.verify_permissions.call_args.kwargs
        assert call_kwargs["x402_access_token"] == "direct-token"

    def test_functools_wraps_preserves_metadata(self, mock_payments):
        """Test that @functools.wraps preserves function metadata."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_awesome_tool(query: str, tool_context=None):
            """This is my awesome tool docstring."""
            return {"status": "success", "content": [{"text": "ok"}]}

        assert my_awesome_tool.__name__ == "my_awesome_tool"
        assert "awesome tool docstring" in my_awesome_tool.__doc__

    def test_agent_id_passed_to_payment_required(
        self, mock_payments, mock_tool_context
    ):
        """Test that agent_id is included in payment required."""

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            agent_id="my-agent-id",
        )
        def my_tool(query: str, tool_context=None):
            ctx = tool_context.invocation_state.get("payment_context")
            pr = ctx.payment_required
            assert pr.accepts[0].extra is not None
            assert pr.accepts[0].extra.agent_id == "my-agent-id"
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", tool_context=mock_tool_context)
        assert result["status"] == "success"


class TestRequiresPaymentHooks:
    """Tests for hook callbacks."""

    def test_before_verify_hook_called(self, mock_payments, mock_tool_context):
        """Test on_before_verify hook is called."""
        hook_calls = {"before": False}

        def on_before(payment_required):
            hook_calls["before"] = True
            assert payment_required.x402_version == 2

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_before_verify=on_before,
        )
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        my_tool("test", tool_context=mock_tool_context)
        assert hook_calls["before"] is True

    def test_after_verify_hook_called(self, mock_payments, mock_tool_context):
        """Test on_after_verify hook is called."""
        hook_calls = {"after": False}

        def on_after(verification):
            hook_calls["after"] = True
            assert verification.is_valid is True

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_after_verify=on_after,
        )
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        my_tool("test", tool_context=mock_tool_context)
        assert hook_calls["after"] is True

    def test_after_settle_hook_called(self, mock_payments, mock_tool_context):
        """Test on_after_settle hook is called."""
        hook_calls = {"settle": False}

        def on_settle(credits_used, settlement):
            hook_calls["settle"] = True
            assert credits_used == 1
            assert settlement.success is True

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_after_settle=on_settle,
        )
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        my_tool("test", tool_context=mock_tool_context)
        assert hook_calls["settle"] is True

    def test_payment_error_hook_custom_response(self, mock_payments, mock_tool_context):
        """Test on_payment_error hook returns custom error."""
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False,
            invalid_reason="Expired token",
            payer=None,
            agent_request_id=None,
        )

        def on_error(error):
            return {
                "status": "error",
                "content": [{"text": f"Custom error: {error}"}],
            }

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_payment_error=on_error,
        )
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", tool_context=mock_tool_context)
        assert result["status"] == "error"
        assert "Custom error" in result["content"][0]["text"]

    def test_payment_error_hook_missing_token(self, mock_payments):
        """Test on_payment_error hook is called on missing token."""
        hook_calls = {"error": False}

        def on_error(error):
            hook_calls["error"] = True
            return None  # Fall through to default x402 error

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_payment_error=on_error,
        )
        def my_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test")
        assert hook_calls["error"] is True
        assert result["status"] == "error"
        # Fallthrough returns x402-compliant error with PaymentRequired
        json_block = result["content"][1]["json"]
        assert json_block["x402Version"] == 2
        assert json_block["accepts"][0]["planId"] == "plan-123"


class TestRequiresPaymentAsync:
    """Tests for async tool decoration."""

    @pytest.mark.asyncio
    async def test_async_tool_verify_execute_settle(
        self, mock_payments, mock_tool_context
    ):
        """Test async tool with full payment flow."""

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=2)
        async def my_async_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": f"Async: {query}"}]}

        result = await my_async_tool("test", tool_context=mock_tool_context)

        assert result["status"] == "success"
        assert "Async: test" in result["content"][0]["text"]
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_called_once()

    @pytest.mark.asyncio
    async def test_async_tool_missing_token(self, mock_payments):
        """Test async tool returns error with PaymentRequired when token is missing."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        async def my_async_tool(query: str, tool_context=None):
            return {"status": "success", "content": [{"text": "ok"}]}

        result = await my_async_tool("test")
        assert result["status"] == "error"
        assert "missing payment_token" in result["content"][0]["text"]
        # x402 spec: error MUST include the PaymentRequired object
        json_block = result["content"][1]["json"]
        assert json_block["x402Version"] == 2
        assert json_block["accepts"][0]["planId"] == "plan-123"

    @pytest.mark.asyncio
    async def test_async_functools_wraps(self, mock_payments):
        """Test that async wrapper preserves metadata."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        async def my_named_async_tool(query: str, tool_context=None):
            """Async tool docstring."""
            return {"status": "success", "content": [{"text": "ok"}]}

        assert my_named_async_tool.__name__ == "my_named_async_tool"
        assert "Async tool docstring" in my_named_async_tool.__doc__


class TestSinglePlanIdDelegation:
    """Tests for single plan_id using build_payment_required helper."""

    def test_single_plan_uses_build_helper(self, mock_payments, mock_tool_context):
        """Test that single plan_id delegates to build_payment_required."""

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-single",
            agent_id="agent-1",
            network="eip155:1",
        )
        def my_tool(query: str, tool_context=None):
            ctx = tool_context.invocation_state.get("payment_context")
            pr = ctx.payment_required
            assert len(pr.accepts) == 1
            assert pr.accepts[0].plan_id == "plan-single"
            assert pr.accepts[0].network == "eip155:1"
            return {"status": "success", "content": [{"text": "ok"}]}

        result = my_tool("test", tool_context=mock_tool_context)
        assert result["status"] == "success"


class TestExtractPaymentRequired:
    """Tests for extract_payment_required()."""

    def test_extracts_payment_required_from_tool_result(self):
        """Test extraction from messages containing a toolResult with PaymentRequired."""
        messages = [
            {"role": "user", "content": [{"text": "Analyze data"}]},
            {
                "role": "assistant",
                "content": [
                    {
                        "type": "toolUse",
                        "toolUseId": "tool-1",
                        "name": "analyze_data",
                        "input": {"query": "test"},
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "toolResult",
                        "toolUseId": "tool-1",
                        "status": "error",
                        "content": [
                            {"text": "Payment required: missing payment_token"},
                            {
                                "json": {
                                    "x402Version": 2,
                                    "resource": {"url": "analyze_data"},
                                    "accepts": [
                                        {
                                            "scheme": "nvm:erc4337",
                                            "network": "eip155:84532",
                                            "planId": "plan-123",
                                        }
                                    ],
                                    "extensions": {},
                                }
                            },
                        ],
                    }
                ],
            },
        ]
        result = extract_payment_required(messages)
        assert result is not None
        assert result["x402Version"] == 2
        assert result["accepts"][0]["planId"] == "plan-123"

    def test_returns_none_for_empty_messages(self):
        """Test that empty messages returns None."""
        assert extract_payment_required([]) is None

    def test_returns_none_for_non_payment_tool_results(self):
        """Test that non-payment toolResults are ignored."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "toolResult",
                        "toolUseId": "tool-1",
                        "status": "error",
                        "content": [
                            {"text": "Some other error"},
                            {"json": {"error": "not a payment error"}},
                        ],
                    }
                ],
            },
        ]
        assert extract_payment_required(messages) is None

    def test_returns_none_for_success_tool_results(self):
        """Test that success toolResults without x402Version are ignored."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "toolResult",
                        "toolUseId": "tool-1",
                        "status": "success",
                        "content": [
                            {"text": "Analysis complete"},
                        ],
                    }
                ],
            },
        ]
        assert extract_payment_required(messages) is None

    def test_returns_first_payment_required_when_multiple_exist(self):
        """Test that the first PaymentRequired is returned when multiple exist."""
        messages = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "toolResult",
                        "toolUseId": "tool-1",
                        "status": "error",
                        "content": [
                            {"text": "Payment required"},
                            {
                                "json": {
                                    "x402Version": 2,
                                    "accepts": [{"planId": "plan-first"}],
                                }
                            },
                        ],
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "toolResult",
                        "toolUseId": "tool-2",
                        "status": "error",
                        "content": [
                            {"text": "Payment required"},
                            {
                                "json": {
                                    "x402Version": 2,
                                    "accepts": [{"planId": "plan-second"}],
                                }
                            },
                        ],
                    }
                ],
            },
        ]
        result = extract_payment_required(messages)
        assert result is not None
        assert result["accepts"][0]["planId"] == "plan-first"

    def test_handles_messages_without_content_list(self):
        """Test graceful handling of messages with non-list content."""
        messages = [
            {"role": "user", "content": "plain string content"},
            {"role": "assistant", "content": None},
            {"role": "user"},
        ]
        assert extract_payment_required(messages) is None
