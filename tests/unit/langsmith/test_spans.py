"""Unit tests for the LangSmith span helpers."""

import logging
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from payments_py.langsmith import spans
from payments_py.langsmith.spans import (
    abbreviate_token,
    active_run_tree,
    add_metadata,
    build_settle_metadata,
    build_verify_metadata,
    redact_metadata_keys,
    settlement_span,
    verify_span,
)
from payments_py.x402.types import SettleResponse, VerifyResponse

# --------------------------------------------------------------------------- #
# abbreviate_token
# --------------------------------------------------------------------------- #


def test_abbreviate_token_long_token():
    token = "eyJ4NDAyVmVyc2lvbiI6Miwicm9sZXMiOlsicGF5ZXIiXX0.stubsig"
    abbreviated = abbreviate_token(token)
    assert abbreviated == "eyJ4NDAyVmVyc2lv…bsig"
    # Short enough to be a metadata field, far shorter than the original.
    assert len(abbreviated) < len(token) / 2
    # Original token is not a substring of the abbreviated form.
    assert token not in abbreviated


def test_abbreviate_token_short_token_returned_as_is():
    # A 20-char token has no abbreviation benefit and is returned unchanged.
    short = "a" * 20
    assert abbreviate_token(short) == short


def test_abbreviate_token_none_or_empty_returns_none():
    assert abbreviate_token(None) is None
    assert abbreviate_token("") is None


def test_abbreviate_token_short_token_emits_warning_but_returns_value(caplog):
    # A sub-21-char token is almost certainly not a real x402 JWT, so the
    # helper warns -- but the return contract is unchanged (value returned
    # verbatim, helper stays idempotent).
    short = "not-a-real-jwt"  # 14 chars
    with caplog.at_level(logging.WARNING, logger="payments_py.langsmith.spans"):
        result = abbreviate_token(short)
    assert result == short
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 1
    assert "shorter than expected" in warnings[0].getMessage()


def test_abbreviate_token_boundary_20_chars_warns(caplog):
    # 20 chars is the inclusive upper bound for the "short" branch.
    short = "a" * 20
    with caplog.at_level(logging.WARNING, logger="payments_py.langsmith.spans"):
        result = abbreviate_token(short)
    assert result == short
    assert any(r.levelno == logging.WARNING for r in caplog.records)


def test_abbreviate_token_jwt_length_does_not_warn(caplog):
    # A normal JWT-length token (>20 chars) is abbreviated silently.
    token = "eyJ4NDAyVmVyc2lvbiI6Miwicm9sZXMiOlsicGF5ZXIiXX0.stubsig"
    with caplog.at_level(logging.WARNING, logger="payments_py.langsmith.spans"):
        result = abbreviate_token(token)
    assert result == "eyJ4NDAyVmVyc2lv…bsig"
    assert not any(r.levelno == logging.WARNING for r in caplog.records)


def test_abbreviate_token_none_or_empty_does_not_warn(caplog):
    # No token at all is not a "wrong token" mistake -- stay silent.
    with caplog.at_level(logging.WARNING, logger="payments_py.langsmith.spans"):
        assert abbreviate_token(None) is None
        assert abbreviate_token("") is None
    assert not any(r.levelno == logging.WARNING for r in caplog.records)


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


def test_build_verify_metadata_includes_abbreviated_token():
    token = "eyJ4NDAyVmVyc2lvbiI6Miwicm9sZXMiOlsicGF5ZXIiXX0.stubsig"
    md = build_verify_metadata(plan_ids=["plan-1"], token=token)
    assert md["nvm.payment_token"] == "eyJ4NDAyVmVyc2lv…bsig"
    # Full token never appears.
    assert token not in md["nvm.payment_token"]


def test_build_verify_metadata_omits_payment_token_when_none():
    md = build_verify_metadata(plan_ids=["plan-1"], token=None)
    assert "nvm.payment_token" not in md


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


def test_build_settle_metadata_includes_abbreviated_token():
    settlement = SettleResponse(success=True, transaction="0x1", network="stripe")
    token = "eyJ4NDAyVmVyc2lvbiI6Miwicm9sZXMiOlsicGF5ZXIiXX0.stubsig"
    md = build_settle_metadata(settlement=settlement, plan_ids=["plan-1"], token=token)
    assert md["nvm.payment_token"] == "eyJ4NDAyVmVyc2lv…bsig"
    assert token not in md["nvm.payment_token"]


def test_build_settle_metadata_omits_payment_token_when_none():
    settlement = SettleResponse(success=True, transaction="0x1", network="stripe")
    md = build_settle_metadata(settlement=settlement, plan_ids=["plan-1"], token=None)
    assert "nvm.payment_token" not in md


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
# redact_metadata_keys
# --------------------------------------------------------------------------- #


def test_redact_metadata_keys_removes_keys_in_place():
    metadata = {"payment_token": "eyJfull", "other": "keep", "nvm.payer": "0x"}
    rt = type("FakeRT", (), {"extra": {"metadata": metadata}})()
    redact_metadata_keys(rt, "payment_token")
    assert "payment_token" not in metadata
    assert metadata == {"other": "keep", "nvm.payer": "0x"}


def test_redact_metadata_keys_handles_multiple_keys():
    metadata = {"a": 1, "b": 2, "c": 3}
    rt = type("FakeRT", (), {"extra": {"metadata": metadata}})()
    redact_metadata_keys(rt, "a", "c", "missing")
    assert metadata == {"b": 2}


def test_redact_metadata_keys_no_op_when_run_tree_is_none():
    redact_metadata_keys(None, "anything")  # must not raise


def test_redact_metadata_keys_no_op_when_no_keys():
    metadata = {"payment_token": "eyJfull"}
    rt = type("FakeRT", (), {"extra": {"metadata": metadata}})()
    redact_metadata_keys(rt)
    assert metadata == {"payment_token": "eyJfull"}


def test_redact_metadata_keys_swallows_exceptions():
    # extra is not a dict -- the helper should silently handle it.
    rt = MagicMock()
    rt.extra = None
    redact_metadata_keys(rt, "payment_token")  # must not raise


def test_redact_metadata_keys_handles_missing_metadata_subdict():
    rt = type("FakeRT", (), {"extra": {}})()
    redact_metadata_keys(rt, "payment_token")  # must not raise


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


def test_settlement_span_yields_none_on_trace_exception():
    """Parity test for verify_span. Both currently delegate to _open_nvm_span;
    this pins the contract so a future split-out can't regress only one path."""
    fake_ls = MagicMock()
    fake_ls.trace.side_effect = RuntimeError("trace failed")
    with (
        patch.object(spans, "_get_current_run_tree", return_value=MagicMock()),
        patch.object(spans, "_ls", fake_ls),
    ):
        with settlement_span(plan_ids=["plan-1"]) as span:
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
