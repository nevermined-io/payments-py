"""Unit test for PaymentsRequestHandler streaming credit burn."""

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.server.tasks.inmemory_push_notification_config_store import (
    InMemoryPushNotificationConfigStore,
)
from a2a.types import Task, TaskStatus, TaskState
from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import HttpRequestContext


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


@pytest.mark.asyncio()  # noqa: D401
async def test_streaming_burns_credits():  # noqa: D401
    # Mock redeem method - must be synchronous since it's called via run_in_executor
    redeem_mock = Mock(return_value={})
    dummy_payments = SimpleNamespace(
        requests=SimpleNamespace(redeem_credits_from_request=redeem_mock),
    )

    # Fake stream event Generator
    async def fake_stream(*_args, **_kwargs):  # noqa: D401
        yield {
            "kind": "status-update",
            "final": True,
            "status": {"state": "completed"},
            "metadata": {"creditsUsed": 7},
            "taskId": "tid",
        }

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
            agent_card={},
            task_store=task_store,
            agent_executor=DummyExecutor(),
            payments_service=dummy_payments,  # type: ignore[arg-type]
            push_config_store=InMemoryPushNotificationConfigStore(),
        )

        ctx = HttpRequestContext(
            bearer_token="TOK",
            url_requested="https://x",
            http_method_requested="POST",
            validation={"agentRequestId": "agentReq"},
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
    redeem_mock.assert_called_once_with("agentReq", "TOK", 7)
