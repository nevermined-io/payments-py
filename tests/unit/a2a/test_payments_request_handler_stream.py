"""Unit test for PaymentsRequestHandler streaming credit burn."""

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
