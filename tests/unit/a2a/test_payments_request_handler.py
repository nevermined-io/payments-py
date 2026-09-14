"""Unit tests for PaymentsRequestHandler."""

import asyncio
import base64
import contextlib
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import logging

import pytest

from a2a.server.events.event_consumer import EventConsumer
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.result_aggregator import ResultAggregator
from a2a.server.tasks.task_manager import TaskManager
from a2a.types import (
    Task,
    TaskStatus,
    TaskState,
    TaskStatusUpdateEvent,
)
from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import HttpRequestContext
from payments_py.common.payments_error import PaymentsError
from tests.x402_responses import make_settle_response, make_verify_response


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


@pytest.mark.asyncio()  # noqa: D401
async def test_on_message_send_validates_and_calls_parent(monkeypatch):  # noqa: D401
    """Test that on_message_send validates request and processes events."""
    # Mock settle method - must be synchronous since it's called via run_in_executor
    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    # Create completed task
    completed_task = Task(
        id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )

    # Mock _setup_message_execution to return our components
    async def mock_setup(*args, **kwargs):
        task_store = InMemoryTaskStore()
        # Add the task to the store so TaskManager can find it
        await task_store.save(completed_task)

        task_manager = TaskManager("tid", "ctx-123", task_store, None)
        queue = EventQueue()
        result_aggregator = ResultAggregator(task_manager)
        producer_task = AsyncMock()
        producer_task.done.return_value = True

        return task_manager, "tid", queue, result_aggregator, producer_task

    # Mock _consume_and_burn_credits to return the task
    async def mock_consume_credits(*args, **kwargs):
        # (result, interrupted_or_non_blocking, background_task)
        return (completed_task, False, None)

    with (
        patch.object(
            PaymentsRequestHandler, "_setup_message_execution", side_effect=mock_setup
        ),
        patch.object(
            PaymentsRequestHandler,
            "_consume_and_burn_credits",
            side_effect=mock_consume_credits,
        ),
        patch.object(
            PaymentsRequestHandler, "_send_push_notification_if_needed", new=AsyncMock()
        ),
        patch.object(
            PaymentsRequestHandler,
            "get_agent_card",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    capabilities=SimpleNamespace(
                        extensions=[
                            SimpleNamespace(
                                uri="urn:nevermined:payment",
                                params=SimpleNamespace(agentId="test-agent"),
                            )
                        ]
                    )
                )
            ),
        ),
    ):
        handler = PaymentsRequestHandler(
            agent_card={},
            task_store=InMemoryTaskStore(),
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
        )

        # Attach HTTP context
        ctx = HttpRequestContext(
            bearer_token="BEARER",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"plan_id": "plan123", "subscriber_address": "0x123"},
        )
        handler.set_http_ctx_for_task("tid", ctx)

        # Call under test
        result = await handler.on_message_send(
            SimpleNamespace(
                message=SimpleNamespace(
                    task_id="tid", message_id="mid", context_id="ctx-123"
                )
            ),
            None,
        )

    # Should return the task
    assert result is completed_task
    # Since we mocked _process_events_with_finalization, credit burning logic
    # wasn't called
    assert settle_mock.call_count == 0


