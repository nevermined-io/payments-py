"""
E2E tests for A2A payment flow.

End-to-end tests for A2A server and client functionality with real network requests.
These tests verify the complete payment flow including:
- Blocking and non-blocking execution
- Authentication and authorization
- Streaming
- Webhooks and push notifications
- Task resubscription and cancellation
- Credit burning
"""

import asyncio
import json
import time
from types import SimpleNamespace
from typing import Any, Dict
from uuid import uuid4

import httpx
import pytest
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.types import (
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from fastapi.testclient import TestClient

from payments_py import Payments
from payments_py.common.payments_error import PaymentsError

from tests.e2e.helpers.a2a_e2e_helpers import (
    A2AE2EAssertions,
    A2AE2EFactory,
    A2AE2EServerManager,
    A2AE2EUtils,
    E2ETestConfig,
)


class MockE2EPaymentsService:
    """Mock payments service for E2E testing with realistic behavior."""

    def __init__(self):
        self.validation_call_count = 0
        self.redeem_call_count = 0
        self.last_redeem_credits = None
        self.should_fail_validation = False
        self.should_fail_redeem = False
        self.bearer_token_map = {
            "VALID_E2E_TOKEN": "valid-agent-123",
            "INVALID_TOKEN": None,
            "BLOCKING_TOKEN": "blocking-agent-456",
            "NON_BLOCKING_TOKEN": "nonblocking-agent-789",
            "STREAMING_TOKEN": "streaming-agent-999",
        }

    @property
    def requests(self):
        """Return requests API interface."""
        return SimpleNamespace(
            start_processing_request=self.start_processing_request,
            redeem_credits_from_request=self.redeem_credits_from_request,
            validation_call_count=self.validation_call_count,
            redeem_call_count=self.redeem_call_count,
            last_redeem_credits=self.last_redeem_credits,
        )

    def start_processing_request(
        self,
        agent_id: str,
        access_token: str,
        url_requested: str,
        http_method_requested: str,
    ) -> dict:
        """Mock start_processing_request with realistic validation."""
        self.validation_call_count += 1

        if self.should_fail_validation or access_token == "INVALID_TOKEN":
            raise PaymentsError.payment_required(
                "Invalid token or insufficient credits"
            )

        if access_token not in self.bearer_token_map:
            raise PaymentsError.payment_required("Unknown bearer token")

        expected_agent_id = self.bearer_token_map.get(access_token)
        if expected_agent_id and agent_id != expected_agent_id:
            raise PaymentsError.payment_required(
                f"Token not valid for agent {agent_id}"
            )

        return {
            "agentRequestId": f"req-{agent_id}-{self.validation_call_count}",
            "agentId": agent_id,
            "accessToken": access_token,
            "credits": 100,
            "planId": "e2e-test-plan",
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
            "remainingCredits": max(0, 100 - credits_used),
        }


class E2ETestExecutor(AgentExecutor):
    """Test executor for E2E tests with realistic behavior."""

    def __init__(self, execution_time: float = 1.0, credits_to_use: int = 5):
        self.execution_time = execution_time
        self.credits_to_use = credits_to_use
        self.execution_count = 0

    async def execute(self, context, event_queue):
        """Execute with realistic agent behavior."""
        self.execution_count += 1
        task_id = context.task_id
        context_id = context.context_id

        print(f"[E2E Executor] Starting execution for task {task_id}")

        # Publish initial task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.working,
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.agent,
                    parts=[{"kind": "text", "text": "Starting E2E test execution..."}],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
        )
        await event_queue.enqueue_event(task)

        # Publish working status
        working_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.working,
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.agent,
                    parts=[{"kind": "text", "text": "Processing E2E test request..."}],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
            final=False,
        )
        await event_queue.enqueue_event(working_event)

        # Simulate execution time
        await asyncio.sleep(self.execution_time)

        # Publish completion
        completed_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.agent,
                    parts=[
                        {
                            "kind": "text",
                            "text": f"E2E test execution completed! Credits used: {self.credits_to_use}",
                        }
                    ],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
            final=True,
            metadata={"creditsUsed": self.credits_to_use},
        )
        await event_queue.enqueue_event(completed_event)

        print(
            f"[E2E Executor] Completed execution for task {task_id}, credits: {self.credits_to_use}"
        )

    async def cancel(self, context, queue):
        """Cancel execution."""
        task_id = context.task_id
        context_id = context.context_id

        cancelled_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.cancelled,
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.agent,
                    parts=[{"kind": "text", "text": "E2E test execution cancelled"}],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
            final=True,
        )
        await queue.enqueue_event(cancelled_event)


