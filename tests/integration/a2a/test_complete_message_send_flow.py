"""Integration tests for complete message/send flow with credit burning."""

import asyncio
import datetime
from uuid import uuid4
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from a2a.types import Task, TaskStatus, TaskState, Message, TaskStatusUpdateEvent
from payments_py.a2a.server import PaymentsA2AServer
from payments_py.common.payments_error import PaymentsError


# Mock decode_access_token for tests
def mock_decode_token(token):
    return {"planId": "test-plan", "sub": "0xTestSubscriber"}


class MockPaymentsService:
    """Mock payments service for testing."""

    def __init__(self):
        self.facilitator = MockFacilitatorAPI()


class MockFacilitatorAPI:
    """Mock facilitator API for testing x402 flow."""

    def __init__(self):
        self.validation_call_count = 0
        self.settle_call_count = 0
        self.last_settle_credits = None
        self.should_fail_validation = False
        self.should_fail_settle = False

    def verify_permissions(
        self,
        plan_id: str,
        max_amount: str,
        x402_access_token: str,
        subscriber_address: str,
    ) -> dict:
        """Mock verify_permissions."""
        self.validation_call_count += 1
        if self.should_fail_validation:
            raise PaymentsError.payment_required("Insufficient credits")

        return {"success": True}

    def settle_permissions(
        self,
        plan_id: str,
        max_amount: str,
        x402_access_token: str,
        subscriber_address: str,
    ) -> dict:
        """Mock settle_permissions."""
        self.settle_call_count += 1
        self.last_settle_credits = int(max_amount)
        if self.should_fail_settle:
            raise PaymentsError.payment_required("Failed to settle permissions")

        return {
            "success": True,
            "txHash": f"0x{plan_id[-8:]}",
            "data": {"creditsBurned": max_amount},
        }


class DummyExecutor:
    """Test executor that properly publishes events to event bus."""

    def __init__(self, should_fail=False, credits_to_use=5):
        self.should_fail = should_fail
        self.credits_to_use = credits_to_use

    async def execute(self, context, event_queue):
        """Execute method that publishes events like TypeScript version."""

        # Get task info from context - use the task_id from RequestContext
        task_id = getattr(context, "task_id", None) or str(uuid4())
        context_id = (
            context.context_id if hasattr(context, "context_id") else "test-ctx"
        )

        # Publish initial task if it doesn't exist (following TypeScript pattern)
        if not (hasattr(context, "task") and context.task):
            initial_task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.submitted,
                    timestamp=datetime.datetime.now().isoformat(),
                ),
                history=(
                    [context.user_message]
                    if hasattr(context, "user_message") and context.user_message
                    else []
                ),
                metadata=(
                    getattr(context.user_message, "metadata", None)
                    if hasattr(context, "user_message") and context.user_message
                    else None
                ),
            )
            await event_queue.enqueue_event(initial_task)

        # Publish working status (like TypeScript)
        working_status_update = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.working,
                message=Message(
                    message_id=str(uuid4()),
                    role="agent",
                    parts=[{"kind": "text", "text": "Processing your request..."}],
                    task_id=task_id,
                    context_id=context_id,
                ),
                timestamp=datetime.datetime.now().isoformat(),
            ),
            final=False,
        )
        await event_queue.enqueue_event(working_status_update)

        # Simulate processing time (shorter to avoid cancellation)
        try:
            await asyncio.sleep(0.01)
        except asyncio.CancelledError:
            # If cancelled, still try to publish final event
            print("[DEBUG] DummyExecutor was cancelled, but continuing to final event")

        # Publish final completed status with agent message (like TypeScript)
        agent_message = Message(
            message_id=str(uuid4()),
            role="agent",
            parts=[{"kind": "text", "text": "Request completed successfully!"}],
            task_id=task_id,
            context_id=context_id,
        )

        final_status_update = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.completed if not self.should_fail else TaskState.failed,
                message=agent_message,
                timestamp=datetime.datetime.now().isoformat(),
            ),
            metadata={
                "creditsUsed": self.credits_to_use,
            },
            final=True,
        )
        print(
            f"[DEBUG] DummyExecutor publishing final event with creditsUsed: {self.credits_to_use}"
        )
        await event_queue.enqueue_event(final_status_update)
        print("[DEBUG] DummyExecutor completed successfully")