@pytest.mark.asyncio()  # noqa: D401
async def test_on_message_send_burns_credits_from_events():  # noqa: D401
    """Test that on_message_send burns credits when processing TaskStatusUpdateEvent with creditsUsed."""
    # Mock settle method - must be synchronous since it's called via run_in_executor
    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    # Create completed task
    completed_task = Task(
        id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )

    # Mock _setup_message_execution to return our components
    async def mock_setup(*args, **kwargs):
        task_store = InMemoryTaskStore()
        await task_store.save(completed_task)

        task_manager = TaskManager("tid", "ctx-123", task_store, None)
        queue = EventQueue()
        result_aggregator = ResultAggregator(task_manager)
        producer_task = AsyncMock()
        producer_task.done.return_value = True

        return task_manager, "tid", queue, result_aggregator, producer_task

    # Mock _consume_and_burn_credits to simulate credit burning
    async def mock_consume_credits(
        result_aggregator, consumer, http_ctx, blocking=True
    ):
        from payments_py.x402.helpers import build_payment_required

        # Simulate credit burning by calling settle_permissions with new x402 API
        credits_used = 3
        try:
            import asyncio

            payment_required = build_payment_required(
                plan_id=http_ctx.validation["plan_id"],
                endpoint=http_ctx.url_requested,
                http_verb=http_ctx.http_method_requested,
            )

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: dummy_payments.facilitator.settle_permissions(
                    payment_required=payment_required,
                    x402_access_token=http_ctx.bearer_token,
                    max_amount=str(credits_used),
                ),
            )
        except Exception:
            pass  # Swallow errors like the real implementation

        # (result, interrupted_or_non_blocking, background_task)
        return (completed_task, False, None)

    with (
        patch.object(
            PaymentsRequestHandler, "_setup_message_execution", side_effect=mock_setup
        ),
        patch.object(
            PaymentsRequestHandler,
            "_consume_and_burn_credits",
            side_effect=mock_consume_credits,
        ),
        patch.object(
            PaymentsRequestHandler, "_send_push_notification_if_needed", new=AsyncMock()
        ),
        patch.object(
            PaymentsRequestHandler,
            "get_agent_card",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    capabilities=SimpleNamespace(
                        extensions=[
                            SimpleNamespace(
                                uri="urn:nevermined:payment",
                                params=SimpleNamespace(agentId="test-agent"),
                            )
                        ]
                    )
                )
            ),
        ),
    ):
        handler = PaymentsRequestHandler(
            agent_card={},
            task_store=InMemoryTaskStore(),
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
        )

        # Attach HTTP context
        ctx = HttpRequestContext(
            bearer_token="BEARER",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"plan_id": "plan123", "subscriber_address": "0x123"},
        )
        handler.set_http_ctx_for_task("tid", ctx)

        # Call under test
        result = await handler.on_message_send(
            SimpleNamespace(
                message=SimpleNamespace(
                    task_id="tid", message_id="mid", context_id="ctx-123"
                )
            ),
            None,
        )

    assert result is completed_task
    # Should have called settle_permissions with x402 API
    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["x402_access_token"] == "BEARER"
    assert call_kwargs["max_amount"] == "3"
    assert call_kwargs["payment_required"] is not None


@pytest.mark.asyncio()  # noqa: D401
async def test_on_message_send_fails_when_agent_id_missing():  # noqa: D401
    """Test that on_message_send fails when agentId is not found in agent card."""
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=Mock()),
    )

    # Mock agent card without payment extension
    agent_card_without_payment = SimpleNamespace(
        capabilities=SimpleNamespace(extensions=[])
    )

    with patch.object(
        PaymentsRequestHandler,
        "get_agent_card",
        new=AsyncMock(return_value=agent_card_without_payment),
    ):
        handler = PaymentsRequestHandler(
            agent_card={},
            task_store=InMemoryTaskStore(),
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
        )

        # Attach HTTP context
        ctx = HttpRequestContext(
            bearer_token="BEARER",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"plan_id": "plan123", "subscriber_address": "0x123"},
        )
        handler.set_http_ctx_for_task("tid", ctx)

        # Call under test - should raise PaymentsError
        with pytest.raises(PaymentsError) as exc_info:
            await handler.on_message_send(
                SimpleNamespace(
                    message=SimpleNamespace(
                        task_id="tid", message_id="mid", context_id="ctx-123"
                    )
                ),
                None,
            )

        assert "Agent ID not found in payment extension" in str(exc_info.value)


@pytest.mark.asyncio()  # noqa: D401
async def test_on_message_send_handles_missing_http_context():  # noqa: D401
    """Test that on_message_send fails when HTTP context is missing."""
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=Mock()),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    # Call under test without setting HTTP context - should raise PaymentsError
    with pytest.raises(PaymentsError) as exc_info:
        await handler.on_message_send(
            SimpleNamespace(
                message=SimpleNamespace(
                    task_id="tid", message_id="mid", context_id="ctx-123"
                )
            ),
            None,
        )

    assert "HTTP context missing for request" in str(exc_info.value)