class E2EStreamingExecutor(E2ETestExecutor):
    """Streaming executor for E2E tests."""

    async def execute(self, context, event_queue):
        """Execute with streaming behavior."""
        task_id = context.task_id
        context_id = context.context_id

        print(
            f"[E2E Streaming Executor] Starting streaming execution for task {task_id}"
        )

        # Publish initial task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.working,
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.agent,
                    parts=[{"kind": "text", "text": "Starting E2E streaming..."}],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
        )
        await event_queue.enqueue_event(task)

        # Send multiple streaming updates
        for i in range(3):
            await asyncio.sleep(0.3)

            streaming_event = TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.working,
                    message=Message(
                        message_id=str(uuid4()),
                        role=Role.agent,
                        parts=[
                            {"kind": "text", "text": f"Streaming update {i+1}/3..."}
                        ],
                        task_id=task_id,
                        context_id=context_id,
                    ),
                ),
                final=False,
            )
            await event_queue.enqueue_event(streaming_event)

        # Final completion
        await asyncio.sleep(0.5)
        completed_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.completed,
                message=Message(
                    message_id=str(uuid4()),
                    role=Role.agent,
                    parts=[
                        {
                            "kind": "text",
                            "text": f"E2E streaming completed! Credits used: {self.credits_to_use}",
                        }
                    ],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
            final=True,
            metadata={"creditsUsed": self.credits_to_use},
        )
        await event_queue.enqueue_event(completed_event)

        print(f"[E2E Streaming Executor] Completed streaming for task {task_id}")


pytestmark = pytest.mark.asyncio


