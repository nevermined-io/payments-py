"""Tests for batch/margin redemption config on PaymentsRequestHandler.

Faithful port of the TS `getRedemptionConfig` + the `useBatch` settlement
deferral (margin surfaced but inert). See issue #308 (A2A parity item 4).
"""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import Task, TaskStatus, TaskState, TaskStatusUpdateEvent
from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import HttpRequestContext
from payments_py.x402.a2a import X402A2AUtils, PaymentStatus
from tests.x402_responses import make_settle_response


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


def _card(redemption_config=None, with_ext=True):
    params = {"agentId": "agent-1", "planId": "plan-123"}
    if redemption_config is not None:
        params["redemptionConfig"] = redemption_config
    if not with_ext:
        return {"capabilities": {"extensions": []}}
    return {
        "capabilities": {
            "extensions": [{"uri": "urn:nevermined:payment", "params": params}]
        }
    }


def _handler(card=None, settle_mock=None, **kwargs) -> PaymentsRequestHandler:
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(
            settle_permissions=settle_mock
            or (lambda **k: make_settle_response(transaction="0xabc")),
        ),
    )
    return PaymentsRequestHandler(
        agent_card=card if card is not None else _card(),
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
        **kwargs,
    )


def _ctx(inband=False) -> HttpRequestContext:
    return HttpRequestContext(
        bearer_token="BEARER",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan-123", "subscriber_address": "0x1"},
        inband=inband,
    )


def _event() -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-1",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5},
    )


# --- get_redemption_config -------------------------------------------------


def test_redemption_config_defaults_off():
    cfg = _handler(card=_card(with_ext=False)).get_redemption_config()
    assert cfg == {"use_batch": False, "use_margin": False, "margin_percent": None}


def test_redemption_config_handler_default_batch():
    cfg = _handler(default_batch=True).get_redemption_config()
    assert cfg["use_batch"] is True


def test_redemption_config_card_overrides_default_on():
    cfg = _handler(card=_card({"useBatch": True})).get_redemption_config()
    assert cfg["use_batch"] is True


def test_redemption_config_card_false_overrides_handler_true():
    # The `is None` fallback, not `or`: an explicit False must win over a True
    # handler default. This is the regression the whole feature hinges on.
    cfg = _handler(
        card=_card({"useBatch": False}), default_batch=True
    ).get_redemption_config()
    assert cfg["use_batch"] is False


def test_redemption_config_margin_surfaced():
    cfg = _handler(
        card=_card({"useMargin": True, "marginPercent": 15}),
        default_margin_percent=5,
    ).get_redemption_config()
    assert cfg["use_margin"] is True
    assert cfg["margin_percent"] == 15  # card wins over handler default of 5


def test_redemption_config_margin_percent_from_handler_default():
    cfg = _handler(default_margin_percent=7).get_redemption_config()
    assert cfg["margin_percent"] == 7


def test_handler_options():
    opts = _handler(default_batch=True, default_margin_percent=3).get_handler_options()
    assert opts == {
        "async_execution": False,
        "default_batch": True,
        "default_margin_percent": 3,
    }


# --- settlement deferral ---------------------------------------------------


@pytest.mark.asyncio()
async def test_batch_defers_settlement():
    settle = Mock(return_value=make_settle_response(transaction="0xabc"))
    handler = _handler(card=_card({"useBatch": True}), settle_mock=settle)
    await handler._handle_task_finalization_from_event(_event(), _ctx())
    settle.assert_not_called()


@pytest.mark.asyncio()
async def test_non_batch_still_settles():
    settle = Mock(return_value=make_settle_response(transaction="0xabc"))
    handler = _handler(card=_card({"useBatch": False}), settle_mock=settle)
    await handler._handle_task_finalization_from_event(_event(), _ctx())
    settle.assert_called_once()


@pytest.mark.asyncio()
async def test_inband_batch_stamps_deferred_marker():
    settle = Mock(return_value=make_settle_response(transaction="0xabc"))
    handler = _handler(card=_card({"useBatch": True}), settle_mock=settle)

    await handler._handle_task_finalization_from_event(_event(), _ctx(inband=True))
    assert "tid" in handler._settlement_deferred_by_task
    settle.assert_not_called()

    task = Task(
        id="tid",
        context_id="ctx-1",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )
    handler._apply_inband_settlement(task, "tid")

    meta = task.status.message.metadata
    assert meta[X402A2AUtils.STATUS_KEY] == PaymentStatus.PAYMENT_VERIFIED
    assert meta[X402A2AUtils.SETTLEMENT_KEY] == "deferred"
    # consumed
    assert "tid" not in handler._settlement_deferred_by_task


@pytest.mark.asyncio()
async def test_streaming_batch_defers_settlement():
    settle = Mock(return_value=make_settle_response(transaction="0xabc"))
    handler = _handler(card=_card({"useBatch": True}), settle_mock=settle)
    handler.set_http_ctx_for_task("tid", _ctx())

    async def fake_stream(*_a, **_k):
        yield _event()

    with patch(
        "payments_py.a2a.payments_request_handler."
        "DefaultRequestHandler.on_message_send_stream",
        new=fake_stream,
    ):
        events = [
            ev
            async for ev in handler.on_message_send_stream(
                SimpleNamespace(
                    message=SimpleNamespace(task_id="tid", message_id="mid")
                ),
                None,
            )
        ]

    assert len(events) == 1
    settle.assert_not_called()


def test_record_payment_deferred_marks_verified_plus_deferred():
    utils = X402A2AUtils()
    task = Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )
    utils.record_payment_deferred(task)
    meta = task.status.message.metadata
    assert meta[X402A2AUtils.STATUS_KEY] == PaymentStatus.PAYMENT_VERIFIED
    assert meta[X402A2AUtils.SETTLEMENT_KEY] == "deferred"
