"""Unit test for PaymentsRequestHandler streaming credit burn."""

import logging

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.inmemory_push_notification_config_store import (
    InMemoryPushNotificationConfigStore,
)
from a2a.types import Task, TaskStatus, TaskState, TaskStatusUpdateEvent
from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import HttpRequestContext


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


@pytest.mark.asyncio()  # noqa: D401
async def test_streaming_burns_credits():  # noqa: D401
    # Mock settle method - must be synchronous since it's called via run_in_executor
    settle_mock = Mock(
        return_value={
            "success": True,
            "txHash": "0x123",
            "data": {"creditsBurned": "7"},
        }
    )
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    # Fake stream yielding a Pydantic TaskStatusUpdateEvent (not a dict)
    async def fake_stream(*_args, **_kwargs):  # noqa: D401
        yield TaskStatusUpdateEvent(
            task_id="tid",
            context_id="ctx-123",
            final=True,
            status=TaskStatus(state=TaskState.completed),
            metadata={"creditsUsed": 7},
        )

    with patch(
        "payments_py.a2a.payments_request_handler.DefaultRequestHandler.on_message_send_stream",
        new=fake_stream,
    ):
        # Create task store and add the task that will be referenced
        task_store = InMemoryTaskStore()
        test_task = Task(
            id="tid",
            context_id="ctx-123",
            status=TaskStatus(state=TaskState.completed),
        )
        await task_store.save(test_task)

        handler = PaymentsRequestHandler(
            agent_card={
                "capabilities": {
                    "extensions": [
                        {
                            "uri": "urn:nevermined:payment",
                            "params": {"agentId": "agent-1", "planId": "plan-123"},
                        }
                    ]
                }
            },
            task_store=task_store,
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        ctx = HttpRequestContext(
            bearer_token="TOK",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"plan_id": "plan-123", "subscriber_address": "0xSub123"},
        )
        handler.set_http_ctx_for_task("tid", ctx)

        # Consume stream
        events = []
        async for ev in handler.on_message_send_stream(
            SimpleNamespace(message=SimpleNamespace(task_id="tid", message_id="mid")),
            None,
        ):
            events.append(ev)

    assert len(events) == 1
    # Should have called settle_permissions with x402 API
    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["x402_access_token"] == "TOK"
    assert call_kwargs["max_amount"] == "7"
    assert call_kwargs["payment_required"] is not None
    assert (
        call_kwargs["agent_request_id"] is None
    )  # No agent_request_id in validation or metadata