@patch("payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token)
@pytest.mark.asyncio
async def test_complete_message_send_with_credit_burning():
    """Test complete message/send flow with successful credit burning."""
    # Setup mock services
    mock_payments = MockPaymentsService()

    # Create agent card with payment extension
    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "test-agent-123",
                        "credits": 10,
                        "planId": "test-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    # Create a dummy executor that will publish events with 3 credits used
    dummy_executor = DummyExecutor(should_fail=False, credits_to_use=3)

    # Start server
    result = PaymentsA2AServer.start(
        payments_service=mock_payments,  # type: ignore[arg-type]
        agent_card=agent_card,
        executor=dummy_executor,
        port=0,
        base_path="/rpc",
        expose_default_routes=True,
        run_async=False,
    )

    # Create test client
    client = TestClient(result.app)

    # Test successful message/send with credit burning
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-123",
                "contextId": "ctx-456",
                "role": "user",
                "parts": [{"kind": "text", "text": "Hello, burn my credits!"}],
            }
        },
    }

    headers = {"Authorization": "Bearer TEST_TOKEN"}
    response = client.post("/rpc", json=payload, headers=headers)

    # Verify response
    assert (
        response.status_code == 200
    ), f"Expected 200, got {response.status_code}: {response.text}"

    response_data = response.json()
    assert "result" in response_data

    # Verify that validation was called exactly once
    assert mock_payments.facilitator.validation_call_count == 1

    # Verify response contains the completed task (blocking mode should wait
    # for completion)
    task_result = response_data["result"]
    assert task_result["kind"] == "task"
    assert task_result["status"]["state"] == "completed"
    assert task_result["status"]["message"]["role"] == "agent"
    assert (
        task_result["status"]["message"]["parts"][0]["text"]
        == "Request completed successfully!"
    )

    # Verify that credits were burned exactly once (no sleep needed, blocking
    # mode waits)
    assert (
        mock_payments.facilitator.settle_call_count == 1
    ), f"Expected 1 settle call, got {mock_payments.facilitator.settle_call_count}"
    assert (
        mock_payments.facilitator.last_settle_credits == 3
    ), f"Expected 3 credits burned, got {mock_payments.facilitator.last_settle_credits}"


@patch("payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token)
@pytest.mark.asyncio
async def test_message_send_with_validation_failure():
    """Test message/send flow when validation fails."""
    # Setup mock services with validation failure
    mock_payments = MockPaymentsService()
    mock_payments.facilitator.should_fail_validation = True

    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "test-agent-123",
                        "credits": 10,
                        "planId": "test-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    dummy_executor = DummyExecutor()

    result = PaymentsA2AServer.start(
        payments_service=mock_payments,  # type: ignore[arg-type]
        agent_card=agent_card,
        executor=dummy_executor,
        port=0,
        base_path="/rpc",
        run_async=False,
    )

    client = TestClient(result.app)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-123",
                "contextId": "ctx-456",
                "role": "user",
                "parts": [{"kind": "text", "text": "This should fail validation"}],
            }
        },
    }

    headers = {"Authorization": "Bearer INVALID_TOKEN"}
    response = client.post("/rpc", json=payload, headers=headers)

    # Should return 402 (payment required) due to validation failure
    assert response.status_code == 402
    response_data = response.json()
    assert "error" in response_data
    assert "Validation error" in response_data["error"]["message"]

    # Verify validation was attempted exactly once but credits were not burned
    assert (
        mock_payments.facilitator.validation_call_count == 1
    ), f"Expected exactly 1 validation attempt, got {mock_payments.facilitator.validation_call_count}"
    assert (
        mock_payments.facilitator.settle_call_count == 0
    ), f"No credits should be settled on validation failure, but {mock_payments.facilitator.settle_call_count} calls were made"