@pytest.mark.asyncio()  # noqa: D401
async def test_on_message_send_generates_task_id_when_missing():  # noqa: D401
    """Test that on_message_send generates taskId and migrates HTTP context when taskId is missing."""
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=Mock()),
    )

    completed_task = Task(
        id="generated-task-id",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )

    # Mock setup and consume methods
    async def mock_setup(*args, **kwargs):
        task_store = InMemoryTaskStore()
        await task_store.save(completed_task)

        task_manager = TaskManager("generated-task-id", "ctx-123", task_store, None)
        queue = EventQueue()
        result_aggregator = ResultAggregator(task_manager)
        producer_task = AsyncMock()
        producer_task.done.return_value = True

        return (
            task_manager,
            "generated-task-id",
            queue,
            result_aggregator,
            producer_task,
        )

    async def mock_consume_credits(*args, **kwargs):
        return (completed_task, False, None)

    with (
        patch.object(
            PaymentsRequestHandler, "_setup_message_execution", side_effect=mock_setup
        ),
        patch.object(
            PaymentsRequestHandler,
            "_consume_and_burn_credits",
            side_effect=mock_consume_credits,
        ),
        patch.object(
            PaymentsRequestHandler, "_send_push_notification_if_needed", new=AsyncMock()
        ),
        patch.object(
            PaymentsRequestHandler,
            "get_agent_card",
            new=AsyncMock(
                return_value=SimpleNamespace(
                    capabilities=SimpleNamespace(
                        extensions=[
                            SimpleNamespace(
                                uri="urn:nevermined:payment",
                                params=SimpleNamespace(agentId="test-agent"),
                            )
                        ]
                    )
                )
            ),
        ),
        patch("uuid.uuid4", return_value="generated-task-id"),
    ):
        handler = PaymentsRequestHandler(
            agent_card={},
            task_store=InMemoryTaskStore(),
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
        )

        # Attach HTTP context for message (not task)
        ctx = HttpRequestContext(
            bearer_token="BEARER",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"plan_id": "plan123", "subscriber_address": "0x123"},
        )
        handler.set_http_ctx_for_message("mid", ctx)

        # Call under test with message that has no taskId
        result = await handler.on_message_send(
            SimpleNamespace(
                message=SimpleNamespace(
                    task_id=None, message_id="mid", context_id="ctx-123"  # No taskId
                )
            ),
            None,
        )

        assert result is completed_task
        # Verify taskId was generated and set on the message
        # Note: In real implementation, the message object would be modified


@pytest.mark.asyncio()  # noqa: D401
async def test_handle_task_finalization_from_event_burns_credits():  # noqa: D401
    """Test that _handle_task_finalization_from_event burns credits correctly."""

    # Mock settle method
    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    # Create event with creditsUsed
    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5},
    )

    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
    )

    # Call under test
    await handler._handle_task_finalization_from_event(event, ctx)

    # Should have called settle_permissions with x402 API
    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["x402_access_token"] == "BEARER_TOKEN"
    assert call_kwargs["max_amount"] == "5"
    assert call_kwargs["payment_required"] is not None
    assert (
        call_kwargs["agent_request_id"] is None
    )  # No agent_request_id in validation or metadata


@pytest.mark.asyncio()  # noqa: D401
async def test_handle_task_finalization_passes_agent_request_id_from_validation():  # noqa: D401
    """Test that _handle_task_finalization_from_event passes agent_request_id from validation context."""

    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5},
    )

    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={
            "plan_id": "plan123",
            "subscriber_address": "0x123",
            "agent_request_id": "req-abc-123",
        },
    )

    await handler._handle_task_finalization_from_event(event, ctx)

    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["agent_request_id"] == "req-abc-123"


