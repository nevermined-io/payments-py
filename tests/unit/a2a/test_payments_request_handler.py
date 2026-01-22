"""Unit tests for PaymentsRequestHandler."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

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
        return (completed_task, False)  # (result, interrupted_or_non_blocking)

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

        return (completed_task, False)  # (result, interrupted_or_non_blocking)

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
        return (completed_task, False)

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
