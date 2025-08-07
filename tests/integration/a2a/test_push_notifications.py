"""Integration tests for push notifications and webhooks."""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock

from a2a.server.agent_execution import AgentExecutor
from a2a.server.events.event_queue import EventQueue
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import (
    Message,
    Role,
    Task,
    TaskStatus,
    TaskState,
    TaskStatusUpdateEvent,
    TaskIdParams,
)

from payments_py.a2a.payments_request_handler import PaymentsRequestHandler
from payments_py.a2a.types import MessageSendParams, HttpRequestContext
from payments_py.a2a.server import PaymentsA2AServer


class DummyWebhookExecutor(AgentExecutor):
    """Executor que simula una tarea que completa y debe enviar webhook."""

    def __init__(self, credits_to_use: int = 3):
        self.credits_to_use = credits_to_use

    async def execute(self, context, event_queue: EventQueue):
        """Execute task and publish completion events."""
        # Create task
        task_id = context.task_id
        context_id = getattr(context, "context_id", str(uuid4()))

        initial_task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.submitted),
        )
        await event_queue.enqueue_event(initial_task)

        # Working status
        working_status_update = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.working),
            final=False,
        )
        await event_queue.enqueue_event(working_status_update)

        # Simulate work
        await asyncio.sleep(0.01)

        # Completed with agent message
        agent_message = Message(
            message_id=str(uuid4()),
            role=Role.agent,
            parts=[{"kind": "text", "text": "Webhook test completed!"}],
            task_id=task_id,
            context_id=context_id,
        )

        final_status_update = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.completed,
                message=agent_message,
            ),
            final=True,
            metadata={"creditsUsed": self.credits_to_use},
        )

        await event_queue.enqueue_event(final_status_update)

    async def cancel(self, context, queue):
        """Cancel execution."""
        pass


class MockPaymentsService:
    """Mock payments service for testing."""

    def __init__(self):
        self.validation_call_count = 0
        self.redeem_call_count = 0
        self.last_redeem_credits = 0
        self.should_fail_validation = False

        # Create the requests API once
        self._requests_api = self._make_requests_api()

    def _make_requests_api(self):
        def start_processing_request(bearer_token: str) -> dict:
            self.validation_call_count += 1
            if self.should_fail_validation:
                raise RuntimeError("Validation failed")
            return {"result": "success", "agentRequestId": "req-123"}

        def redeem_credits_from_request(
            agent_request_id: str, bearer_token: str, credits: int
        ) -> None:
            self.redeem_call_count += 1
            self.last_redeem_credits = credits

        return SimpleNamespace(
            start_processing_request=start_processing_request,
            redeem_credits_from_request=redeem_credits_from_request,
            # Expose state for testing
            validation_call_count=lambda: self.validation_call_count,
            redeem_call_count=lambda: self.redeem_call_count,
            last_redeem_credits=lambda: self.last_redeem_credits,
        )

    @property
    def requests(self):
        # Return the same instance always, but update state properties
        self._requests_api.validation_call_count = self.validation_call_count
        self._requests_api.redeem_call_count = self.redeem_call_count
        self._requests_api.last_redeem_credits = self.last_redeem_credits
        self._requests_api.should_fail_validation = self.should_fail_validation
        return self._requests_api


pytestmark = pytest.mark.anyio