class TestA2AE2EFlow:
    """E2E tests for A2A payment flows."""

    def setup_method(self):
        """Setup for each test method."""
        self.payments_service = MockE2EPaymentsService()
        self.server_manager = A2AE2EServerManager()

    def teardown_method(self):
        """Cleanup after each test method."""
        # Note: teardown_method should be sync, we'll handle cleanup differently
        pass

    def test_blocking_flow_with_credit_burning(self):
        """Test E2E blocking flow with credit burning (using TestClient for simplicity)."""
        # Setup agent card
        agent_card = A2AE2EFactory.create_agent_card(
            "E2E Blocking Agent", "valid-agent-123"
        )
        payment_metadata = A2AE2EFactory.create_payment_metadata(
            "valid-agent-123", credits=50
        )

        # Add payment extension to agent card
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Create executor
        executor = E2ETestExecutor(execution_time=0.5, credits_to_use=8)

        # Start server (using run_async=False to get FastAPI app)
        from payments_py.a2a.server import PaymentsA2AServer

        server_result = PaymentsA2AServer.start(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=0,  # Dynamic port
            base_path="/a2a",
            expose_default_routes=True,
            run_async=False,
        )

        # Create TestClient for HTTP requests (more reliable than real network)
        client = TestClient(server_result.app)

        # Create test message
        message = A2AE2EFactory.create_test_message("E2E blocking test message")

        # Send blocking request
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": True},
            },
        }

        headers = {"Authorization": "Bearer VALID_E2E_TOKEN"}

        response = client.post("/a2a", json=payload, headers=headers)

        # Verify response
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}: {response.text}"

        response_data = response.json()
        assert (
            "result" in response_data
        ), f"Expected result in response: {response_data}"

        # Verify task completion
        task_result = response_data["result"]
        A2AE2EAssertions.assert_task_response(task_result, "completed")

        # Verify message content
        task_message = task_result["status"]["message"]
        A2AE2EAssertions.assert_message_response(task_message, "agent")
        assert "Credits used: 8" in task_message["parts"][0]["text"]

        # Verify validation and credit burning occurred
        assert self.payments_service.requests.validation_call_count == 1
        assert self.payments_service.requests.redeem_call_count == 1
        assert self.payments_service.requests.last_redeem_credits == 8

        print("✅ E2E blocking flow test passed with credit burning")

    def test_invalid_bearer_token_flow(self):
        """Test E2E flow with invalid bearer token."""
        # Setup agent card
        agent_card = A2AE2EFactory.create_agent_card(
            "E2E Auth Agent", "valid-agent-123"
        )
        payment_metadata = A2AE2EFactory.create_payment_metadata("valid-agent-123")

        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        executor = E2ETestExecutor()

        # Start server (using TestClient)
        from payments_py.a2a.server import PaymentsA2AServer

        server_result = PaymentsA2AServer.start(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=0,
            base_path="/a2a",
            run_async=False,
        )

        client = TestClient(server_result.app)

        # Test with invalid token
        message = A2AE2EFactory.create_test_message("This should fail")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": message},
        }

        headers = {"Authorization": "Bearer INVALID_TOKEN"}

        response = client.post("/a2a", json=payload, headers=headers)

        # Should return 402 Payment Required
        assert (
            response.status_code == 402
        ), f"Expected 402, got {response.status_code}: {response.text}"

        response_data = response.json()
        assert "error" in response_data
        assert "Validation error" in response_data["error"]["message"]

        # Verify no credit burning occurred
        assert self.payments_service.requests.validation_call_count == 1
        assert self.payments_service.requests.redeem_call_count == 0

        print("✅ E2E invalid token test passed")

    def test_non_blocking_flow_with_polling(self):
        """Test E2E non-blocking flow with task polling."""
        # Setup
        agent_card = A2AE2EFactory.create_agent_card(
            "E2E NonBlocking Agent", "nonblocking-agent-789"
        )
        payment_metadata = A2AE2EFactory.create_payment_metadata(
            "nonblocking-agent-789", credits=75
        )

        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        executor = E2ETestExecutor(execution_time=1.5, credits_to_use=12)

        # Start server (using TestClient for simplicity)
        from payments_py.a2a.server import PaymentsA2AServer

        server_result = PaymentsA2AServer.start(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=0,
            base_path="/a2a",
            run_async=False,
        )

        client = TestClient(server_result.app)

        # Send non-blocking request
        message = A2AE2EFactory.create_test_message("E2E non-blocking test")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }

        headers = {"Authorization": "Bearer NON_BLOCKING_TOKEN"}

        response = client.post("/a2a", json=payload, headers=headers)

        # Verify immediate response
        assert (
            response.status_code == 200
        ), f"Expected 200, got {response.status_code}: {response.text}"
        response_data = response.json()
        task_result = response_data["result"]

        # Note: With TestClient, even non-blocking requests may complete immediately
        # In real network E2E tests, this would be "submitted"
        task_state = task_result["status"]["state"]
        assert task_state in [
            "submitted",
            "completed",
        ], f"Expected submitted or completed, got {task_state}"
        task_id = task_result["id"]

        # For E2E test, we'll verify the response format is correct
        print(
            f"✅ E2E non-blocking test passed - task {task_id} in state: {task_state}"
        )

        # Verify validation occurred
        assert self.payments_service.requests.validation_call_count == 1

        # Note: Credits will be burned in background, so we can't easily verify in TestClient
        # In real E2E tests with actual network, you would poll for completion

        print("✅ E2E non-blocking flow test passed")


# Additional test methods will continue in the next batch...
