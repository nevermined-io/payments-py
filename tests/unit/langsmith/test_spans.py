"""Unit tests for the LangSmith span helpers."""

from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from payments_py.langsmith import spans
from payments_py.langsmith.spans import (
    active_run_tree,
    add_metadata,
    build_settle_metadata,
    build_verify_metadata,
    settlement_span,
    verify_span,
)
from payments_py.x402.types import SettleResponse, VerifyResponse

# --------------------------------------------------------------------------- #
# build_verify_metadata
# --------------------------------------------------------------------------- #


def test_build_verify_metadata_minimal():
    md = build_verify_metadata(plan_ids=["plan-1"])
    assert md == {"nvm.plan_ids": ["plan-1"]}


def test_build_verify_metadata_full_static_fields():
    md = build_verify_metadata(
        plan_ids=["plan-1", "plan-2"],
        scheme="nvm:card-delegation",
        network="stripe",
        agent_id="agent-xyz",
        duration_ms=12.345,
    )
    assert md == {
        "nvm.plan_ids": ["plan-1", "plan-2"],
        "nvm.scheme": "nvm:card-delegation",
        "nvm.network": "stripe",
        "nvm.agent_id": "agent-xyz",
        "nvm.verify.duration_ms": 12.35,  # rounded to 2 dp
    }


def test_build_verify_metadata_extracts_from_verification():
    verification = VerifyResponse(
        is_valid=True,
        payer="0xpayer",
        network="base-sepolia",
        agent_request_id="req-123",
    )
    md = build_verify_metadata(
        plan_ids=["plan-1"],
        verification=verification,
    )
    assert md["nvm.payer"] == "0xpayer"
    assert md["nvm.network"] == "base-sepolia"
    assert md["nvm.agent_request_id"] == "req-123"


def test_build_verify_metadata_explicit_network_wins_over_verification():
    verification = VerifyResponse(is_valid=True, network="base-sepolia")
    md = build_verify_metadata(
        plan_ids=["plan-1"],
        network="stripe",
        verification=verification,
    )
    assert md["nvm.network"] == "stripe"


def test_build_verify_metadata_drops_none_and_empty():
    md = build_verify_metadata(plan_ids=["plan-1"], scheme=None, agent_id="")
    assert "nvm.scheme" not in md
    assert "nvm.agent_id" not in md


# --------------------------------------------------------------------------- #
# build_settle_metadata
# --------------------------------------------------------------------------- #


def test_build_settle_metadata_full():
    settlement = SettleResponse(
        success=True,
        payer="0xpayer",
        transaction="0xdeadbeef",
        network="stripe",
        credits_redeemed="5",
        remaining_balance="45",
    )
    md = build_settle_metadata(
        settlement=settlement,
        plan_ids=["plan-1"],
        agent_id="agent-xyz",
        duration_ms=42.0,
    )
    assert md == {
        "nvm.plan_ids": ["plan-1"],
        "nvm.agent_id": "agent-xyz",
        "nvm.settle.duration_ms": 42.0,
        "nvm.credits_redeemed": "5",
        "nvm.balance.after": "45",
        "nvm.tx_hash": "0xdeadbeef",
        "nvm.network": "stripe",
        "nvm.payer": "0xpayer",
    }


def test_build_settle_metadata_omits_empty_transaction_and_network():
    settlement = SettleResponse(success=True, transaction="", network="")
    md = build_settle_metadata(settlement=settlement, plan_ids=["plan-1"])
    assert "nvm.tx_hash" not in md
    assert "nvm.network" not in md


def test_build_settle_metadata_drops_none_credits():
    settlement = SettleResponse(success=True, transaction="0x1", network="stripe")
    md = build_settle_metadata(settlement=settlement, plan_ids=["plan-1"])
    assert "nvm.credits_redeemed" not in md
    assert "nvm.balance.after" not in md


# --------------------------------------------------------------------------- #
# active_run_tree + add_metadata
# --------------------------------------------------------------------------- #


def test_active_run_tree_returns_none_when_langsmith_unavailable():
    with patch.object(spans, "_LANGSMITH_AVAILABLE", False):
        assert active_run_tree() is None


def test_active_run_tree_returns_none_when_helper_returns_none():
    with patch.object(spans, "_get_current_run_tree", return_value=None):
        assert active_run_tree() is None


def test_active_run_tree_returns_run_tree_from_helper():
    fake_rt = MagicMock()
    with patch.object(spans, "_get_current_run_tree", return_value=fake_rt):
        assert active_run_tree() is fake_rt


def test_active_run_tree_swallows_helper_exception():
    with patch.object(
        spans, "_get_current_run_tree", side_effect=RuntimeError("no tracer")
    ):
        assert active_run_tree() is None


def test_add_metadata_no_op_when_run_tree_is_none():
    # Should not raise.
    add_metadata(None, {"k": "v"})


def test_add_metadata_no_op_when_metadata_empty():
    rt = MagicMock()
    add_metadata(rt, {})
    rt.add_metadata.assert_not_called()


def test_add_metadata_calls_run_tree_add_metadata():
    rt = MagicMock()
    add_metadata(rt, {"nvm.plan_id": "p1"})
    rt.add_metadata.assert_called_once_with({"nvm.plan_id": "p1"})


def test_add_metadata_swallows_run_tree_exception():
    rt = MagicMock()
    rt.add_metadata.side_effect = RuntimeError("boom")
    add_metadata(rt, {"k": "v"})  # must not raise