@pytest.mark.asyncio
async def test_push_notifications_with_webhook():
    """Test that push notifications are sent when a task completes."""

    # Setup mock payments service
    mock_payments = MockPaymentsService()

    # Mock webhook server responses
    webhook_calls = []

    async def mock_post(url, **kwargs):
        """Mock httpx POST call to capture webhook calls."""
        webhook_calls.append(
            {
                "url": url,
                "json": kwargs.get("json"),
                "headers": kwargs.get("headers"),
                "timeout": kwargs.get("timeout"),
            }
        )
        # Return a mock response
        response_mock = MagicMock()
        response_mock.status_code = 200
        return response_mock

    # Agent card with push notification capabilities
    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "webhook-agent-123",
                        "credits": 10,
                        "planId": "webhook-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    dummy_executor = DummyWebhookExecutor(credits_to_use=5)
    task_store = InMemoryTaskStore()

    # Create PaymentsRequestHandler directly for more control
    handler = PaymentsRequestHandler(
        agent_card=agent_card,
        task_store=task_store,
        agent_executor=dummy_executor,
        payments_service=mock_payments,
    )

    # Set up HTTP context
    http_ctx = HttpRequestContext(
        bearer_token="WEBHOOK_TOKEN",
        url_requested="/rpc",
        http_method_requested="POST",
        validation={"result": "success", "agentRequestId": "webhook-req-123"},
    )

    # Push notification config
    push_config = {
        "url": "https://webhook.example.com/callback",
        "authentication": {
            "schemes": ["bearer"],
            "credentials": "webhook-secret-token",
        },
    }

    # Mock the push config store methods
    with patch.object(
        handler, "on_get_task_push_notification_config", new_callable=AsyncMock
    ) as mock_get_push_config:
        mock_get_push_config.return_value = {"pushNotificationConfig": push_config}

        # Mock httpx POST call
        with patch(
            "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post
        ):

            # Create a message that will complete the task (no task_id, let SDK generate)
            message = Message(
                message_id=str(uuid4()),
                role=Role.user,
                parts=[{"kind": "text", "text": "Test webhook"}],
                # task_id=task_id,  # Don't specify, let SDK generate
            )

            params = MessageSendParams(message=message)

            # Set HTTP context by message ID first
            handler.set_http_ctx_for_message(message.message_id, http_ctx)

            # Execute the task (blocking mode to ensure completion)
            result = await handler.on_message_send(params)

            # Verify task completed
            assert isinstance(result, Task)
            assert result.status.state == TaskState.completed
            assert result.status.message.parts[0].root.text == "Webhook test completed!"

            # Get the generated task_id
            task_id = result.id

            # Verify credits were burned
            assert mock_payments.requests.redeem_call_count == 1
            assert mock_payments.requests.last_redeem_credits == 5

            # Wait a bit for async webhook call
            await asyncio.sleep(0.1)

            # Verify webhook was called
            assert len(webhook_calls) == 1
            webhook_call = webhook_calls[0]

            # Verify webhook URL
            assert webhook_call["url"] == "https://webhook.example.com/callback"

            # Verify webhook payload
            webhook_payload = webhook_call["json"]
            assert webhook_payload["taskId"] == task_id
            assert webhook_payload["state"] == "completed"
            assert "payload" in webhook_payload

            # Verify webhook authentication headers
            webhook_headers = webhook_call["headers"]
            assert webhook_headers["Content-Type"] == "application/json"
            assert webhook_headers["Authorization"] == "Bearer webhook-secret-token"

            # Verify timeout
            assert webhook_call["timeout"] == 5.0