@pytest.mark.asyncio()  # noqa: D401
async def test_handle_task_finalization_passes_agent_request_id_from_event_metadata():  # noqa: D401
    """Test that _handle_task_finalization_from_event falls back to agentRequestId from event metadata."""

    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5, "agentRequestId": "req-from-event"},
    )

    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
    )

    await handler._handle_task_finalization_from_event(event, ctx)

    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["agent_request_id"] == "req-from-event"


@pytest.mark.asyncio()  # noqa: D401
async def test_handle_task_finalization_from_event_no_credits():  # noqa: D401
    """Test that _handle_task_finalization_from_event does nothing when no creditsUsed."""

    # Mock settle method
    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    # Create event without creditsUsed
    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={},  # No creditsUsed
    )

    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
    )

    # Call under test
    await handler._handle_task_finalization_from_event(event, ctx)

    # Should NOT have called settle_permissions
    settle_mock.assert_not_called()


@pytest.mark.asyncio()  # noqa: D401
async def test_handle_task_finalization_from_event_no_metadata():  # noqa: D401
    """Test that _handle_task_finalization_from_event does nothing when no metadata."""

    # Mock settle method
    settle_mock = Mock(return_value={"success": True, "txHash": "0xabc"})
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    # Create event without metadata
    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata=None,  # No metadata
    )

    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
    )

    # Call under test
    await handler._handle_task_finalization_from_event(event, ctx)

    # Should NOT have called settle_permissions
    settle_mock.assert_not_called()


@pytest.mark.asyncio()  # noqa: D401
async def test_handle_task_finalization_swallows_errors():  # noqa: D401
    """Test that _handle_task_finalization_from_event swallows settle errors."""

    # Mock settle method to raise an exception
    settle_mock = Mock(side_effect=Exception("Settle failed"))
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    # Create event with creditsUsed
    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5},
    )

    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
    )

    # Call under test - should not raise exception
    await handler._handle_task_finalization_from_event(event, ctx)

    # Should have attempted to call settle_permissions with x402 API
    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["x402_access_token"] == "BEARER_TOKEN"
    assert call_kwargs["max_amount"] == "5"
    assert call_kwargs["payment_required"] is not None


@pytest.mark.asyncio()  # noqa: D401
async def test_validate_request_captures_agent_request_attributes():  # noqa: D401
    """Test that validate_request sets latest_agent_request and latest_agent_request_id."""

    # Mock verify_permissions result
    verify_result = make_verify_response(
        agent_request={"agent_request_id": "req-xyz", "some": "data"},
        agent_request_id="req-xyz",
    )
    verify_mock = Mock(return_value=verify_result)
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(verify_permissions=verify_mock),
    )

    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {"planId": "plan-abc", "agentId": "agent-1"},
                }
            ]
        }
    }

    handler = PaymentsRequestHandler(
        agent_card=agent_card,
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )

    # Craft a minimal valid x402 token (base64-encoded JSON)
    token_payload = {
        "payload": {"authorization": {"from": "0xSubscriber"}},
        "accepted": {"scheme": "nvm:erc4337"},
    }
    bearer_token = base64.b64encode(json.dumps(token_payload).encode()).decode()

    result = await handler.validate_request(
        agent_id="agent-1",
        bearer_token=bearer_token,
        url_requested="https://example.com/ask",
        http_method_requested="POST",
    )

    # Verify attributes are set on the handler
    assert handler.latest_agent_request == {
        "agent_request_id": "req-xyz",
        "some": "data",
    }
    assert handler.latest_agent_request_id == "req-xyz"

    # Verify the return dict includes agent_request_id and agent_request
    assert result["agent_request_id"] == "req-xyz"
    assert result["agent_request"] == {"agent_request_id": "req-xyz", "some": "data"}


# ---------------------------------------------------------------------------
# A spent v3 token must be distinguishable from a backend blip (BCK.X402.0059)
# ---------------------------------------------------------------------------