@pytest.mark.asyncio
async def test_message_send_with_missing_bearer_token():
    """Test message/send without bearer token."""
    mock_payments = MockPaymentsService()

    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "test-agent-789",
                        "credits": 5,
                        "planId": "test-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    dummy_executor = DummyExecutor()

    result = PaymentsA2AServer.start(
        payments_service=mock_payments,  # type: ignore[arg-type]
        agent_card=agent_card,
        executor=dummy_executor,
        port=0,
        base_path="/rpc",
        run_async=False,
    )

    client = TestClient(result.app)

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "msg-no-token",
                "contextId": "ctx-no-token",
                "role": "user",
                "parts": [{"kind": "text", "text": "No token provided"}],
            }
        },
    }

    # No Authorization header
    response = client.post("/rpc", json=payload)

    # Should return 401 (unauthorized)
    assert response.status_code == 401
    response_data = response.json()
    assert "error" in response_data
    assert "Missing bearer token" in response_data["error"]["message"]

    # No validation or credit burning should occur
    assert (
        mock_payments.facilitator.validation_call_count == 0
    ), f"No validation should occur without bearer token, but {mock_payments.facilitator.validation_call_count} calls were made"
    assert (
        mock_payments.facilitator.settle_call_count == 0
    ), f"No credits should be settled without bearer token, but {mock_payments.facilitator.settle_call_count} calls were made"


@patch("payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token)
@pytest.mark.asyncio
async def test_non_blocking_execution_with_polling():
    """Test non-blocking execution (blocking: false) with task polling."""
    mock_payments = MockPaymentsService()

    # Create agent card
    agent_card = {
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "nonblock-agent-123",
                        "credits": 15,
                        "planId": "nonblock-plan",
                        "paymentType": "credits",
                    },
                }
            ]
        }
    }

    # Create executor with some delay to simulate async work
    executor = DummyExecutor(should_fail=False, credits_to_use=4)

    # Start server
    result = PaymentsA2AServer.start(
        payments_service=mock_payments,  # type: ignore[arg-type]
        agent_card=agent_card,
        executor=executor,
        port=0,
        base_path="/rpc",
        expose_default_routes=True,
        run_async=False,
    )

    client = TestClient(result.app)

    # Test non-blocking message/send
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "configuration": {
                "blocking": False,  # Non-blocking execution
            },
            "message": {
                "messageId": "nonblock-msg-123",
                "contextId": "nonblock-ctx-456",
                "role": "user",
                "parts": [{"kind": "text", "text": "Start non-blocking task!"}],
            },
        },
    }

    headers = {"Authorization": "Bearer NONBLOCK_TEST_TOKEN"}
    response = client.post("/rpc", json=payload, headers=headers)

    # Verify immediate response (should be submitted state)
    assert response.status_code == 200
    response_data = response.json()
    assert "result" in response_data

    task = response_data["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "submitted"  # Should return immediately

    task_id = task["id"]

    # For now, just verify the immediate response behavior
    # The non-blocking execution continues in background
    # In a real scenario, you'd poll the task or use webhooks

    # Verify initial validation occurred exactly once
    initial_validation_count = mock_payments.facilitator.validation_call_count
    assert (
        initial_validation_count == 1
    ), f"Expected exactly 1 validation call, got {initial_validation_count}"

    # Poll for task completion - now that we've fixed the background processing,
    # the task should actually complete and credits should be burned
    max_attempts = 10
    final_task = None

    for attempt in range(max_attempts):
        poll_payload = {
            "jsonrpc": "2.0",
            "id": 2 + attempt,  # Different ID for each poll
            "method": "tasks/get",
            "params": {"id": task_id},
        }

        poll_response = client.post("/rpc", json=poll_payload, headers=headers)

        if poll_response.status_code == 200:
            poll_data = poll_response.json()
            if "result" in poll_data:
                task_result = poll_data["result"]
                print(
                    f"[Attempt {attempt + 1}] Task state: {task_result['status']['state']}"
                )

                if task_result["status"]["state"] == "completed":
                    final_task = task_result
                    break
                elif task_result["status"]["state"] in ["failed", "canceled"]:
                    break  # Don't continue polling for terminal failure states

        await asyncio.sleep(0.2)  # Wait before next poll

    # Verify final task completion
    assert (
        final_task is not None
    ), f"Task should have completed within polling window after {max_attempts} attempts"
    assert final_task["status"]["state"] == "completed"
    assert final_task["status"]["message"]["role"] == "agent"
    assert (
        final_task["status"]["message"]["parts"][0]["text"]
        == "Request completed successfully!"
    )

    # Verify validation occurred (initial + any polling validation)
    assert mock_payments.facilitator.validation_call_count >= initial_validation_count

    # Most importantly: verify credit burning occurred after task completion
    assert (
        mock_payments.facilitator.settle_call_count == 1
    ), "Credits should be settled when task completes in non-blocking mode"
