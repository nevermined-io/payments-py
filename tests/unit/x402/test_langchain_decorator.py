"""Unit tests for the LangChain x402 payment decorator and helpers."""

from unittest.mock import MagicMock

import pytest
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from payments_py.x402.langchain import (
    PaymentRequiredError,
    create_paid_react_agent,
    last_settlement,
    requires_payment,
)
from payments_py.x402.langchain import decorator as decorator_module
from payments_py.x402.types import SettleResponse, VerifyResponse


@pytest.fixture
def mock_payments():
    """A Payments-like mock with verify + settle stubbed."""
    payments = MagicMock()
    payments.facilitator.verify_permissions.return_value = VerifyResponse(
        is_valid=True,
        invalid_reason=None,
        payer="0x1234567890abcdef",
        agent_request_id="test-request-id-123",
    )
    payments.facilitator.settle_permissions.return_value = SettleResponse(
        success=True,
        error_reason=None,
        payer="0x1234567890abcdef",
        transaction="0xabc123",
        network="eip155:84532",
        credits_redeemed="1",
        remaining_balance="99",
    )
    return payments


@pytest.fixture(autouse=True)
def reset_last_settlement():
    """Reset the module-level holder between tests so they don't bleed state."""
    decorator_module._LAST_SETTLEMENT["value"] = None
    yield
    decorator_module._LAST_SETTLEMENT["value"] = None


def _make_protected_tool(mock_payments, *, credits=1):
    """Build a minimal @tool wrapped with @requires_payment."""

    @tool
    @requires_payment(payments=mock_payments, plan_id="plan-123", credits=credits)
    def my_tool(topic: str, config: RunnableConfig = None) -> str:
        """Return a canned string."""
        return f"insight for {topic}"

    return my_tool


class TestRequiresPaymentDecorator:
    def test_raises_payment_required_when_no_token(self, mock_payments):
        """No payment_token in configurable → PaymentRequiredError with payload."""
        my_tool = _make_protected_tool(mock_payments)

        with pytest.raises(PaymentRequiredError) as excinfo:
            my_tool.invoke({"topic": "x"}, config={"configurable": {}})

        assert excinfo.value.payment_required is not None
        accepts = excinfo.value.payment_required.accepts
        assert len(accepts) == 1
        assert accepts[0].plan_id == "plan-123"
        # verify_permissions must not have been called — we short-circuited
        mock_payments.facilitator.verify_permissions.assert_not_called()
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_verifies_and_settles_on_success(self, mock_payments):
        my_tool = _make_protected_tool(mock_payments)

        result = my_tool.invoke(
            {"topic": "evs"},
            config={"configurable": {"payment_token": "tok-abc"}},
        )

        assert result == "insight for evs"
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_called_once()

    def test_settle_failure_does_not_break_result(self, mock_payments):
        """If settle_permissions raises, the tool result is still returned."""
        mock_payments.facilitator.settle_permissions.side_effect = RuntimeError("boom")
        my_tool = _make_protected_tool(mock_payments)

        result = my_tool.invoke(
            {"topic": "x"},
            config={"configurable": {"payment_token": "tok"}},
        )

        assert result == "insight for x"


class TestLastSettlement:
    def test_returns_none_before_any_settlement(self):
        assert last_settlement() is None

    def test_returns_latest_settle_response(self, mock_payments):
        my_tool = _make_protected_tool(mock_payments)
        my_tool.invoke(
            {"topic": "x"},
            config={"configurable": {"payment_token": "tok"}},
        )

        receipt = last_settlement()
        assert receipt is not None
        assert receipt.credits_redeemed == "1"
        assert receipt.remaining_balance == "99"
        assert receipt.transaction == "0xabc123"

    def test_overwritten_by_subsequent_settlement(self, mock_payments):
        """Last-writer-wins semantics: a second call overrides the first."""
        my_tool = _make_protected_tool(mock_payments)

        my_tool.invoke(
            {"topic": "a"}, config={"configurable": {"payment_token": "tok"}}
        )
        first = last_settlement()
        assert first.credits_redeemed == "1"

        # Adjust the mock to return a different receipt on the next call
        mock_payments.facilitator.settle_permissions.return_value = SettleResponse(
            success=True,
            payer="0x1234567890abcdef",
            transaction="0xdef456",
            network="eip155:84532",
            credits_redeemed="2",
            remaining_balance="97",
        )
        my_tool.invoke(
            {"topic": "b"}, config={"configurable": {"payment_token": "tok"}}
        )

        second = last_settlement()
        assert second.credits_redeemed == "2"
        assert second.transaction == "0xdef456"

    def test_not_set_when_no_token_provided(self, mock_payments):
        """PaymentRequiredError path must not leave a stale receipt."""
        my_tool = _make_protected_tool(mock_payments)
        with pytest.raises(PaymentRequiredError):
            my_tool.invoke({"topic": "x"}, config={"configurable": {}})
        assert last_settlement() is None


class TestCreatePaidReactAgent:
    def test_returns_invokable_graph(self, mock_payments):
        """The helper builds an agent that has the ``invoke`` API."""
        pytest.importorskip("langgraph")
        my_tool = _make_protected_tool(mock_payments)

        # Use a stub model that satisfies create_react_agent's type expectations
        # but is never actually called — we don't run the agent.
        model = MagicMock(name="stub_chat_model")
        model.bind_tools.return_value = model

        agent = create_paid_react_agent(model, [my_tool])

        assert hasattr(agent, "invoke")
        assert callable(agent.invoke)

    def test_tool_node_has_handle_tool_errors_disabled(self, mock_payments):
        """Introspect the agent graph to assert the ToolNode policy."""
        pytest.importorskip("langgraph")
        my_tool = _make_protected_tool(mock_payments)
        model = MagicMock(name="stub_chat_model")
        model.bind_tools.return_value = model

        agent = create_paid_react_agent(model, [my_tool])

        # The compiled graph exposes its inner nodes; find the tool node and
        # confirm handle_tool_errors was set to False. Internal API — if
        # LangGraph reshapes this, the test breaks loudly which is the point.
        tools_node = agent.get_graph().nodes["tools"]
        underlying = getattr(tools_node, "data", tools_node)
        handle = getattr(underlying, "handle_tool_errors", None)
        assert (
            handle is False
        ), f"Expected ToolNode.handle_tool_errors=False, got {handle!r}"