# --------------------------------------------------------------------------- #
# verify_span + settlement_span
# --------------------------------------------------------------------------- #


def test_verify_span_yields_none_when_no_active_run():
    with patch.object(spans, "_get_current_run_tree", return_value=None):
        with verify_span(plan_ids=["plan-1"]) as span:
            assert span is None


def test_verify_span_yields_span_from_ls_trace():
    fake_parent = MagicMock(name="parent_run_tree")
    fake_child = MagicMock(name="child_span")

    @contextmanager
    def fake_trace(**kwargs):
        # Echo the args so we can assert on them.
        fake_child.recorded_args = kwargs
        yield fake_child

    fake_ls = MagicMock()
    fake_ls.trace = fake_trace

    with (
        patch.object(spans, "_get_current_run_tree", return_value=fake_parent),
        patch.object(spans, "_ls", fake_ls),
    ):
        with verify_span(
            plan_ids=["plan-1"],
            scheme="nvm:erc4337",
            network="base-sepolia",
            agent_id="agent-x",
        ) as span:
            assert span is fake_child

    assert fake_child.recorded_args["name"] == "nvm:verify"
    assert fake_child.recorded_args["run_type"] == "tool"
    assert fake_child.recorded_args["inputs"] == {
        "plan_ids": ["plan-1"],
        "scheme": "nvm:erc4337",
        "network": "base-sepolia",
        "agent_id": "agent-x",
    }


def test_verify_span_yields_none_on_trace_exception():
    fake_ls = MagicMock()
    fake_ls.trace.side_effect = RuntimeError("trace failed")
    with (
        patch.object(spans, "_get_current_run_tree", return_value=MagicMock()),
        patch.object(spans, "_ls", fake_ls),
    ):
        with verify_span(plan_ids=["plan-1"]) as span:
            assert span is None


def test_verify_span_propagates_body_exception_to_caller():
    """Caller-raised exceptions must propagate out, not be swallowed.

    Regression test: an earlier implementation wrapped the `with _ls.trace(): yield`
    in a broad try/except that re-yielded None on any exception, which violates
    the @contextmanager protocol and surfaces as
    `RuntimeError("generator didn't stop after throw()")`. The user-visible
    symptom was that the very first `agent.invoke()` (the discovery probe in
    the langchain tutorial) crashed with that error instead of the expected
    PaymentRequiredError.
    """
    parent_rt = MagicMock(name="parent_run_tree")
    span_handle = MagicMock(name="span_handle")
    exit_calls: list[tuple] = []

    @contextmanager
    def fake_trace(**kwargs):
        try:
            yield span_handle
        except BaseException as e:
            exit_calls.append((type(e), str(e)))
            raise

    fake_ls = MagicMock()
    fake_ls.trace = fake_trace

    class Boom(Exception):
        pass

    with (
        patch.object(spans, "_get_current_run_tree", return_value=parent_rt),
        patch.object(spans, "_ls", fake_ls),
    ):
        with pytest.raises(Boom):
            with verify_span(plan_ids=["plan-1"]) as span:
                assert span is span_handle
                raise Boom("from body")

    # The inner _ls.trace context manager saw the exception (so LangSmith
    # marks the span as failed), and the exception propagated up to the caller.
    assert exit_calls == [(Boom, "from body")]


def test_settlement_span_propagates_body_exception_to_caller():
    """Mirror of test_verify_span_propagates_body_exception_to_caller for settle."""
    parent_rt = MagicMock(name="parent_run_tree")
    span_handle = MagicMock(name="span_handle")
    exit_calls: list[tuple] = []

    @contextmanager
    def fake_trace(**kwargs):
        try:
            yield span_handle
        except BaseException as e:
            exit_calls.append((type(e), str(e)))
            raise

    fake_ls = MagicMock()
    fake_ls.trace = fake_trace

    class Boom(Exception):
        pass

    with (
        patch.object(spans, "_get_current_run_tree", return_value=parent_rt),
        patch.object(spans, "_ls", fake_ls),
    ):
        with pytest.raises(Boom):
            with settlement_span(plan_ids=["plan-1"]) as span:
                assert span is span_handle
                raise Boom("from settle body")

    assert exit_calls == [(Boom, "from settle body")]


def test_settlement_span_yields_none_when_no_active_run():
    with patch.object(spans, "_get_current_run_tree", return_value=None):
        with settlement_span(plan_ids=["plan-1"]) as span:
            assert span is None


def test_settlement_span_yields_span_from_ls_trace():
    fake_parent = MagicMock(name="parent_run_tree")
    fake_child = MagicMock(name="child_span")

    @contextmanager
    def fake_trace(**kwargs):
        fake_child.recorded_args = kwargs
        yield fake_child

    fake_ls = MagicMock()
    fake_ls.trace = fake_trace

    with (
        patch.object(spans, "_get_current_run_tree", return_value=fake_parent),
        patch.object(spans, "_ls", fake_ls),
    ):
        with settlement_span(plan_ids=["plan-1"], agent_id="agent-x") as span:
            assert span is fake_child

    assert fake_child.recorded_args["name"] == "nvm:settlement"
    assert fake_child.recorded_args["inputs"] == {
        "plan_ids": ["plan-1"],
        "agent_id": "agent-x",
    }
