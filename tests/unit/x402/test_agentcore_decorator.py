"""
Unit tests for AgentCore x402 payment decorator.
"""

import json
from unittest.mock import MagicMock

import pytest

from payments_py.x402.agentcore import requires_payment
from payments_py.x402.agentcore.decorator import (
    _build_402_response,
    _build_error_response,
    _extract_request,
    _resolve_credits,
    _wrap_result_as_response,
    _settlement_receipt,
)
from payments_py.x402.agentcore.helpers import decode_header
from payments_py.x402.types import VerifyResponse, SettleResponse

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_event(tool_name="Healthcare___getPatient", arguments=None, token=None):
    """Build an AgentCore MCP interceptor event."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["payment-signature"] = token

    return {
        "mcp": {
            "gatewayRequest": {
                "httpMethod": "POST",
                "headers": headers,
                "body": {
                    "jsonrpc": "2.0",
                    "id": "req-1",
                    "method": "tools/call",
                    "params": {
                        "name": tool_name,
                        "arguments": arguments or {"patient_id": "123"},
                    },
                },
            }
        }
    }


def _get_transformed_response(result):
    """Extract the transformedGatewayResponse from an interceptor output."""
    return result.get("mcp", {}).get("transformedGatewayResponse", {})


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


class TestExtractRequest:
    """Tests for _extract_request."""

    def test_extracts_headers_and_body(self):
        event = _make_event(token="my-token")
        headers, body = _extract_request(event)
        assert headers["payment-signature"] == "my-token"
        assert body["method"] == "tools/call"

    def test_empty_event(self):
        headers, body = _extract_request({})
        assert headers == {}
        assert body == {}


class TestResolveCredits:
    """Tests for _resolve_credits."""

    def test_static_credits(self):
        assert _resolve_credits(5, {}) == 5

    def test_callable_credits(self):
        def calc(event):
            params = (
                event.get("mcp", {})
                .get("gatewayRequest", {})
                .get("body", {})
                .get("params", {})
            )
            return len(params.get("arguments", {})) * 2

        event = _make_event(arguments={"a": 1, "b": 2, "c": 3})
        assert _resolve_credits(calc, event) == 6


class TestBuild402Response:
    """Tests for _build_402_response."""

    def test_contains_payment_required_header(self):
        from payments_py.x402.helpers import build_payment_required

        pr = build_payment_required(plan_id="plan-123", endpoint="/test")
        result = _build_402_response(pr, rpc_id="req-1")

        response = result["mcp"]["transformedGatewayResponse"]
        assert "payment-required" in response["headers"]
        assert response["statusCode"] == 200

        # Decode the payment-required header
        decoded = decode_header(response["headers"]["payment-required"])
        assert decoded["x402Version"] == 2
        assert decoded["accepts"][0]["planId"] == "plan-123"

    def test_body_has_is_error(self):
        from payments_py.x402.helpers import build_payment_required

        pr = build_payment_required(plan_id="plan-123", endpoint="/test")
        result = _build_402_response(pr, rpc_id="req-1")

        body = result["mcp"]["transformedGatewayResponse"]["body"]
        assert body["result"]["isError"] is True
        assert body["id"] == "req-1"


class TestBuildErrorResponse:
    """Tests for _build_error_response."""

    def test_error_format(self):
        result = _build_error_response("Something broke", rpc_id="req-2")
        response = result["mcp"]["transformedGatewayResponse"]
        body = response["body"]
        assert body["result"]["isError"] is True
        assert body["id"] == "req-2"
        error_text = json.loads(body["result"]["content"][0]["text"])
        assert error_text["error"] == "Something broke"
        assert error_text["code"] == 500


class TestWrapResultAsResponse:
    """Tests for _wrap_result_as_response."""

    @pytest.fixture
    def settlement(self):
        return SettleResponse(
            success=True,
            transaction="0xabc",
            network="eip155:84532",
            credits_redeemed="2",
            remaining_balance="98",
        )

    def test_wraps_bare_result(self, settlement):
        bare = {"content": [{"type": "text", "text": "hello"}]}
        result = _wrap_result_as_response(bare, settlement, rpc_id="req-1")

        response = _get_transformed_response(result)
        assert "payment-response" in response["headers"]
        assert response["body"]["jsonrpc"] == "2.0"
        assert response["body"]["id"] == "req-1"
        assert response["body"]["result"]["content"][0]["text"] == "hello"

        # Check _meta.x402
        meta = response["body"]["result"]["_meta"]["x402"]
        assert meta["success"] is True
        assert meta["creditsRedeemed"] == "2"

    def test_wraps_full_mcp_body(self, settlement):
        full = {
            "jsonrpc": "2.0",
            "id": "req-5",
            "result": {"content": [{"type": "text", "text": "data"}]},
        }
        result = _wrap_result_as_response(full, settlement, rpc_id="req-5")

        response = _get_transformed_response(result)
        assert response["body"]["id"] == "req-5"
        meta = response["body"]["result"]["_meta"]["x402"]
        assert meta["transaction"] == "0xabc"

    def test_passes_through_interceptor_output(self, settlement):
        existing = {
            "interceptorOutputVersion": "1.0",
            "mcp": {
                "transformedGatewayResponse": {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": {
                        "jsonrpc": "2.0",
                        "id": "req-7",
                        "result": {"content": [{"type": "text", "text": "ok"}]},
                    },
                }
            },
        }
        result = _wrap_result_as_response(existing, settlement)

        response = _get_transformed_response(result)
        assert "payment-response" in response["headers"]
        meta = response["body"]["result"]["_meta"]["x402"]
        assert meta["success"] is True


class TestSettlementReceipt:
    """Tests for _settlement_receipt."""

    def test_receipt_fields(self):
        settlement = SettleResponse(
            success=True,
            transaction="0xdef",
            network="eip155:84532",
            credits_redeemed="3",
            remaining_balance="50",
        )
        receipt = _settlement_receipt(settlement)
        assert receipt["success"] is True
        assert receipt["transactionHash"] == "0xdef"
        assert receipt["network"] == "eip155:84532"
        assert receipt["creditsRedeemed"] == "3"
        assert receipt["remainingBalance"] == "50"


# ---------------------------------------------------------------------------
# Decorator: validation
# ---------------------------------------------------------------------------


class TestRequiresPaymentValidation:
    """Tests for requires_payment parameter validation."""

    def test_no_plan_id_raises(self, mock_payments):
        with pytest.raises(ValueError, match="Either plan_id or plan_ids"):

            @requires_payment(payments=mock_payments)
            def handler(event, context=None):
                pass

    def test_plan_id_convenience_alias(self, mock_payments):

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            return {"content": []}

        assert callable(handler)

    def test_plan_ids_list(self, mock_payments):

        @requires_payment(payments=mock_payments, plan_ids=["plan-a", "plan-b"])
        def handler(event, context=None):
            return {"content": []}

        assert callable(handler)


# ---------------------------------------------------------------------------
# Decorator: full flow
# ---------------------------------------------------------------------------


class TestRequiresPaymentFlow:
    """Tests for the verify → execute → settle flow."""

    def test_no_token_returns_402(self, mock_payments):
        """Request without token → 402 with payment-required header."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            return {"content": [{"type": "text", "text": "should not run"}]}

        result = handler(_make_event())

        response = _get_transformed_response(result)
        assert "payment-required" in response["headers"]

        decoded = decode_header(response["headers"]["payment-required"])
        assert decoded["x402Version"] == 2
        assert decoded["accepts"][0]["planId"] == "plan-123"

        # Handler was NOT called, facilitator was NOT called
        mock_payments.facilitator.verify_permissions.assert_not_called()
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_valid_token_verify_execute_settle(self, mock_payments):
        """Request with valid token → verify + execute + settle."""
        executed = {"called": False}

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=2)
        def handler(event, context=None):
            executed["called"] = True
            return {"content": [{"type": "text", "text": "result"}]}

        result = handler(_make_event(token="valid-token"))

        assert executed["called"] is True

        # Verify was called with correct args
        mock_payments.facilitator.verify_permissions.assert_called_once()
        verify_kwargs = mock_payments.facilitator.verify_permissions.call_args.kwargs
        assert verify_kwargs["x402_access_token"] == "valid-token"
        assert verify_kwargs["max_amount"] == "2"

        # Settle was called
        mock_payments.facilitator.settle_permissions.assert_called_once()
        settle_kwargs = mock_payments.facilitator.settle_permissions.call_args.kwargs
        assert settle_kwargs["max_amount"] == "2"
        assert settle_kwargs["agent_request_id"] == "test-request-id-123"

        # Response has payment-response header
        response = _get_transformed_response(result)
        assert "payment-response" in response["headers"]
        meta = response["body"]["result"]["_meta"]["x402"]
        assert meta["success"] is True
        assert meta["creditsRedeemed"] == "1"

    def test_verification_failure_returns_402(self, mock_payments):
        """Invalid token → 402, handler NOT executed, no settle."""
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False,
            invalid_reason="Insufficient credits",
        )

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            raise AssertionError("Should not be called")

        result = handler(_make_event(token="bad-token"))

        response = _get_transformed_response(result)
        assert "payment-required" in response["headers"]

        decoded = decode_header(response["headers"]["payment-required"])
        assert decoded["accepts"][0]["planId"] == "plan-123"

        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_handler_exception_returns_error(self, mock_payments):
        """Handler raising exception → error response."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            raise RuntimeError("Agent crashed")

        result = handler(_make_event(token="valid-token"))

        response = _get_transformed_response(result)
        body = response["body"]
        assert body["result"]["isError"] is True
        error_text = json.loads(body["result"]["content"][0]["text"])
        assert "Agent crashed" in error_text["error"]

    def test_settlement_failure_still_returns_result(self, mock_payments):
        """Settlement error → handler result still returned (no payment-response)."""
        mock_payments.facilitator.settle_permissions.side_effect = Exception(
            "Settlement API down"
        )

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            return {"content": [{"type": "text", "text": "result data"}]}

        result = handler(_make_event(token="valid-token"))

        response = _get_transformed_response(result)
        body = response["body"]
        # Result still returned even though settlement failed
        assert body["result"]["content"][0]["text"] == "result data"
        # No payment-response header since settlement failed
        assert "payment-response" not in response["headers"]

    def test_context_passed_to_handler(self, mock_payments):
        """Lambda context is forwarded to the handler."""
        received_context = {}

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            received_context["ctx"] = context
            return {"content": []}

        mock_ctx = MagicMock()
        mock_ctx.function_name = "my-lambda"
        handler(_make_event(token="valid-token"), mock_ctx)

        assert received_context["ctx"].function_name == "my-lambda"

    def test_functools_wraps_preserves_metadata(self, mock_payments):
        """Decorator preserves function name and docstring."""

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def my_healthcare_handler(event, context=None):
            """Handle healthcare requests."""
            return {"content": []}

        assert my_healthcare_handler.__name__ == "my_healthcare_handler"
        assert "healthcare requests" in my_healthcare_handler.__doc__


# ---------------------------------------------------------------------------
# Credits: _meta.creditsToCharge override
# ---------------------------------------------------------------------------


class TestCreditsOverride:
    """Tests for credits extraction from handler response."""

    def test_meta_credits_overrides_config(self, mock_payments):
        """Handler returning _meta.creditsToCharge overrides decorator credits."""

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=1)
        def handler(event, context=None):
            return {
                "content": [{"type": "text", "text": "expensive result"}],
                "_meta": {"creditsToCharge": 5},
            }

        handler(_make_event(token="valid-token"))

        # Verify used config credits (1)
        verify_kwargs = mock_payments.facilitator.verify_permissions.call_args.kwargs
        assert verify_kwargs["max_amount"] == "1"

        # Settle used response credits (5)
        settle_kwargs = mock_payments.facilitator.settle_permissions.call_args.kwargs
        assert settle_kwargs["max_amount"] == "5"

    def test_no_meta_uses_config_credits(self, mock_payments):
        """No _meta.creditsToCharge → settle uses config credits."""

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=3)
        def handler(event, context=None):
            return {"content": [{"type": "text", "text": "plain result"}]}

        handler(_make_event(token="valid-token"))

        settle_kwargs = mock_payments.facilitator.settle_permissions.call_args.kwargs
        assert settle_kwargs["max_amount"] == "3"

    def test_callable_credits(self, mock_payments):
        """Dynamic credits via callable."""

        def calc(event):
            args = (
                event.get("mcp", {})
                .get("gatewayRequest", {})
                .get("body", {})
                .get("params", {})
                .get("arguments", {})
            )
            return 10 if args.get("detailed") else 1

        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=calc)
        def handler(event, context=None):
            return {"content": [{"type": "text", "text": "ok"}]}

        handler(_make_event(arguments={"detailed": True}, token="valid-token"))

        verify_kwargs = mock_payments.facilitator.verify_permissions.call_args.kwargs
        assert verify_kwargs["max_amount"] == "10"


# ---------------------------------------------------------------------------
# Hooks
# ---------------------------------------------------------------------------


class TestHooks:
    """Tests for lifecycle hooks."""

    def test_before_verify_hook(self, mock_payments):
        calls = {"before": False}

        def on_before(payment_required):
            calls["before"] = True
            assert payment_required.x402_version == 2

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_before_verify=on_before,
        )
        def handler(event, context=None):
            return {"content": []}

        handler(_make_event(token="valid-token"))
        assert calls["before"] is True

    def test_after_verify_hook(self, mock_payments):
        calls = {"after": False}

        def on_after(verification):
            calls["after"] = True
            assert verification.is_valid is True
            assert verification.payer == "0x1234567890abcdef"

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_after_verify=on_after,
        )
        def handler(event, context=None):
            return {"content": []}

        handler(_make_event(token="valid-token"))
        assert calls["after"] is True

    def test_after_settle_hook(self, mock_payments):
        calls = {"settle": False}

        def on_settle(credits_used, settlement):
            calls["settle"] = True
            assert credits_used == 1
            assert settlement.success is True

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_after_settle=on_settle,
        )
        def handler(event, context=None):
            return {"content": []}

        handler(_make_event(token="valid-token"))
        assert calls["settle"] is True

    def test_error_hook_custom_response(self, mock_payments):
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False, invalid_reason="Expired"
        )

        def on_error(exc):
            return {
                "interceptorOutputVersion": "1.0",
                "mcp": {
                    "transformedGatewayResponse": {
                        "statusCode": 200,
                        "headers": {},
                        "body": {"custom": "error"},
                    }
                },
            }

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_payment_error=on_error,
        )
        def handler(event, context=None):
            return {"content": []}

        result = handler(_make_event(token="bad-token"))
        response = _get_transformed_response(result)
        assert response["body"] == {"custom": "error"}

    def test_error_hook_returns_none_falls_through(self, mock_payments):
        """Error hook returning None → default 402 response."""
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False, invalid_reason="Expired"
        )

        hook_called = {"called": False}

        def on_error(exc):
            hook_called["called"] = True
            return None

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            on_payment_error=on_error,
        )
        def handler(event, context=None):
            return {"content": []}

        result = handler(_make_event(token="bad-token"))
        assert hook_called["called"] is True

        # Falls through to default 402
        response = _get_transformed_response(result)
        assert "payment-required" in response["headers"]


# ---------------------------------------------------------------------------
# Token header variants
# ---------------------------------------------------------------------------


class TestTokenHeaders:
    """Tests for custom token header names."""

    def test_custom_single_header(self, mock_payments):

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            token_header="X-Payment",
        )
        def handler(event, context=None):
            return {"content": []}

        event = _make_event()
        event["mcp"]["gatewayRequest"]["headers"]["X-Payment"] = "my-token"

        result = handler(event)
        response = _get_transformed_response(result)
        # Should have payment-response (successful flow)
        assert "payment-response" in response["headers"]

    def test_custom_header_list(self, mock_payments):

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            token_header=["x-pay", "Authorization"],
        )
        def handler(event, context=None):
            return {"content": []}

        event = _make_event()
        event["mcp"]["gatewayRequest"]["headers"]["Authorization"] = "my-token"

        result = handler(event)
        response = _get_transformed_response(result)
        assert "payment-response" in response["headers"]

    def test_case_insensitive_headers(self, mock_payments):

        @requires_payment(payments=mock_payments, plan_id="plan-123")
        def handler(event, context=None):
            return {"content": []}

        event = _make_event()
        event["mcp"]["gatewayRequest"]["headers"]["PAYMENT-SIGNATURE"] = "my-token"

        result = handler(event)
        response = _get_transformed_response(result)
        assert "payment-response" in response["headers"]


# ---------------------------------------------------------------------------
# Agent ID and endpoint
# ---------------------------------------------------------------------------


class TestAgentConfig:
    """Tests for agent_id and endpoint configuration."""

    def test_agent_id_in_payment_required(self, mock_payments):

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            agent_id="agent-456",
        )
        def handler(event, context=None):
            return {"content": []}

        result = handler(_make_event())  # No token → 402

        response = _get_transformed_response(result)
        decoded = decode_header(response["headers"]["payment-required"])
        assert decoded["accepts"][0]["extra"]["agentId"] == "agent-456"

    def test_endpoint_in_payment_required(self, mock_payments):

        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            endpoint="https://my-api.example.com/v1",
        )
        def handler(event, context=None):
            return {"content": []}

        result = handler(_make_event())  # No token → 402

        response = _get_transformed_response(result)
        decoded = decode_header(response["headers"]["payment-required"])
        assert decoded["resource"]["url"] == "https://my-api.example.com/v1"