@pytest.mark.asyncio
async def test_push_notifications_different_auth_schemes():
    """Test push notifications with different authentication schemes."""

    mock_payments = MockPaymentsService()
    webhook_calls = []

    async def mock_post(url, **kwargs):
        webhook_calls.append(
            {
                "url": url,
                "json": kwargs.get("json"),
                "headers": kwargs.get("headers"),
            }
        )
        response_mock = MagicMock()
        response_mock.status_code = 200
        return response_mock

    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "auth-test-agent",
                        "credits": 5,
                        "planId": "auth-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    dummy_executor = DummyWebhookExecutor(credits_to_use=2)
    task_store = InMemoryTaskStore()

    handler = PaymentsRequestHandler(
        agent_card=agent_card,
        task_store=task_store,
        agent_executor=dummy_executor,
        payments_service=mock_payments,
    )

    # Test cases for different auth schemes
    auth_test_cases = [
        {
            "name": "basic_auth",
            "config": {
                "url": "https://basic.example.com/webhook",
                "authentication": {
                    "schemes": ["basic"],
                    "credentials": "user:pass",
                },
            },
            "expected_auth": "Basic dXNlcjpwYXNz",  # base64("user:pass")
        },
        {
            "name": "custom_headers",
            "config": {
                "url": "https://custom.example.com/webhook",
                "authentication": {
                    "schemes": ["custom"],
                    "credentials": {
                        "X-API-Key": "custom-api-key",
                        "X-Secret": "custom-secret",
                    },
                },
            },
            "expected_headers": {
                "X-API-Key": "custom-api-key",
                "X-Secret": "custom-secret",
            },
        },
        {
            "name": "no_auth",
            "config": {
                "url": "https://noauth.example.com/webhook",
            },
            "expected_headers": {"Content-Type": "application/json"},
        },
    ]

    for test_case in auth_test_cases:
        webhook_calls.clear()  # Reset for each test case

        http_ctx = HttpRequestContext(
            bearer_token="TEST_TOKEN",
            url_requested="/rpc",
            http_method_requested="POST",
            validation={
                "result": "success",
                "agentRequestId": f"req-{test_case['name']}",
            },
        )

        with patch.object(
            handler, "on_get_task_push_notification_config", new_callable=AsyncMock
        ) as mock_get_push_config:
            mock_get_push_config.return_value = {
                "pushNotificationConfig": test_case["config"]
            }

            with patch(
                "httpx.AsyncClient.post", new_callable=AsyncMock, side_effect=mock_post
            ):

                message = Message(
                    message_id=str(uuid4()),
                    role=Role.user,
                    parts=[{"kind": "text", "text": f"Test {test_case['name']}"}],
                    # task_id=task_id,  # Don't specify, let SDK generate
                )

                params = MessageSendParams(message=message)
                handler.set_http_ctx_for_message(message.message_id, http_ctx)

                # Execute task
                result = await handler.on_message_send(params)
                assert result.status.state == TaskState.completed

                # Wait for webhook
                await asyncio.sleep(0.1)

                # Verify webhook call
                assert len(webhook_calls) == 1
                webhook_call = webhook_calls[0]

                assert webhook_call["url"] == test_case["config"]["url"]

                # Verify authentication
                headers = webhook_call["headers"]

                if "expected_auth" in test_case:
                    assert headers["Authorization"] == test_case["expected_auth"]
                elif "expected_headers" in test_case:
                    for key, value in test_case["expected_headers"].items():
                        assert headers[key] == value
                else:
                    # No auth case - should only have Content-Type
                    assert "Authorization" not in headers
                    assert headers["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_push_notifications_failure_handling():
    """Test that push notification failures don't break task execution."""

    mock_payments = MockPaymentsService()

    # Mock failing webhook calls
    async def mock_failing_post(*args, **kwargs):
        raise httpx.RequestError("Network error")

    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "failure-test-agent",
                        "credits": 3,
                        "planId": "failure-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    dummy_executor = DummyWebhookExecutor(credits_to_use=1)
    task_store = InMemoryTaskStore()

    handler = PaymentsRequestHandler(
        agent_card=agent_card,
        task_store=task_store,
        agent_executor=dummy_executor,
        payments_service=mock_payments,
    )

    http_ctx = HttpRequestContext(
        bearer_token="FAILURE_TOKEN",
        url_requested="/rpc",
        http_method_requested="POST",
        validation={"result": "success", "agentRequestId": "failure-req-123"},
    )

    push_config = {
        "url": "https://failing.example.com/webhook",
        "authentication": {
            "schemes": ["bearer"],
            "credentials": "secret",
        },
    }

    with patch.object(
        handler, "on_get_task_push_notification_config", new_callable=AsyncMock
    ) as mock_get_push_config:
        mock_get_push_config.return_value = {"pushNotificationConfig": push_config}

        with patch(
            "httpx.AsyncClient.post",
            new_callable=AsyncMock,
            side_effect=mock_failing_post,
        ):

            message = Message(
                message_id=str(uuid4()),
                role=Role.user,
                parts=[{"kind": "text", "text": "Test failure handling"}],
                # task_id=task_id,  # Don't specify, let SDK generate
            )

            params = MessageSendParams(message=message)
            handler.set_http_ctx_for_message(message.message_id, http_ctx)

            # Execute task - should succeed despite webhook failure
            result = await handler.on_message_send(params)

            # Verify task still completed successfully
            assert result.status.state == TaskState.completed
            assert result.status.message.parts[0].root.text == "Webhook test completed!"

            # Verify credits were still burned
            assert mock_payments.requests.redeem_call_count == 1
            assert mock_payments.requests.last_redeem_credits == 1

            # Wait for webhook attempt
            await asyncio.sleep(0.1)

            # The webhook should have been attempted but failed silently
            # No exception should have been raised