def _spent_token_handler(inband: bool = True):
    """Handler whose settle always reports the token as already spent."""
    from payments_py.common.payments_error import PaymentsError

    settle_mock = Mock(
        side_effect=PaymentsError("access token already used", "BCK.X402.0059")
    )
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )
    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )
    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5},
    )
    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
        inband=inband,
    )
    return handler, event, ctx, settle_mock


@pytest.mark.asyncio()  # noqa: D401
async def test_spent_token_is_logged_as_an_error_not_a_warning(caplog):  # noqa: D401
    """A replayed token and a backend outage must not look the same to a
    seller: one is someone replaying tokens against them, the other is our own
    infrastructure. Note the error arrives as a plain ``PaymentsError`` carrying
    the wire code — the case `is_access_token_already_used` exists for, and the
    one an `isinstance` check would miss."""
    handler, event, ctx, _ = _spent_token_handler()

    with caplog.at_level(logging.ERROR):
        await handler._handle_task_finalization_from_event(event, ctx)

    assert any(
        "BCK.X402.0059" in record.getMessage() and record.levelno == logging.ERROR
        for record in caplog.records
    )


@pytest.mark.asyncio()  # noqa: D401
async def test_spent_token_records_a_failed_receipt_for_the_inband_path():  # noqa: D401
    """The failed receipt is what makes the in-band path emit payment-failed
    rather than reporting a paid task, so the spent-token branch must not skip
    it — an earlier attempt at this fix used a separate `except` block and did."""
    handler, event, ctx, _ = _spent_token_handler(inband=True)

    await handler._handle_task_finalization_from_event(event, ctx)

    receipt = handler._settle_receipt_by_task["tid"]
    assert receipt.success is False
    assert "BCK.X402.0059" in (receipt.error_reason or "")


@pytest.mark.asyncio()  # noqa: D401
async def test_transient_settle_failure_is_still_a_warning(caplog):  # noqa: D401
    """The other side of the split: an ordinary failure keeps its old
    treatment, so the ERROR above stays meaningful."""
    settle_mock = Mock(side_effect=RuntimeError("backend down"))
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )
    handler = PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )
    event = TaskStatusUpdateEvent(
        task_id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        final=True,
        metadata={"creditsUsed": 5},
    )
    ctx = HttpRequestContext(
        bearer_token="BEARER_TOKEN",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
        inband=True,
    )

    with caplog.at_level(logging.DEBUG):
        await handler._handle_task_finalization_from_event(event, ctx)

    assert not any(record.levelno == logging.ERROR for record in caplog.records)
    assert any(record.levelno == logging.WARNING for record in caplog.records)


@pytest.mark.asyncio()  # noqa: D401
async def test_streamed_spent_token_records_a_failed_receipt(caplog):  # noqa: D401
    """The streaming path cannot retract the events, but it must still record
    the failure so the in-band path emits payment-failed rather than reporting
    a paid task — and log it as a replay rather than an outage."""
    from payments_py.common.payments_error import PaymentsError

    handler, _, _, _ = _spent_token_handler()

    with caplog.at_level(logging.ERROR):
        handler._record_settle_failure(
            PaymentsError("access token already used", "BCK.X402.0059"),
            task_id="tid",
            inband=True,
            credits_used=5,
            streamed=True,
        )

    receipt = handler._settle_receipt_by_task["tid"]
    assert receipt.success is False
    assert "BCK.X402.0059" in (receipt.error_reason or "")
    assert any(
        "after the stream was delivered" in record.getMessage()
        and record.levelno == logging.ERROR
        for record in caplog.records
    )


