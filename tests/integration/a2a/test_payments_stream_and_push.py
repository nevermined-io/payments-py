"""Integration tests for streaming, resubscribe and push notifications."""

from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

import pytest
import unittest.mock

from a2a.server.agent_execution import AgentExecutor
from a2a.types import (
    Message,
    Role,
    Part,
    TaskStatus,
    TaskState,
    TaskStatusUpdateEvent,
)
from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import MessageSendParams, AgentCard, HttpRequestContext


class DummyStreamingExecutor(AgentExecutor):  # noqa: D101
    async def execute(self, request_context, event_bus):  # type: ignore[override]  # noqa: D401
        # Emit a message then a terminal status update
        msg_id = str(uuid4())
        task_id = (
            request_context.current_task.id
            if request_context.current_task
            else str(uuid4())
        )
        context_id = (
            request_context.current_task.context_id
            if request_context.current_task
            else str(uuid4())
        )

        # Create proper Message object
        message = Message(
            message_id=msg_id,
            role="agent",
            parts=[Part(text="hi")],  # Use proper Part object
            task_id=task_id,
            context_id=context_id,
        )

        # Create proper TaskStatusUpdateEvent
        status_update = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.completed),
            final=True,
            metadata={"creditsUsed": 2},
        )

        await event_bus.enqueue_event(message)
        await event_bus.enqueue_event(status_update)

    async def cancel(self, request_context, queue):  # noqa: D401, D403
        pass


@pytest.fixture()
def agent_card() -> AgentCard:  # noqa: D401
    return {
        "name": "PyAgent",
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "agent-1",
                        "paymentType": "fixed",
                        "credits": 1,
                    },
                }
            ]
        },
    }


@pytest.fixture()
def payments_stub(monkeypatch):  # noqa: D401
    settle_called = {}

    def settle(**kwargs):  # noqa: D401
        settle_called["called"] = kwargs
        return {"success": True, "txHash": "0x123", "data": {"creditsBurned": str(kwargs.get("max_amount", 0))}}

    payments = SimpleNamespace(
        facilitator=SimpleNamespace(
            verify_permissions=lambda **k: {"success": True},
            settle_permissions=settle,
        )
    )
    return payments, settle_called


pytestmark = pytest.mark.anyio


async def test_stream_and_resubscribe(agent_card, payments_stub):  # noqa: D401
    """Test that credits are burned when agent returns a terminal task."""
    payments, settle_called = payments_stub

    # Mock objects needed for the test
    handler = PaymentsRequestHandler(
        agent_card=agent_card,
        task_store=None,
        agent_executor=None,
        payments_service=payments,
    )

    # Set up HTTP context for the task
    http_ctx = HttpRequestContext(
        bearer_token="TOK",
        url_requested="/rpc",
        http_method_requested="POST",
        validation={"result": "success", "plan_id": "plan-123", "subscriber_address": "0xSub123"},
    )
    # Set context by message_id (as the handler looks for it)
    handler.set_http_ctx_for_message("msg-123", http_ctx)

    # Mock the parent's on_message_send_stream to yield our events
    async def mock_parent_stream(params, context=None):
        # Simulate migrating context from message to task manually
        http_ctx = handler._http_ctx_by_message.get("msg-123")
        if http_ctx:
            handler.set_http_ctx_for_task("task-123", http_ctx)

        # Yield a status update event with credits used
        yield {
            "kind": "status-update",
            "taskId": "task-123",
            "contextId": "ctx-123",
            "final": True,
            "status": {"state": "completed"},
            "metadata": {"creditsUsed": 2},
        }

    with unittest.mock.patch.object(
        handler.__class__.__bases__[0],
        "on_message_send_stream",
        side_effect=mock_parent_stream,
    ):
        # Call the handler's on_message_send_stream method
        message = Message(message_id="msg-123", role=Role.user, parts=[])
        params = MessageSendParams(message=message)

        events = []
        async for event in handler.on_message_send_stream(params):
            events.append(event)

        # Debug info
        print(f"Events received: {len(events)}")
        print(f"settle_called: {settle_called}")

        # Should have called settle_permissions
        assert settle_called
        assert len(events) == 1