@pytest.mark.asyncio()  # noqa: D401
async def test_streaming_passes_agent_request_id_from_validation():  # noqa: D401
    """Test streaming settlement passes agent_request_id from validation context."""
    settle_mock = Mock(
        return_value={
            "success": True,
            "txHash": "0x123",
            "data": {"creditsBurned": "3"},
        }
    )
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    async def fake_stream(*_args, **_kwargs):  # noqa: D401
        yield TaskStatusUpdateEvent(
            task_id="tid",
            context_id="ctx-123",
            final=True,
            status=TaskStatus(state=TaskState.completed),
            metadata={"creditsUsed": 3},
        )

    with patch(
        "payments_py.a2a.payments_request_handler.DefaultRequestHandler.on_message_send_stream",
        new=fake_stream,
    ):
        task_store = InMemoryTaskStore()
        test_task = Task(
            id="tid",
            context_id="ctx-123",
            status=TaskStatus(state=TaskState.completed),
        )
        await task_store.save(test_task)

        handler = PaymentsRequestHandler(
            agent_card={
                "capabilities": {
                    "extensions": [
                        {
                            "uri": "urn:nevermined:payment",
                            "params": {"agentId": "agent-1", "planId": "plan-123"},
                        }
                    ]
                }
            },
            task_store=task_store,
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        ctx = HttpRequestContext(
            bearer_token="TOK",
            url_requested="https://x",
            http_method_requested="POST",
            validation={
                "plan_id": "plan-123",
                "subscriber_address": "0xSub123",
                "agent_request_id": "req-stream-abc",
            },
        )
        handler.set_http_ctx_for_task("tid", ctx)

        events = []
        async for ev in handler.on_message_send_stream(
            SimpleNamespace(message=SimpleNamespace(task_id="tid", message_id="mid")),
            None,
        ):
            events.append(ev)

    assert len(events) == 1
    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["agent_request_id"] == "req-stream-abc"


@pytest.mark.asyncio()  # noqa: D401
async def test_streaming_passes_agent_request_id_from_event_metadata():  # noqa: D401
    """Test streaming settlement falls back to agentRequestId from event metadata."""
    settle_mock = Mock(
        return_value={
            "success": True,
            "txHash": "0x123",
            "data": {"creditsBurned": "2"},
        }
    )
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    async def fake_stream(*_args, **_kwargs):  # noqa: D401
        yield TaskStatusUpdateEvent(
            task_id="tid",
            context_id="ctx-123",
            final=True,
            status=TaskStatus(state=TaskState.completed),
            metadata={"creditsUsed": 2, "agentRequestId": "req-meta-456"},
        )

    with patch(
        "payments_py.a2a.payments_request_handler.DefaultRequestHandler.on_message_send_stream",
        new=fake_stream,
    ):
        task_store = InMemoryTaskStore()
        test_task = Task(
            id="tid",
            context_id="ctx-123",
            status=TaskStatus(state=TaskState.completed),
        )
        await task_store.save(test_task)

        handler = PaymentsRequestHandler(
            agent_card={
                "capabilities": {
                    "extensions": [
                        {
                            "uri": "urn:nevermined:payment",
                            "params": {"agentId": "agent-1", "planId": "plan-123"},
                        }
                    ]
                }
            },
            task_store=task_store,
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        ctx = HttpRequestContext(
            bearer_token="TOK",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"plan_id": "plan-123", "subscriber_address": "0xSub123"},
        )
        handler.set_http_ctx_for_task("tid", ctx)

        events = []
        async for ev in handler.on_message_send_stream(
            SimpleNamespace(message=SimpleNamespace(task_id="tid", message_id="mid")),
            None,
        ):
            events.append(ev)

    assert len(events) == 1
    settle_mock.assert_called_once()
    call_kwargs = settle_mock.call_args.kwargs
    assert call_kwargs["agent_request_id"] == "req-meta-456"


@pytest.mark.asyncio()  # noqa: D401
async def test_streaming_spent_token_records_a_failed_receipt(caplog):  # noqa: D401
    """Execute the streaming settle site's real call into the shared policy.

    The events have already gone out by then, so the output cannot be retracted
    — but that argument covers withholding, not silence: the failed receipt is
    what makes the in-band path emit payment-failed instead of reporting the
    task as paid, and it must land under the task id the in-band path reads.

    Driven through `on_message_send_stream` rather than by calling
    `_record_settle_failure` directly, so the call site's own arguments are
    under test: `streamed=`, the task id and `inband` are supplied by the
    handler here, not by the test. Mutating any of them goes red.
    """
    from payments_py.common.payments_error import PaymentsError

    settle_mock = Mock(
        side_effect=PaymentsError("access token already used", "BCK.X402.0059")
    )
    dummy_payments = SimpleNamespace(
        facilitator=SimpleNamespace(settle_permissions=settle_mock),
    )

    async def fake_stream(*_args, **_kwargs):  # noqa: D401
        yield TaskStatusUpdateEvent(
            task_id="tid",
            context_id="ctx-123",
            final=True,
            status=TaskStatus(state=TaskState.completed),
            metadata={"creditsUsed": 7},
        )

    with patch(
        "payments_py.a2a.payments_request_handler.DefaultRequestHandler.on_message_send_stream",
        new=fake_stream,
    ):
        task_store = InMemoryTaskStore()
        await task_store.save(
            Task(
                id="tid",
                context_id="ctx-123",
                status=TaskStatus(state=TaskState.completed),
            )
        )

        handler = PaymentsRequestHandler(
            agent_card={
                "capabilities": {
                    "extensions": [
                        {
                            "uri": "urn:nevermined:payment",
                            "params": {"agentId": "agent-1", "planId": "plan-123"},
                        }
                    ]
                }
            },
            task_store=task_store,
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        handler.set_http_ctx_for_task(
            "tid",
            HttpRequestContext(
                bearer_token="TOK",
                url_requested="https://x",
                http_method_requested="POST",
                validation={"plan_id": "plan-123", "subscriber_address": "0xSub123"},
                inband=True,
            ),
        )

        with caplog.at_level(logging.ERROR):
            async for _ in handler.on_message_send_stream(
                SimpleNamespace(
                    message=SimpleNamespace(task_id="tid", message_id="mid")
                ),
                None,
            ):
                pass

    settle_mock.assert_called_once()
    # The call site's own `streamed=` argument, not one the test supplies: a
    # replay here is unrecoverable in a way the finalization site's is not, and
    # the log has to say which happened.
    assert any(
        "after the stream was delivered" in record.getMessage()
        and record.levelno == logging.ERROR
        for record in caplog.records
    )
    # Under the id the in-band path reads, or payment-failed never fires.
    receipt = handler._settle_receipt_by_task["tid"]
    assert receipt.success is False
    assert "BCK.X402.0059" in (receipt.error_reason or "")
