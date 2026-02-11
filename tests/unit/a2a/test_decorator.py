"""Unit tests for @a2a_requires_payment decorator."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

import pytest
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    Task,
    TaskState,
    TaskStatusUpdateEvent,
)

from payments_py.a2a.decorator import (
    AgentResponse,
    _DecoratorExecutor,
    a2a_requires_payment,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_context(
    *, text: str = "Hello", task_id: str = "tid-1", context_id: str = "ctx-1"
):
    """Build a lightweight RequestContext-like object."""
    return SimpleNamespace(
        task_id=task_id,
        context_id=context_id,
        message=None,
        current_task=None,
        get_user_input=lambda delimiter="\n": text,
    )


class _SpyEventQueue(EventQueue):
    """EventQueue that also records all enqueued events for easy assertion."""

    def __init__(self):
        super().__init__()
        self.events: list = []

    async def enqueue_event(self, event):
        self.events.append(event)
        await super().enqueue_event(event)


def _make_payments():
    return SimpleNamespace(
        facilitator=SimpleNamespace(
            verify_permissions=Mock(return_value=SimpleNamespace(is_valid=True)),
            settle_permissions=Mock(return_value={"success": True}),
        ),
    )


def _make_agent_card():
    return {
        "name": "TestAgent",
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "paymentType": "dynamic",
                        "credits": 10,
                        "agentId": "agent-1",
                        "planId": "plan-1",
                    },
                }
            ]
        },
    }


# ---------------------------------------------------------------------------
# AgentResponse tests
# ---------------------------------------------------------------------------
class TestAgentResponse:
    def test_defaults(self):
        r = AgentResponse(text="hi")
        assert r.text == "hi"
        assert r.credits_used is None
        assert r.metadata is None

    def test_custom_values(self):
        r = AgentResponse(text="ok", credits_used=5, metadata={"foo": "bar"})
        assert r.credits_used == 5
        assert r.metadata == {"foo": "bar"}


# ---------------------------------------------------------------------------
# _DecoratorExecutor tests
# ---------------------------------------------------------------------------
class TestDecoratorExecutor:
    @pytest.mark.asyncio
    async def test_publishes_initial_task_and_completed_event(self):
        """Executor should publish initial Task -> working -> completed events."""

        async def handler(ctx):
            return AgentResponse(text="Done!", credits_used=3)

        executor = _DecoratorExecutor(handler, default_credits=1)
        ctx = _make_context()
        queue = _SpyEventQueue()

        await executor.execute(ctx, queue)
        events = queue.events

        # Should have 3 events: Task (submitted), working update, completed update
        assert len(events) == 3

        # First: initial Task
        assert isinstance(events[0], Task)
        assert events[0].status.state == TaskState.submitted

        # Second: working status
        assert isinstance(events[1], TaskStatusUpdateEvent)
        assert events[1].status.state == TaskState.working
        assert events[1].final is False

        # Third: completed status with creditsUsed
        final = events[2]
        assert isinstance(final, TaskStatusUpdateEvent)
        assert final.status.state == TaskState.completed
        assert final.final is True
        assert final.metadata["creditsUsed"] == 3
        assert final.status.message.parts[0].root.text == "Done!"

    @pytest.mark.asyncio
    async def test_default_credits_used_when_none(self):
        """When AgentResponse.credits_used is None, default_credits is used."""

        async def handler(ctx):
            return AgentResponse(text="ok")

        executor = _DecoratorExecutor(handler, default_credits=7)
        ctx = _make_context()
        queue = _SpyEventQueue()

        await executor.execute(ctx, queue)

        final = queue.events[-1]
        assert final.metadata["creditsUsed"] == 7

    @pytest.mark.asyncio
    async def test_extra_metadata_merged(self):
        """Extra metadata from AgentResponse should be merged into event metadata."""

        async def handler(ctx):
            return AgentResponse(text="ok", credits_used=2, metadata={"skill": "calc"})

        executor = _DecoratorExecutor(handler, default_credits=1)
        ctx = _make_context()
        queue = _SpyEventQueue()

        await executor.execute(ctx, queue)

        final = queue.events[-1]
        assert final.metadata["creditsUsed"] == 2
        assert final.metadata["skill"] == "calc"

    @pytest.mark.asyncio
    async def test_handler_exception_publishes_failed_event(self):
        """When the handler raises, executor should publish a failed event."""

        async def handler(ctx):
            raise ValueError("something broke")

        executor = _DecoratorExecutor(handler, default_credits=1)
        ctx = _make_context()
        queue = _SpyEventQueue()

        await executor.execute(ctx, queue)
        events = queue.events

        # Should have: Task (submitted), working, failed
        assert len(events) == 3
        final = events[-1]
        assert isinstance(final, TaskStatusUpdateEvent)
        assert final.status.state == TaskState.failed
        assert final.final is True
        assert final.metadata["creditsUsed"] == 0
        assert "something broke" in final.status.message.parts[0].root.text

    @pytest.mark.asyncio
    async def test_cancel_publishes_cancelled_event(self):
        """cancel() should publish a cancelled event with 0 credits."""

        async def handler(ctx):
            return AgentResponse(text="never called")

        executor = _DecoratorExecutor(handler, default_credits=1)
        ctx = _make_context()
        queue = _SpyEventQueue()

        await executor.cancel(ctx, queue)
        events = queue.events

        assert len(events) == 1
        event = events[0]
        assert isinstance(event, TaskStatusUpdateEvent)
        assert event.status.state == TaskState.canceled
        assert event.final is True
        assert event.metadata["creditsUsed"] == 0

    @pytest.mark.asyncio
    async def test_skips_initial_task_when_current_task_exists(self):
        """When context already has a current_task, skip publishing initial Task."""

        async def handler(ctx):
            return AgentResponse(text="ok", credits_used=1)

        executor = _DecoratorExecutor(handler, default_credits=1)
        ctx = _make_context()
        ctx.current_task = SimpleNamespace(id="tid-1")
        queue = _SpyEventQueue()

        await executor.execute(ctx, queue)
        events = queue.events

        # Should have 2 events: working + completed (no initial Task)
        assert len(events) == 2
        assert isinstance(events[0], TaskStatusUpdateEvent)
        assert events[0].status.state == TaskState.working
        assert isinstance(events[1], TaskStatusUpdateEvent)
        assert events[1].status.state == TaskState.completed


# ---------------------------------------------------------------------------
# Decorator wrapper tests
# ---------------------------------------------------------------------------
class TestA2ARequiresPaymentDecorator:
    def test_decorated_function_has_serve_and_create_server(self):
        """Decorated function should have .serve() and .create_server() methods."""
        payments = _make_payments()
        card = _make_agent_card()

        @a2a_requires_payment(payments=payments, agent_card=card, default_credits=2)
        async def my_agent(context):
            return AgentResponse(text="hi")

        assert callable(my_agent.serve)
        assert callable(my_agent.create_server)

    def test_decorated_function_has_executor(self):
        """Decorated function should expose its internal executor."""
        payments = _make_payments()
        card = _make_agent_card()

        @a2a_requires_payment(payments=payments, agent_card=card)
        async def my_agent(context):
            return AgentResponse(text="hi")

        assert isinstance(my_agent.executor, _DecoratorExecutor)

    def test_decorated_function_preserves_name(self):
        """functools.wraps should preserve the original function name."""
        payments = _make_payments()
        card = _make_agent_card()

        @a2a_requires_payment(payments=payments, agent_card=card)
        async def my_special_agent(context):
            return AgentResponse(text="hi")

        assert my_special_agent.__name__ == "my_special_agent"

    @pytest.mark.asyncio
    async def test_wrapper_still_callable(self):
        """The wrapper should still be callable as an async function."""
        payments = _make_payments()
        card = _make_agent_card()

        @a2a_requires_payment(payments=payments, agent_card=card)
        async def my_agent(context):
            return AgentResponse(text="direct call")

        result = await my_agent(_make_context())
        assert isinstance(result, AgentResponse)
        assert result.text == "direct call"

    def test_serve_calls_payments_a2a_server_start(self):
        """serve() should call PaymentsA2AServer.start() with correct args."""
        payments = _make_payments()
        card = _make_agent_card()

        @a2a_requires_payment(
            payments=payments,
            agent_card=card,
            default_credits=3,
            async_execution=True,
        )
        async def my_agent(context):
            return AgentResponse(text="hi")

        mock_result = MagicMock()
        mock_result.server.serve = AsyncMock()

        with patch(
            "payments_py.a2a.server.PaymentsA2AServer.start",
            return_value=mock_result,
        ) as mock_start:
            with patch("asyncio.run") as mock_run:
                my_agent.serve(port=9090, base_path="/api")

        mock_start.assert_called_once_with(
            agent_card=card,
            executor=my_agent.executor,
            payments_service=payments,
            port=9090,
            base_path="/api",
            expose_agent_card=True,
            hooks=None,
            async_execution=True,
            app=None,
        )

    def test_create_server_returns_server_result(self):
        """create_server() should return PaymentsA2AServerResult."""
        payments = _make_payments()
        card = _make_agent_card()

        @a2a_requires_payment(payments=payments, agent_card=card)
        async def my_agent(context):
            return AgentResponse(text="hi")

        mock_result = MagicMock()

        with patch(
            "payments_py.a2a.server.PaymentsA2AServer.start",
            return_value=mock_result,
        ) as mock_start:
            result = my_agent.create_server(port=7070)

        assert result is mock_result
        mock_start.assert_called_once()