@contextlib.contextmanager
def _mocked_send(completed_task: Task, background_task):
    """Patch context for `on_message_send` that returns `background_task`.

    Mirrors the setup of the tests above, but lets the caller decide what
    `_consume_and_burn_credits` hands back as the SDK's third tuple element.
    """

    async def mock_setup(*args, **kwargs):
        task_store = InMemoryTaskStore()
        await task_store.save(completed_task)
        task_manager = TaskManager("tid", "ctx-123", task_store, None)
        queue = EventQueue()
        result_aggregator = ResultAggregator(task_manager)
        # Mock, not AsyncMock: on an unspecced AsyncMock `done()` returns an
        # un-awaited coroutine, which is truthy, so `_cleanup_producer` would
        # skip its cancel branch by accident rather than by configuration.
        producer_task = Mock(spec=asyncio.Task)
        producer_task.done.return_value = True
        return task_manager, "tid", queue, result_aggregator, producer_task

    async def mock_consume_credits(*args, **kwargs):
        # interrupted=True is what makes the SDK spawn a continuation at all.
        return (completed_task, True, background_task)

    with contextlib.ExitStack() as stack:
        for patcher in (
            patch.object(
                PaymentsRequestHandler,
                "_setup_message_execution",
                side_effect=mock_setup,
            ),
            patch.object(
                PaymentsRequestHandler,
                "_consume_and_burn_credits",
                side_effect=mock_consume_credits,
            ),
            patch.object(
                PaymentsRequestHandler,
                "_send_push_notification_if_needed",
                new=AsyncMock(),
            ),
            patch.object(
                PaymentsRequestHandler,
                "get_agent_card",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        capabilities=SimpleNamespace(
                            extensions=[
                                SimpleNamespace(
                                    uri="urn:nevermined:payment",
                                    params=SimpleNamespace(agentId="test-agent"),
                                )
                            ]
                        )
                    )
                ),
            ),
        ):
            stack.enter_context(patcher)
        yield


def _build_handler(settle_mock=None) -> PaymentsRequestHandler:
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(
            settle_permissions=settle_mock
            or (lambda **kwargs: make_settle_response(transaction="0xabc")),
        ),
    )
    return PaymentsRequestHandler(
        agent_card={},
        task_store=InMemoryTaskStore(),
        agent_executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
    )


def _http_ctx() -> HttpRequestContext:
    return HttpRequestContext(
        bearer_token="BEARER",
        url_requested="https://x",
        http_method_requested="POST",
        validation={"plan_id": "plan123", "subscriber_address": "0x123"},
    )


def _send_params():
    return SimpleNamespace(
        message=SimpleNamespace(task_id="tid", message_id="mid", context_id="ctx-123")
    )


def _completed_task() -> Task:
    return Task(
        id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.completed),
        history=[],
    )


@pytest.mark.asyncio()
async def test_on_message_send_holds_background_task_until_it_finishes():
    """The SDK's continuation must be strongly referenced while it is pending.

    `consume_and_break_on_interrupt` spawns the continuation with
    `asyncio.create_task` and documents that the caller has to retain it — the
    event loop keeps only a weak reference. That continuation is where the
    credit burn runs for an interrupted request, so an unheld task means a burn
    that can vanish to the garbage collector.

    Without this test the retention is pinned by nothing: every other mock in
    this module hands back `background_task=None`.
    """
    completed_task = _completed_task()
    gate = asyncio.Event()
    background_task = asyncio.create_task(gate.wait())

    with _mocked_send(completed_task, background_task):
        handler = _build_handler()
        handler.set_http_ctx_for_task("tid", _http_ctx())
        await handler.on_message_send(_send_params(), None)

        # Both interrupted-path tasks are held, under the names the parent
        # handler uses — the cleanup task is created synchronously in the
        # `finally`, so the loop has not run yet and this is deterministic.
        assert {t.get_name() for t in handler._background_tasks} == {
            "continue_consuming:tid",
            "cleanup_producer:tid",
        }
        assert background_task in handler._background_tasks

        gate.set()
        await background_task
        await asyncio.sleep(0)

        # ...and released once it finishes. (See #279 for the path where the
        # continuation never finishes: the producer is cancelled without the
        # queue being closed, so `consume_all` keeps re-polling forever.)
        assert background_task not in handler._background_tasks


