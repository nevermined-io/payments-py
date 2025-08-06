"""Integration tests for complete message/send flow with credit burning."""

import asyncio
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient
import pytest
from payments_py.a2a.server import PaymentsA2AServer
from payments_py.common.payments_error import PaymentsError


class MockPaymentsService:
    """Mock payments service for testing."""

    def __init__(self):
        self.requests = MockRequestsAPI()


class MockRequestsAPI:
    """Mock requests API for testing."""

    def __init__(self):
        self.validation_call_count = 0
        self.redeem_call_count = 0
        self.last_redeem_credits = None
        self.should_fail_validation = False
        self.should_fail_redeem = False

    def start_processing_request(
        self,
        agent_id: str,
        access_token: str,
        url_requested: str,
        http_method_requested: str,
    ) -> dict:
        """Mock start_processing_request."""
        self.validation_call_count += 1
        if self.should_fail_validation:
            raise PaymentsError.payment_required("Insufficient credits")

        return {
            "agentRequestId": f"req-{agent_id}-{self.validation_call_count}",
            "agentId": agent_id,
            "accessToken": access_token,
            "credits": 100,
            "planId": "test-plan",
        }

    def redeem_credits_from_request(
        self, agent_request_id: str, access_token: str, credits_used: int
    ) -> dict:
        """Mock redeem_credits_from_request."""
        self.redeem_call_count += 1
        self.last_redeem_credits = credits_used
        if self.should_fail_redeem:
            raise PaymentsError.payment_required("Failed to redeem credits")

        return {
            "txHash": f"0x{agent_request_id[-8:]}",
            "creditsRedeemed": credits_used,
            "remainingCredits": 100 - credits_used,
        }


class DummyExecutor:
    """Test executor that properly publishes events to event bus."""

    def __init__(self, should_fail=False, credits_to_use=5):
        self.should_fail = should_fail
        self.credits_to_use = credits_to_use

    async def execute(self, context, event_queue):
        """Execute method that publishes events like TypeScript version."""
        from a2a.types import Task, TaskStatus, TaskState, Message
        from uuid import uuid4
        import datetime

        # Get task info from context
        task_id = (
            context.task.id
            if hasattr(context, "task") and context.task
            else str(uuid4())
        )
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

        # Simulate processing time
        await asyncio.sleep(0.05)

        # Publish agent response message
        agent_message = Message(
            message_id=str(uuid4()),
            role="agent",
            parts=[{"kind": "text", "text": "Request completed successfully!"}],
            task_id=task_id,
            context_id=context_id,
        )
        await event_queue.enqueue_event(agent_message)

        # Publish final status update with creditsUsed
        final_status_update = {
            "kind": "status-update",
            "taskId": task_id,
            "contextId": context_id,
            "status": TaskStatus(
                state=TaskState.completed if not self.should_fail else TaskState.failed,
                message=agent_message,
                timestamp=datetime.datetime.now().isoformat(),
            ),
            "metadata": {
                "creditsUsed": self.credits_to_use,
            },
            "final": True,
        }
        await event_queue.enqueue_event(final_status_update)


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

    # Verify that validation was called
    assert mock_payments.requests.validation_call_count == 1

    # Verify that credits were burned (may be async, so we wait a bit)
    await asyncio.sleep(0.2)
    assert mock_payments.requests.redeem_call_count == 1
    assert mock_payments.requests.last_redeem_credits == 3


@pytest.mark.asyncio
async def test_message_send_with_validation_failure():
    """Test message/send flow when validation fails."""
    # Setup mock services with validation failure
    mock_payments = MockPaymentsService()
    mock_payments.requests.should_fail_validation = True

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

    # Verify validation was attempted but credits were not burned
    assert mock_payments.requests.validation_call_count == 1
    assert mock_payments.requests.redeem_call_count == 0


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
    assert mock_payments.requests.validation_call_count == 0
    assert mock_payments.requests.redeem_call_count == 0
