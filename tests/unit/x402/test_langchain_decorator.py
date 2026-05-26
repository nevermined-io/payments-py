"""Unit tests for the LangChain x402 payment decorator and helpers."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

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


class TestLangSmithSpansIntegration:
    """Confirm @requires_payment invokes the LangSmith span helpers correctly."""

    def test_verify_and_settle_spans_are_opened(self, mock_payments):
        """Both context managers must be called with the resolved plan_ids/agent."""
        verify_calls: list[dict] = []
        settle_calls: list[dict] = []

        @contextmanager
        def fake_verify_span(**kwargs):
            verify_calls.append(kwargs)
            yield MagicMock(name="verify_span_handle")

        @contextmanager
        def fake_settlement_span(**kwargs):
            settle_calls.append(kwargs)
            yield MagicMock(name="settlement_span_handle")

        @tool
        @requires_payment(
            payments=mock_payments, plan_id="plan-123", credits=1, agent_id="agent-x"
        )
        def my_tool(topic: str, config: RunnableConfig = None) -> str:
            """Canned response."""
            return f"insight for {topic}"

        with (
            patch.object(decorator_module, "verify_span", fake_verify_span),
            patch.object(decorator_module, "settlement_span", fake_settlement_span),
        ):
            my_tool.invoke(
                {"topic": "x"},
                config={"configurable": {"payment_token": "tok"}},
            )

        assert len(verify_calls) == 1
        assert verify_calls[0]["plan_ids"] == ["plan-123"]
        assert verify_calls[0]["agent_id"] == "agent-x"

        assert len(settle_calls) == 1
        assert settle_calls[0]["plan_ids"] == ["plan-123"]
        assert settle_calls[0]["agent_id"] == "agent-x"

    def test_metadata_attached_to_parent_and_child_spans(self, mock_payments):
        """When a parent run is active, both the child span AND the parent receive nvm.* metadata."""
        parent_rt = MagicMock(name="parent_run_tree")
        verify_handle = MagicMock(name="verify_handle")
        settle_handle = MagicMock(name="settle_handle")

        @contextmanager
        def fake_verify_span(**kwargs):
            yield verify_handle

        @contextmanager
        def fake_settlement_span(**kwargs):
            yield settle_handle

        @tool
        @requires_payment(payments=mock_payments, plan_id="plan-123", credits=1)
        def my_tool(topic: str, config: RunnableConfig = None) -> str:
            """Canned response."""
            return f"insight for {topic}"

        with (
            patch.object(decorator_module, "active_run_tree", return_value=parent_rt),
            patch.object(decorator_module, "verify_span", fake_verify_span),
            patch.object(decorator_module, "settlement_span", fake_settlement_span),
        ):
            my_tool.invoke(
                {"topic": "x"},
                config={"configurable": {"payment_token": "tok"}},
            )

        # Verify span got metadata twice — once pre-verify (static fields only)
        # and once post-verify (augmented with payer + duration). Settle span
        # gets metadata once after the settle call.
        assert verify_handle.add_metadata.call_count == 2
        pre_verify_md = verify_handle.add_metadata.call_args_list[0].args[0]
        post_verify_md = verify_handle.add_metadata.call_args_list[1].args[0]
        assert pre_verify_md["nvm.plan_ids"] == ["plan-123"]
        assert "nvm.payer" not in pre_verify_md
        assert "nvm.verify.duration_ms" not in pre_verify_md
        assert post_verify_md["nvm.payer"] == "0x1234567890abcdef"
        assert "nvm.verify.duration_ms" in post_verify_md

        settle_handle.add_metadata.assert_called_once()
        settle_md = settle_handle.add_metadata.call_args.args[0]
        assert settle_md["nvm.credits_redeemed"] == "1"
        assert settle_md["nvm.tx_hash"] == "0xabc123"
        assert settle_md["nvm.balance.after"] == "99"

        # Parent run tree gets metadata three times: pre-verify, post-verify,
        # settle. All payloads should carry nvm.* keys.
        assert parent_rt.add_metadata.call_count == 3
        all_parent_md = {
            k: v
            for call in parent_rt.add_metadata.call_args_list
            for k, v in call.args[0].items()
        }
        assert all_parent_md["nvm.plan_ids"] == ["plan-123"]
        assert all_parent_md["nvm.payer"] == "0x1234567890abcdef"
        assert all_parent_md["nvm.credits_redeemed"] == "1"
        assert all_parent_md["nvm.tx_hash"] == "0xabc123"

    def test_spans_no_op_when_no_active_run(self, mock_payments):
        """With no LangSmith run active, parent metadata is skipped and tool still works."""
        my_tool = _make_protected_tool(mock_payments)

        # active_run_tree returns None by default in unit-test environment (no
        # LANGSMITH_TRACING set). Confirm the tool completes normally.
        result = my_tool.invoke(
            {"topic": "x"},
            config={"configurable": {"payment_token": "tok"}},
        )

        assert result == "insight for x"
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_called_once()

    def test_redacts_payment_token_from_parent_run_metadata(self, mock_payments):
        """Parent run's payment_token (LangChain auto-captured) is stripped.

        LangChain serializes config["configurable"] into the parent tool span's
        metadata. The full x402 access token grants access to the protected
        tool until it expires, so the decorator strips it from the parent run
        before opening any nvm:* child span. The abbreviated nvm.payment_token
        remains available via build_verify_metadata for correlation.
        """
        # Build a fake parent run tree that mirrors what LangChain would set up:
        # config["configurable"] was captured into extra["metadata"].
        parent_metadata = {
            "payment_token": "eyJ4NDAyVmVyc2lvbi.full_secret.dont_leak",
            "other_key": "preserve",
        }
        parent_rt = MagicMock(name="parent_run_tree")
        parent_rt.extra = {"metadata": parent_metadata}

        @contextmanager
        def fake_span(**kwargs):
            yield MagicMock()

        my_tool = _make_protected_tool(mock_payments)

        with (
            patch.object(decorator_module, "active_run_tree", return_value=parent_rt),
            patch.object(decorator_module, "verify_span", fake_span),
            patch.object(decorator_module, "settlement_span", fake_span),
        ):
            my_tool.invoke(
                {"topic": "x"},
                config={"configurable": {"payment_token": "tok"}},
            )

        assert "payment_token" not in parent_metadata
        assert parent_metadata.get("other_key") == "preserve"

    def test_settle_metadata_failure_does_not_strand_receipt(self, mock_payments):
        """If build_settle_metadata raises, last_settlement() must still update.

        Regression: the on-chain settle has already happened. An observability
        error after the facilitator call must not orphan the local receipt.
        """
        parent_rt = MagicMock(name="parent_run_tree")
        verify_handle = MagicMock(name="verify_handle")
        settle_handle = MagicMock(name="settle_handle")

        @contextmanager
        def fake_verify(**kwargs):
            yield verify_handle

        @contextmanager
        def fake_settle(**kwargs):
            yield settle_handle

        my_tool = _make_protected_tool(mock_payments)

        with (
            patch.object(decorator_module, "active_run_tree", return_value=parent_rt),
            patch.object(decorator_module, "verify_span", fake_verify),
            patch.object(decorator_module, "settlement_span", fake_settle),
            patch.object(
                decorator_module,
                "build_settle_metadata",
                side_effect=RuntimeError("synthetic build failure"),
            ),
        ):
            result = my_tool.invoke(
                {"topic": "x"},
                config={"configurable": {"payment_token": "tok"}},
            )

        # Tool result returned and receipt persisted despite the metadata error.
        assert result == "insight for x"
        assert last_settlement() is not None
        assert last_settlement().credits_redeemed == "1"
        assert last_settlement().transaction == "0xabc123"

    def test_verify_metadata_failure_does_not_mask_payment_required(
        self, mock_payments
    ):
        """If build_verify_metadata raises on the invalid path, PaymentRequiredError still propagates.

        Regression: callers depend on the PaymentRequiredError contract. A
        metadata build failure must not surface as a generic TypeError.
        """
        # Force the facilitator to return is_valid=False.
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False,
            invalid_reason="token expired",
        )
        parent_rt = MagicMock(name="parent_run_tree")

        @contextmanager
        def fake_span(**kwargs):
            yield MagicMock()

        my_tool = _make_protected_tool(mock_payments)

        with (
            patch.object(decorator_module, "active_run_tree", return_value=parent_rt),
            patch.object(decorator_module, "verify_span", fake_span),
            patch.object(decorator_module, "settlement_span", fake_span),
            patch.object(
                decorator_module,
                "build_verify_metadata",
                side_effect=RuntimeError("synthetic build failure"),
            ),
        ):
            with pytest.raises(PaymentRequiredError) as excinfo:
                my_tool.invoke(
                    {"topic": "x"},
                    config={"configurable": {"payment_token": "tok"}},
                )

        # Original contract preserved.
        assert "token expired" in str(excinfo.value)
        mock_payments.facilitator.settle_permissions.assert_not_called()

    @pytest.mark.asyncio
    async def test_async_path_emits_verify_and_settle_spans(self, mock_payments):
        """Async tool path mirrors the sync path -- spans emit on ainvoke().

        Regression guard for a future refactor that might inline payment logic
        into the sync wrapper and break the async path silently.
        """
        verify_calls: list[dict] = []
        settle_calls: list[dict] = []

        @contextmanager
        def fake_verify_span(**kwargs):
            verify_calls.append(kwargs)
            yield MagicMock(name="verify_span_handle")

        @contextmanager
        def fake_settlement_span(**kwargs):
            settle_calls.append(kwargs)
            yield MagicMock(name="settlement_span_handle")

        @tool
        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            credits=1,
            agent_id="agent-x",
        )
        async def my_async_tool(topic: str, config: RunnableConfig = None) -> str:
            """Canned async response."""
            return f"async insight for {topic}"

        with (
            patch.object(decorator_module, "verify_span", fake_verify_span),
            patch.object(decorator_module, "settlement_span", fake_settlement_span),
        ):
            result = await my_async_tool.ainvoke(
                {"topic": "x"},
                config={"configurable": {"payment_token": "tok"}},
            )

        assert result == "async insight for x"
        assert len(verify_calls) == 1
        assert verify_calls[0]["plan_ids"] == ["plan-123"]
        assert verify_calls[0]["agent_id"] == "agent-x"
        assert len(settle_calls) == 1
        assert settle_calls[0]["plan_ids"] == ["plan-123"]
        assert settle_calls[0]["agent_id"] == "agent-x"

    def test_failed_probe_still_emits_verify_span_with_nvm_metadata(
        self, mock_payments
    ):
        """Discovery probe (no payment_token) must still produce an nvm:verify span.

        The span is marked failed by the PaymentRequiredError, but it carries the
        static nvm.* attrs (plan_ids, scheme, agent_id) so the buyer's failed
        trace is still identifiable as a Nevermined verify failure rather than
        an opaque LangChain crash.
        """
        parent_rt = MagicMock(name="parent_run_tree")
        verify_handle = MagicMock(name="verify_handle")
        settle_handle = MagicMock(name="settle_handle")
        verify_opened = []

        @contextmanager
        def fake_verify_span(**kwargs):
            verify_opened.append(kwargs)
            yield verify_handle

        @contextmanager
        def fake_settlement_span(**kwargs):
            yield settle_handle

        @tool
        @requires_payment(
            payments=mock_payments,
            plan_id="plan-123",
            credits=1,
            agent_id="agent-x",
        )
        def my_tool(topic: str, config: RunnableConfig = None) -> str:
            """Canned response."""
            return f"insight for {topic}"

        with (
            patch.object(decorator_module, "active_run_tree", return_value=parent_rt),
            patch.object(decorator_module, "verify_span", fake_verify_span),
            patch.object(decorator_module, "settlement_span", fake_settlement_span),
        ):
            with pytest.raises(PaymentRequiredError):
                # No payment_token — should still open the verify span and tag
                # the parent + span with the pre-verify nvm.* metadata.
                my_tool.invoke({"topic": "x"}, config={"configurable": {}})

        # verify_span was opened (before the token check) with the expected
        # inputs.
        assert len(verify_opened) == 1
        assert verify_opened[0]["plan_ids"] == ["plan-123"]
        assert verify_opened[0]["agent_id"] == "agent-x"

        # Span got pre-verify metadata before the raise.
        verify_handle.add_metadata.assert_called_once()
        pre_md = verify_handle.add_metadata.call_args.args[0]
        assert pre_md["nvm.plan_ids"] == ["plan-123"]
        assert pre_md["nvm.agent_id"] == "agent-x"
        # No verification ran yet, so dynamic fields are absent.
        assert "nvm.payer" not in pre_md
        assert "nvm.verify.duration_ms" not in pre_md

        # Parent got the same metadata — so the failed trace is still searchable
        # by nvm.plan_ids in the LangSmith UI.
        parent_rt.add_metadata.assert_called_once_with(pre_md)

        # Facilitator never invoked (we short-circuit inside the span).
        mock_payments.facilitator.verify_permissions.assert_not_called()
        mock_payments.facilitator.settle_permissions.assert_not_called()
        # Settlement span never opened either.
        settle_handle.add_metadata.assert_not_called()
