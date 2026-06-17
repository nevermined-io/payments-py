"""Unit tests for the in-band x402 v2 A2A helpers and handler integration."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import Task, TaskState, TaskStatus, TaskStatusUpdateEvent

from payments_py.a2a.inband import (
    extract_inband_token,
    get_inband_payment_payload,
)
from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import HttpRequestContext
from payments_py.x402.a2a import x402Metadata
from payments_py.x402.token import decode_access_token
from payments_py.x402.types import SettleResponse


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


def _payload() -> dict:
    return {
        "x402Version": 2,
        "accepted": {"scheme": "nvm:erc4337", "planId": "plan-1"},
        "payload": {"authorization": {"from": "0xSubscriber"}},
    }


def _message_with_payload() -> SimpleNamespace:
    return SimpleNamespace(
        metadata={
            x402Metadata.STATUS_KEY: "payment-submitted",
            x402Metadata.PAYLOAD_KEY: _payload(),
        }
    )


# ---------------------------------------------------------------------------
# Helper extraction
# ---------------------------------------------------------------------------
def test_get_inband_payment_payload_from_dict_message():
    msg = {
        "metadata": {
            x402Metadata.STATUS_KEY: "payment-submitted",
            x402Metadata.PAYLOAD_KEY: _payload(),
        }
    }
    assert get_inband_payment_payload(msg) == _payload()


def test_get_inband_payment_payload_absent_returns_none():
    assert get_inband_payment_payload(SimpleNamespace(metadata={})) is None
    assert get_inband_payment_payload(SimpleNamespace(metadata=None)) is None
    assert get_inband_payment_payload(None) is None


# ---------------------------------------------------------------------------
# Token plumbing: in-band payload <-> base64 access token round-trip
# ---------------------------------------------------------------------------
def test_extract_inband_token_roundtrips_through_decode():
    """The re-encoded token must decode back to the original payload object.

    This is the core reconciliation: the facilitator consumes the base64
    token, while the in-band transport carries the decoded payload object.
    """
    msg = _message_with_payload()
    token = extract_inband_token(msg)
    assert isinstance(token, str) and token

    decoded = decode_access_token(token)
    assert decoded == _payload()
    # The subscriber address the handler reads survives the round-trip.
    assert decoded["payload"]["authorization"]["from"] == "0xSubscriber"


def test_extract_inband_token_none_when_no_payload():
    assert extract_inband_token(SimpleNamespace(metadata={})) is None


# ---------------------------------------------------------------------------
# Handler helpers
# ---------------------------------------------------------------------------
def _handler() -> PaymentsRequestHandler:
    return PaymentsRequestHandler(
        agent_card={
            "capabilities": {
                "extensions": [
                    {
                        "uri": "urn:nevermined:payment",
                        "params": {"agentId": "agent-1", "planId": "plan-1"},
                    }
                ]
            }
        },
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=SimpleNamespace(environment_name="staging_sandbox"),
    )


def test_build_payment_required_task_shape():
    handler = _handler()
    task = handler._build_payment_required_task(
        task_id=None,
        context_id="ctx-1",
        agent_id="agent-1",
        ext_params={"planId": "plan-1"},
    )
    assert task.status.state == TaskState.input_required
    meta = task.status.message.metadata
    assert meta[x402Metadata.STATUS_KEY] == "payment-required"
    pr = meta[x402Metadata.REQUIRED_KEY]
    assert pr["x402Version"] == 2
    assert pr["accepts"][0]["planId"] == "plan-1"
    assert pr["accepts"][0]["extra"]["agentId"] == "agent-1"


def test_build_payment_failed_task_shape():
    handler = _handler()
    task = handler._build_payment_failed_task(
        task_id="tid",
        context_id="ctx",
        code="PAYMENT_VERIFICATION_FAILED",
        reason="bad signature",
    )
    assert task.status.state == TaskState.failed
    meta = task.status.message.metadata
    assert meta[x402Metadata.STATUS_KEY] == "payment-failed"
    assert meta[x402Metadata.ERROR_KEY]["code"] == "PAYMENT_VERIFICATION_FAILED"


def test_apply_inband_settlement_success_stamps_receipt():
    handler = _handler()
    task = Task(
        id="tid",
        context_id="ctx",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )
    handler._settle_receipt_by_task["tid"] = SettleResponse(
        success=True, transaction="0xfeed", network="eip155:84532"
    )
    handler._apply_inband_settlement(task, "tid")

    meta = task.status.message.metadata
    assert meta[x402Metadata.STATUS_KEY] == "payment-completed"
    assert meta[x402Metadata.RECEIPTS_KEY]["transaction"] == "0xfeed"
    # Receipt consumed (popped) so a later call is a no-op.
    assert "tid" not in handler._settle_receipt_by_task


def test_apply_inband_settlement_failure_forces_failed_and_drops_content():
    handler = _handler()
    task = Task(
        id="tid",
        context_id="ctx",
        status=TaskStatus(state=TaskState.completed),
        history=[],
        artifacts=[{"artifactId": "a1", "name": "secret", "parts": []}],
    )
    handler._settle_receipt_by_task["tid"] = SettleResponse(
        success=False, error_reason="insufficient funds"
    )
    handler._apply_inband_settlement(task, "tid")

    assert task.status.state == TaskState.failed
    assert task.artifacts is None  # paid content suppressed
    meta = task.status.message.metadata
    assert meta[x402Metadata.STATUS_KEY] == "payment-failed"


def test_apply_inband_settlement_noop_without_receipt():
    handler = _handler()
    task = Task(
        id="tid",
        context_id="ctx",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )
    # No receipt recorded (free / no-credit call): nothing is stamped.
    handler._apply_inband_settlement(task, "tid")
    assert task.status.state == TaskState.completed
    assert task.status.message is None


@pytest.mark.asyncio
async def test_finalization_does_not_store_receipt_on_legacy_header_path():
    """The legacy header path (inband=False) must not retain settle receipts.

    Locks in the fix that prevents ``_settle_receipt_by_task`` from growing
    unbounded for header-path callers that never consume the receipt.
    """
    settle_mock = Mock(return_value=SettleResponse(success=True, transaction="0xabc"))
    handler = PaymentsRequestHandler(
        agent_card={
            "capabilities": {
                "extensions": [
                    {
                        "uri": "urn:nevermined:payment",
                        "params": {"agentId": "agent-1", "planId": "plan-1"},
                    }
                ]
            }
        },
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=SimpleNamespace(
            facilitator=SimpleNamespace(settle_permissions=settle_mock)
        ),
    )
    event = TaskStatusUpdateEvent(
        task_id="tid-legacy",
        context_id="ctx",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 2},
    )
    ctx = HttpRequestContext(
        bearer_token="HEADER",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan-1"},
        inband=False,
    )
    await handler._handle_task_finalization_from_event(event, ctx)

    settle_mock.assert_called_once()
    # Header path settles but stores no receipt (nothing would ever pop it).
    assert "tid-legacy" not in handler._settle_receipt_by_task


def test_coerce_settle_response_from_duck_typed_object():
    obj = SimpleNamespace(
        success=True, transaction="0xabc", network="eip155:84532", payer="0xp"
    )
    coerced = PaymentsRequestHandler._coerce_settle_response(obj)
    assert isinstance(coerced, SettleResponse)
    assert coerced.transaction == "0xabc"
    # by_alias serialization carries the x402 receipt fields.
    dumped = coerced.model_dump(by_alias=True)
    assert dumped["success"] is True


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])