@pytest.mark.asyncio()
async def test_background_task_failure_is_logged_not_swallowed(caplog):
    """A continuation that raises must say so, under the task's own name.

    Retention is delegated to `DefaultRequestHandler._track_background_task`
    precisely because its done-callback calls `result()`. Inside the
    continuation, `task_manager.process` and the payment-extension helpers run
    outside the `try` that wraps `settle_permissions`, so without that call a
    failure there loses the burn and leaves only asyncio's GC-time
    "exception was never retrieved".

    The task is deliberately created unnamed: the name asserted below has to
    come from `on_message_send`, not from this fixture, or the test would be
    pinning itself. The assertion is on the logged exception rather than on the
    SDK's wording, so an upstream reword does not fail a dependency bump for a
    non-behavioural reason.
    """
    completed_task = _completed_task()

    async def boom():
        raise RuntimeError("continuation blew up")

    background_task = asyncio.create_task(boom())

    with caplog.at_level(logging.ERROR), _mocked_send(completed_task, background_task):
        handler = _build_handler()
        handler.set_http_ctx_for_task("tid", _http_ctx())
        await handler.on_message_send(_send_params(), None)

        with pytest.raises(RuntimeError):
            await background_task
        await asyncio.sleep(0)

    logged = [
        record
        for record in caplog.records
        if "continue_consuming:tid" in record.getMessage()
        and record.exc_info
        and isinstance(record.exc_info[1], RuntimeError)
    ]
    assert logged, (
        "continuation failure was not logged under its task name: "
        f"{[r.getMessage() for r in caplog.records]}"
    )
    assert background_task not in handler._background_tasks


@pytest.mark.asyncio()
@pytest.mark.parametrize("blocking", [True, False])
async def test_consume_and_burn_credits_runs_against_the_real_sdk(blocking):
    """Exercise the real `_consume_and_burn_credits` against the real SDK.

    Every other `on_message_send` test patches this method out, so the a2a-sdk
    contract the runtime floor (`a2a-sdk = "^0.3.25"`) exists for — the
    `(result, interrupted, background_task)` triple, and `_continue_consuming`
    being the hook the burn is installed on — was covered by nothing but the
    staging E2E suite, which is exactly what the Dependabot gate in
    `.github/workflows/test.yaml` skips on a PR that bumps the dependency.

    No network and no executor: events are pushed onto a real `EventQueue`.
    `auth_required` interrupts even when `blocking=True`, which is what makes
    the SDK hand back a continuation on both parametrisations.
    """
    settle_calls: list[dict] = []

    def settle(**kwargs):
        settle_calls.append(kwargs)
        return make_settle_response(transaction="0xabc")

    handler = _build_handler(settle_mock=settle)
    http_ctx = _http_ctx()
    handler.set_http_ctx_for_task("tid", http_ctx)

    task_store = InMemoryTaskStore()
    auth_required_task = Task(
        id="tid",
        context_id="ctx-123",
        status=TaskStatus(state=TaskState.auth_required),
        history=[],
    )
    await task_store.save(auth_required_task)
    task_manager = TaskManager("tid", "ctx-123", task_store, None)
    aggregator = ResultAggregator(task_manager)

    queue = EventQueue()
    await queue.enqueue_event(auth_required_task)
    consumer = EventConsumer(queue)

    with patch(
        "payments_py.a2a.payments_request_handler.decode_access_token",
        return_value={"sub": "0x123"},
    ):
        result, interrupted, background_task = await handler._consume_and_burn_credits(
            aggregator, consumer, http_ctx, blocking
        )

        # The contract the floor is pinned for: a third element, and a real task.
        assert interrupted is True
        assert isinstance(background_task, asyncio.Task)
        assert result is not None

        # The burn hook must be live on the continuation, not just on the
        # foreground consumer.
        await queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id="tid",
                context_id="ctx-123",
                final=True,
                status=TaskStatus(state=TaskState.completed),
                metadata={"creditsUsed": 1},
            )
        )
        await queue.close()
        await background_task

    assert len(settle_calls) == 1, f"expected one settle, got {settle_calls}"
