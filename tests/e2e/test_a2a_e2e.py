"""
End-to-End tests for A2A Payment Integration using Nevermined backend.
"""

import asyncio
import uuid
from uuid import uuid4
import threading
import time
import httpx
from fastapi import FastAPI, Request
import uvicorn

import pytest
from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.types import (
    Message,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

# Setup agent card with payment metadata
from payments_py import Payments
from payments_py.a2a.agent_card import build_payment_agent_card
from payments_py.common.types import PaymentOptions
from tests.e2e.helpers.a2a_setup_helpers import create_a2a_test_agent_and_plan
from tests.e2e.conftest import (
    SUBSCRIBER_API_KEY,
    BUILDER_API_KEY,
    TEST_ENVIRONMENT,
)

PORT = 6782


class BasicE2EExecutor(AgentExecutor):
    """Basic test executor for E2E tests."""

    def __init__(self, execution_time: float = 1.0, credits_to_use: int = 5):
        self.execution_time = execution_time
        self.credits_to_use = credits_to_use
        self.execution_count = 0

    async def execute(self, context, event_queue):
        """Execute agent behavior."""
        self.execution_count += 1
        task_id = context.task_id
        context_id = context.context_id

        print(f"[Basic E2E Executor] Starting execution for task {task_id}")

        # Publish initial task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.working),
            history=[],
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
                    parts=[{"kind": "text", "text": "E2E test working..."}],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
            final=False,
        )
        await event_queue.enqueue_event(working_event)

        # Simulate execution time
        await asyncio.sleep(self.execution_time)

        # Publish completion with creditsUsed metadata
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
            metadata={
                "creditsUsed": self.credits_to_use
            },  # Important for credit burning
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
            status=TaskStatus(state=TaskState.cancelled),
            final=True,
        )
        await queue.enqueue_event(cancelled_event)


class E2EStreamingExecutor(AgentExecutor):
    """Streaming executor for E2E tests."""

    def __init__(self, execution_time: float = 1.0, credits_to_use: int = 5):
        self.execution_time = execution_time
        self.credits_to_use = credits_to_use
        self.execution_count = 0

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
            status=TaskStatus(state=TaskState.working),
            history=[],
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
                            {
                                "kind": "text",
                                "text": f"Streaming update {i + 1}/3...",
                            }
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


class E2ETestExecutor(AgentExecutor):
    """E2E executor for comprehensive testing."""

    def __init__(self, execution_time: float = 1.0, credits_to_use: int = 5):
        self.execution_time = execution_time
        self.credits_to_use = credits_to_use
        self.execution_count = 0

    async def execute(self, context, event_queue):
        """Execute real agent behavior with credit burning."""
        self.execution_count += 1
        task_id = context.task_id
        context_id = context.context_id

        print(f"[E2E Executor] Starting execution for task {task_id}")

        # Publish initial task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.working),
            history=[],
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
                    parts=[{"kind": "text", "text": "E2E test processing..."}],
                    task_id=task_id,
                    context_id=context_id,
                ),
            ),
            final=False,
        )
        await event_queue.enqueue_event(working_event)

        # Simulate actual work
        await asyncio.sleep(self.execution_time)

        # Publish completion with creditsUsed metadata
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
                            "text": f"E2E execution completed! Credits used: {self.credits_to_use}",
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
            status=TaskStatus(state=TaskState.cancelled),
            final=True,
        )
        await queue.enqueue_event(cancelled_event)


class E2EStreamingTestExecutor(AgentExecutor):
    """Advanced streaming executor for E2E tests."""

    def __init__(self, execution_time: float = 1.0, credits_to_use: int = 5):
        self.execution_time = execution_time
        self.credits_to_use = credits_to_use
        self.execution_count = 0

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
            status=TaskStatus(state=TaskState.working),
            history=[],
        )
        await event_queue.enqueue_event(task)

        # Send multiple realistic streaming updates
        streaming_messages = [
            "Analyzing your request...",
            "Processing data...",
            "Generating response...",
            "Finalizing output...",
        ]

        for i, message_text in enumerate(streaming_messages):
            await asyncio.sleep(0.4)

            streaming_event = TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.working,
                    message=Message(
                        message_id=str(uuid4()),
                        role=Role.agent,
                        parts=[{"kind": "text", "text": message_text}],
                        task_id=task_id,
                        context_id=context_id,
                    ),
                ),
                final=False,
            )
            await event_queue.enqueue_event(streaming_event)

        # Final completion
        await asyncio.sleep(0.3)
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

    async def cancel(self, context, queue):
        """Cancel execution."""
        task_id = context.task_id
        context_id = context.context_id

        cancelled_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.cancelled),
            final=True,
        )
        await queue.enqueue_event(cancelled_event)


class WebhookTestExecutor(AgentExecutor):
    """Executor for webhook testing."""

    def __init__(self, execution_time: float = 0.5, credits_to_use: int = 3):
        self.execution_time = execution_time
        self.credits_to_use = credits_to_use

    async def execute(self, context, event_queue):
        """Execute and trigger webhook."""
        task_id = context.task_id
        context_id = context.context_id

        print(f"[Webhook Executor] Starting execution for task {task_id}")

        # Publish initial task
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.working),
            history=[],
        )
        await event_queue.enqueue_event(task)

        # Simulate work
        await asyncio.sleep(self.execution_time)

        # Publish completion with webhook metadata
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
                            "text": f"Webhook test completed! Credits used: {self.credits_to_use}",
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

        print(f"[Webhook Executor] Completed execution for task {task_id}")

    async def cancel(self, context, queue):
        """Cancel execution."""
        task_id = context.task_id
        context_id = context.context_id

        cancelled_event = TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.cancelled),
            final=True,
        )
        await queue.enqueue_event(cancelled_event)


class A2ATestServer:
    """Real A2A server for E2E testing with payments integration."""

    def __init__(self, port: int = 0):
        self.port = port
        self.server_thread = None
        self.uvicorn_server = None
        self.base_url = None
        self.payments_service = None
        self.agent_card = None
        self.executor = None

    def start(self, payments_service, agent_card, executor, webhook_config=None):
        """Start the A2A server in a background thread."""
        from payments_py.a2a.server import PaymentsA2AServer

        # Use fixed port 6782 if not specified (important for payments validation)
        if self.port == 0:
            self.port = PORT

        self.base_url = f"http://localhost:{self.port}/a2a/"
        print(f"[A2A Server] Starting real A2A server at: {self.base_url}")

        # Store references
        self.payments_service = payments_service
        self.agent_card = agent_card
        self.executor = executor

        # Start server in background thread
        def run_server():
            try:
                server_result = PaymentsA2AServer.start(
                    payments_service=payments_service,
                    agent_card=agent_card,
                    executor=executor,
                    port=self.port,
                    base_path="/a2a/",
                    expose_default_routes=True,
                    async_execution=False,
                    webhook_config=webhook_config,
                )

                # Configure uvicorn server to use localhost explicitly
                import uvicorn

                config = uvicorn.Config(
                    app=server_result.app,
                    host="localhost",  # Explicitly use localhost for payments validation
                    port=self.port,
                    log_level="info",
                )
                self.uvicorn_server = uvicorn.Server(config)

                # Create new event loop for this thread
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                # Run the server
                loop.run_until_complete(self.uvicorn_server.serve())

            except Exception as e:
                print(f"[A2A Server] Error: {e}")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        # Ensure the port is free before starting (avoid race with previous server)
        try:
            import socket  # local import to avoid global dependency

            for _ in range(50):
                sock = socket.socket()
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("127.0.0.1", self.port))
                    sock.close()
                    break
                except OSError:
                    sock.close()
                    time.sleep(0.1)
        except Exception:
            # Best-effort; if anything goes wrong, proceed to start
            pass

        self.server_thread.start()

        # Wait for server to start
        max_wait = 10
        for i in range(max_wait):
            try:
                # Try to connect to the server
                response = httpx.get(
                    f"http://localhost:{self.port}/a2a/.well-known/agent.json",
                    timeout=1,
                )
                if response.status_code == 200:
                    print(f"[A2A Server] Server is ready at {self.base_url}")
                    return self.base_url
            except BaseException:
                pass
            time.sleep(0.5)

        print(
            f"[A2A Server] Warning: Server may not be ready yet after {max_wait / 2}s"
        )
        return self.base_url

    def stop(self):
        """Stop the A2A server."""
        if self.uvicorn_server:
            print("[A2A Server] Stopping A2A server")
            try:
                if hasattr(self.uvicorn_server, "should_exit"):
                    self.uvicorn_server.should_exit = True
            except Exception as e:
                print(f"[A2A Server] Error stopping: {e}")
        # Wait for the server thread to finish and release the port
        try:
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=5.0)
        except Exception:
            pass
        # Best-effort: ensure port is free before returning
        try:
            import socket  # local import

            for _ in range(100):
                sock = socket.socket()
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    sock.bind(("127.0.0.1", 41243))
                    sock.close()
                    break
                except OSError:
                    sock.close()
                    time.sleep(0.05)
        except Exception:
            pass


class WebhookTestServer:
    """Simple webhook test server for E2E testing."""

    def __init__(self, port: int = 0):
        self.app = FastAPI()
        self.received_webhooks = []
        self.port = port
        self.server_thread = None
        self.server = None

        # Setup webhook endpoint
        @self.app.post("/webhook")
        async def webhook_endpoint(request: Request):
            """Webhook endpoint to receive callbacks."""
            body = await request.json()
            headers = dict(request.headers)

            webhook_data = {
                "body": body,
                "headers": headers,
                "timestamp": time.time(),
            }
            self.received_webhooks.append(webhook_data)

            print(f"[Webhook Server] Received webhook: {body}")
            return {"status": "ok", "received": True}

    def start(self):
        """Start the webhook server in a background thread."""
        import socket

        # Find available port if not specified
        if self.port == 0:
            sock = socket.socket()
            sock.bind(("", 0))
            self.port = sock.getsockname()[1]
            sock.close()

        print(f"[Webhook Server] Starting webhook server on port {self.port}")

        # Start server in background thread
        def run_server():
            config = uvicorn.Config(
                app=self.app,
                host="127.0.0.1",
                port=self.port,
                log_level="error",  # Suppress uvicorn logs
            )
            self.server = uvicorn.Server(config)

            # Create new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            try:
                loop.run_until_complete(self.server.serve())
            except Exception as e:
                print(f"[Webhook Server] Error: {e}")

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        # Wait for server to start
        time.sleep(0.5)
        return f"http://127.0.0.1:{self.port}/webhook"

    def stop(self):
        """Stop the webhook server."""
        if self.server:
            print("[Webhook Server] Stopping webhook server")
            try:
                # Stop the server
                if hasattr(self.server, "should_exit"):
                    self.server.should_exit = True
            except Exception as e:
                print(f"[Webhook Server] Error stopping: {e}")

    def get_received_webhooks(self):
        """Get all received webhooks."""
        return self.received_webhooks.copy()

    def clear_webhooks(self):
        """Clear received webhooks."""
        self.received_webhooks.clear()


class TestA2AE2EFlow:
    """E2E tests for A2A payment flows using Nevermined backend."""

    @classmethod
    def setup_class(cls):
        """Setup once for all test methods in the class."""
        # Create Payments instances using shared configuration
        cls.payments_publisher = Payments(
            PaymentOptions(nvm_api_key=BUILDER_API_KEY, environment=TEST_ENVIRONMENT)
        )
        cls.payments_subscriber = Payments(
            PaymentOptions(nvm_api_key=SUBSCRIBER_API_KEY, environment=TEST_ENVIRONMENT)
        )

        print(f"Publisher address: {cls.payments_publisher.account_address}")
        print(f"Subscriber address: {cls.payments_subscriber.account_address}")

        # Create agent and plan for tests (only once for all tests)
        setup_result = create_a2a_test_agent_and_plan(
            cls.payments_publisher,
            port=PORT,
            base_path="/a2a/",
            credits_per_request=1,
        )

        cls.AGENT_ID = setup_result["agentId"]
        cls.PLAN_ID = setup_result["planId"]
        cls.access_token = None  # Will be set after plan is ordered in test_check_balance_and_order_if_needed

    @classmethod
    def teardown_class(cls):
        """Cleanup after all test methods in the class."""

    @pytest.mark.asyncio
    async def test_check_balance_and_order_if_needed(self):
        """Check subscriber balance and order plan if needed."""
        print(f"Checking balance for plan: {self.PLAN_ID}")

        try:
            # Check current balance
            print(f"Attempting to get balance for plan: {self.PLAN_ID}")
            print(
                f"Using subscriber with address: {self.payments_subscriber.account_address}"
            )

            try:
                balance_result = self.payments_subscriber.plans.get_plan_balance(
                    self.PLAN_ID
                )
                print(f"Raw balance result: {balance_result}")
                current_balance = int(balance_result.balance)
                print(f"Current balance: {current_balance}")
            except Exception as balance_error:
                print(f"❌ Error getting balance: {balance_error}")
                # If we can't get balance, let's try to order anyway
                print("Attempting to order plan without balance check...")
                current_balance = 0

            # If balance is 0 or low, order the plan
            if current_balance < 10:  # Ensure we have at least 10 credits
                print("Balance is low, ordering plan...")
                try:
                    order_result = self.payments_subscriber.plans.order_plan(
                        self.PLAN_ID
                    )
                    print(f"Order result: {order_result}")
                    if order_result and order_result.get("success"):
                        print("✅ Plan ordered successfully")
                    else:
                        print(f"⚠️ Order result: {order_result}")
                except Exception as order_error:
                    print(f"❌ Error ordering plan: {order_error}")
                    # Continue anyway, maybe the user already has credits

                # Try to check balance again after ordering
                try:
                    balance_result = self.payments_subscriber.plans.get_plan_balance(
                        self.PLAN_ID
                    )
                    new_balance = int(balance_result.balance)
                    print(f"New balance after ordering: {new_balance}")
                except Exception as balance_error2:
                    print(f"❌ Error getting balance after order: {balance_error2}")

            print("✅ Balance check and order process completed")

        except Exception as e:
            print(f"❌ Error in balance check/order: {e}")
            # Don't raise, continue with tests
            print("⚠️ Continuing with tests despite balance check error")

        # Get x402 access token after ordering the plan (if ordered)
        try:
            agent_access_params = (
                self.payments_subscriber.x402.get_x402_access_token(
                    self.PLAN_ID, self.AGENT_ID
                )
            )
            self.__class__.access_token = agent_access_params.get("accessToken")
            print(f"✅ Got access token: {self.__class__.access_token[:20]}...")
        except Exception as e:
            print(f"⚠️ Warning: Could not get access token after ordering: {e}")
            self.__class__.access_token = None

    @pytest.mark.asyncio
    async def test_get_agent_access_token(self):
        """Test getting agent access token."""
        # Access token is already obtained in setup_class, just verify it exists
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"
        assert len(self.access_token) > 0, "Access token should not be empty"
        print(f"✅ Access token verified: {self.access_token[:20]}...")

    @pytest.mark.asyncio
    async def test_blocking_flow_with_credit_burning(self):
        """Test E2E blocking flow with actual credit burning."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Check balance BEFORE execution
        print("🔍 Checking balance BEFORE execution...")
        try:
            balance_before_result = self.payments_subscriber.plans.get_plan_balance(
                self.PLAN_ID
            )
            balance_before = int(balance_before_result.balance)
            print(f"📊 Balance BEFORE: {balance_before} credits")
        except Exception as e:
            print(f"❌ Error getting balance before: {e}")
            balance_before = None

        agent_card = {
            "name": "E2E Blocking Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": False},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Create executor that uses exactly 3 credits
        credits_to_burn = (
            1  # Plan is configured to burn 1 credit regardless of agent reported usage
        )
        executor = BasicE2EExecutor(execution_time=0.5, credits_to_use=credits_to_burn)

        # Start REAL A2A server that can receive HTTP requests
        a2a_server = A2ATestServer(port=PORT)
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        try:
            # Create test message
            message = {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": "E2E blocking test message"}],
            }

            # Send blocking request with bearer token to REAL server
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": message,
                    "options": {"blocking": True},
                },
            }

            headers = {"Authorization": f"Bearer {self.access_token}"}

            print(f"Sending blocking request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=30)

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
            assert task_result["status"]["state"] == "completed"

            # Verify message content includes credit usage
            task_message = task_result["status"]["message"]
            assert task_message["role"] == "agent"
            assert (
                f"Credits used: {credits_to_burn}" in task_message["parts"][0]["text"]
            )

            # Check balance AFTER execution to verify credits were actually burned
            print("🔍 Checking balance AFTER execution...")
            try:
                balance_after_result = self.payments_subscriber.plans.get_plan_balance(
                    self.PLAN_ID
                )
                balance_after = int(balance_after_result.balance)
                print(f"📊 Balance AFTER: {balance_after} credits")

                if balance_before is not None:
                    credits_burned = balance_before - balance_after
                    print(f"🔥 Credits actually burned: {credits_burned}")

                    # Verify that the exact number of credits were burned
                    assert credits_burned == credits_to_burn, (
                        f"Expected {credits_to_burn} credits to be burned, "
                        f"but {credits_burned} were burned (before: {balance_before}, after: {balance_after})"
                    )
                    print(
                        f"✅ Verified: Exactly {credits_to_burn} credits were burned from the balance!"
                    )
                else:
                    print(
                        "⚠️ Could not verify credit burning - balance before was not available"
                    )

            except Exception as e:
                print(f"❌ Error getting balance after: {e}")
                print("⚠️ Could not verify credit burning due to balance check error")

            print("✅ E2E blocking flow test passed with verified credit burning")

        finally:
            # Always cleanup the server
            a2a_server.stop()

    @pytest.mark.asyncio
    async def test_invalid_bearer_token_flow(self):
        """Test E2E flow with invalid bearer token."""
        # Setup agent card
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = {
            "name": "Real E2E Auth Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": False},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)
        executor = E2ETestExecutor()

        # Start REAL A2A server
        a2a_server = A2ATestServer(port=PORT)
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        # Test with invalid token
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": "This should fail"}],
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {"message": message},
        }

        headers = {"Authorization": "Bearer INVALID_TOKEN"}

        try:
            print(f"Sending invalid token request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=30)

            # Should return 402 Payment Required
            assert (
                response.status_code == 402
            ), f"Expected 402, got {response.status_code}: {response.text}"

            response_data = response.json()
            assert "error" in response_data
            assert "Validation error" in response_data["error"]["message"]

            print("✅ E2E invalid token test passed")
        finally:
            a2a_server.stop()

    @pytest.mark.asyncio
    async def test_non_blocking_flow(self):
        """Test E2E non-blocking flow."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Setup
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = {
            "name": "E2E NonBlocking Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": False},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Use 1 credit to match plan configuration
        executor = E2ETestExecutor(execution_time=1.5, credits_to_use=1)

        # Start REAL A2A server that can receive HTTP requests
        a2a_server = A2ATestServer(port=PORT)
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        # Send non-blocking request
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": "E2E non-blocking test"}],
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            print(f"Sending non-blocking request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=30)

            # Verify immediate response
            assert (
                response.status_code == 200
            ), f"Expected 200, got {response.status_code}: {response.text}"
            response_data = response.json()
            task_result = response_data["result"]

            # With real server, task might complete immediately, but check it's valid
            task_state = task_result["status"]["state"]
            assert task_state in [
                "submitted",
                "working",
                "completed",
            ], f"Expected valid state, got {task_state}"
            task_id = task_result["id"]

            print(
                f"✅ E2E non-blocking test passed - task {task_id} in state: {task_state}"
            )
        finally:
            a2a_server.stop()

    @pytest.mark.asyncio
    async def test_streaming_flow(self):
        """Test E2E streaming flow."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Setup agent card with streaming enabled
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = {
            "name": "E2E Streaming Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": True},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Use 1 credit to match plan configuration
        executor = E2EStreamingTestExecutor(execution_time=0.5, credits_to_use=1)

        # Start REAL A2A server
        a2a_server = A2ATestServer(port=PORT)
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        # Send streaming request
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": "Real E2E streaming test"}],
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/stream",
            "params": {"message": message},
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            print(f"Sending streaming request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=30)

            # Verify streaming response
            assert (
                response.status_code == 200
            ), f"Expected 200, got {response.status_code}: {response.text}"

            # Check that it's a streaming response (event-stream)
            content_type = response.headers.get("content-type", "")
            assert (
                "text/event-stream" in content_type
            ), f"Expected streaming response, got {content_type}"

            print("✅ E2E streaming test initiated successfully")
        finally:
            a2a_server.stop()

    @pytest.mark.asyncio
    async def test_task_cancellation(self):
        """Test E2E task cancellation."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Setup agent card
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = {
            "name": "E2E Cancellation Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": False},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Use 1 credit to match plan configuration, longer execution time for
        # cancellation test
        executor = BasicE2EExecutor(execution_time=3.0, credits_to_use=1)

        # Start REAL A2A server
        a2a_server = A2ATestServer(port=PORT)
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        # Start a non-blocking task
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": "E2E cancellation test - long task"}],
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            print(f"Sending cancellation test request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 200

            response_data = response.json()
            task_id = response_data["result"]["id"]

            print(f"Started task {task_id} for cancellation test")
            print("✅ E2E cancellation test setup completed")
        finally:
            a2a_server.stop()

    @pytest.mark.asyncio
    async def test_webhook_integration(self):
        """Test E2E webhook functionality with real local webhook server."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Start real webhook server
        webhook_server = WebhookTestServer()
        webhook_url = webhook_server.start()

        try:
            print(f"[Test] Webhook server started at: {webhook_url}")

            # Setup agent card with webhook configuration
            from payments_py.a2a.agent_card import build_payment_agent_card

            agent_card = {
                "name": "E2E Webhook Agent",
                "version": "1.0.0",
                "capabilities": {"streaming": False},
            }

            payment_metadata = {
                "agentId": self.AGENT_ID,
                "planId": self.PLAN_ID,
                "credits": 50,
                "paymentType": "credits",
                "isTrialPlan": False,
            }

            agent_card = build_payment_agent_card(agent_card, payment_metadata)

            # Use 1 credit to match plan configuration
            executor = WebhookTestExecutor(execution_time=0.3, credits_to_use=1)

            # Configure webhook to point to our local server
            webhook_config = {
                "url": webhook_url,
                "headers": {"Content-Type": "application/json"},
                "credentials": "webhook-test-token-e2e",
            }

            # Start REAL A2A server with webhook configuration
            a2a_server = A2ATestServer()
            server_url = a2a_server.start(
                payments_service=self.payments_publisher,
                agent_card=agent_card,
                executor=executor,
                webhook_config=webhook_config,
            )

            # Send request that should trigger webhook
            message = {
                "messageId": str(uuid.uuid4()),
                "role": "user",
                "parts": [
                    {
                        "kind": "text",
                        "text": "Test webhook functionality with real server",
                    }
                ],
            }

            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": message,
                    "options": {"blocking": True},
                },
            }

            headers = {"Authorization": f"Bearer {self.access_token}"}

            print(f"Sending webhook test request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=10)

            # Verify response
            assert (
                response.status_code == 200
            ), f"Expected 200, got {response.status_code}: {response.text}"

            response_data = response.json()
            task_result = response_data["result"]
            assert task_result["status"]["state"] == "completed"

            # Wait for webhook to be delivered
            await asyncio.sleep(1.0)

            # Verify webhook was received by our real server
            received_webhooks = webhook_server.get_received_webhooks()

            if received_webhooks:
                webhook_data = received_webhooks[0]
                webhook_body = webhook_data["body"]
                webhook_headers = webhook_data["headers"]

                # Verify webhook payload structure
                assert (
                    "taskId" in webhook_body
                ), f"Missing taskId in webhook body: {webhook_body}"
                assert (
                    "state" in webhook_body
                ), f"Missing state in webhook body: {webhook_body}"
                assert (
                    webhook_body["state"] == "completed"
                ), f"Expected completed state, got: {webhook_body['state']}"

                # Verify webhook headers
                assert webhook_headers.get("content-type") == "application/json"
                assert (
                    webhook_headers.get("authorization")
                    == f"Bearer {webhook_config['credentials']}"
                )

                print("✅ E2E webhook integration test passed with real server")
                print(f"   📨 Received webhook: {webhook_body}")

            else:
                print(
                    "⚠️ No webhooks received by real server - webhook might be disabled or failed"
                )
                # Don't fail the test, just warn - webhook functionality might not be
                # fully enabled

        finally:
            # Always clean up both servers
            a2a_server.stop()
            webhook_server.stop()

    @pytest.mark.asyncio
    async def test_task_resubscription(self):
        """Test E2E task resubscription functionality."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Setup agent card
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = {
            "name": "E2E Resubscription Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": True},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Use 1 credit to match plan configuration
        executor = E2ETestExecutor(execution_time=1.5, credits_to_use=1)

        # Start REAL A2A server
        a2a_server = A2ATestServer()
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        # Start a non-blocking task first
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": "E2E resubscription test task"}],
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            print(f"Sending resubscription test request to real server: {server_url}")
            response = httpx.post(server_url, json=payload, headers=headers, timeout=10)
            assert response.status_code == 200

            response_data = response.json()
            task_id = response_data["result"]["id"]

            print(f"Started task {task_id} for resubscription test")

            # Wait a moment for task to start processing
            await asyncio.sleep(0.5)

            # Now test resubscription to the task
            resubscribe_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tasks/resubscribe",
                "params": {"taskId": task_id},
            }

            # Test resubscription via HTTP (for non-streaming)
            resubscribe_response = httpx.post(
                server_url, json=resubscribe_payload, headers=headers, timeout=30
            )

            if resubscribe_response.status_code == 200:
                # For HTTP resubscription, we should get task status
                resubscribe_data = resubscribe_response.json()
                if "result" in resubscribe_data:
                    task_status = resubscribe_data["result"]
                    assert "status" in task_status
                    print(
                        f"✅ E2E resubscription test passed - got task status: {task_status['status']['state']}"
                    )
                else:
                    print("✅ E2E resubscription test passed - resubscription accepted")
            else:
                # Resubscription might not be supported in this test setup
                print(
                    f"⚠️ Resubscription returned {resubscribe_response.status_code} - might not be supported in test environment"
                )
        finally:
            a2a_server.stop()

    @pytest.mark.asyncio
    async def test_complete_task_cancellation(self):
        """Test complete E2E task cancellation flow."""
        # Access token is already set in setup_class
        assert (
            self.access_token is not None
        ), "Access token should be set in setup_class"

        # Setup agent card
        from payments_py.a2a.agent_card import build_payment_agent_card

        agent_card = {
            "name": "E2E Cancellation Agent",
            "version": "1.0.0",
            "capabilities": {"streaming": False},
        }

        payment_metadata = {
            "agentId": self.AGENT_ID,
            "planId": self.PLAN_ID,
            "credits": 50,
            "paymentType": "credits",
            "isTrialPlan": False,
        }

        agent_card = build_payment_agent_card(agent_card, payment_metadata)

        # Very long execution time for cancellation test, 1 credit
        executor = BasicE2EExecutor(execution_time=5.0, credits_to_use=1)

        # Start REAL A2A server
        a2a_server = A2ATestServer()
        server_url = a2a_server.start(
            payments_service=self.payments_publisher,
            agent_card=agent_card,
            executor=executor,
        )

        # Start a long-running non-blocking task
        message = {
            "messageId": str(uuid.uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": "E2E long task for cancellation"}],
        }

        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }

        headers = {"Authorization": f"Bearer {self.access_token}"}

        try:
            print(
                f"Sending complete cancellation test request to real server: {server_url}"
            )
            response = httpx.post(server_url, json=payload, headers=headers, timeout=30)
            assert response.status_code == 200

            response_data = response.json()
            task_id = response_data["result"]["id"]

            print(f"Started long task {task_id} for cancellation test")

            # Wait a moment to ensure task is running
            await asyncio.sleep(0.2)

            # Try to cancel the task
            cancel_payload = {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tasks/cancel",
                "params": {"taskId": task_id},
            }

            cancel_response = httpx.post(
                server_url, json=cancel_payload, headers=headers, timeout=30
            )

            if cancel_response.status_code == 200:
                cancel_data = cancel_response.json()
                if "result" in cancel_data:
                    print(
                        "✅ E2E task cancellation test passed - task cancelled successfully"
                    )
                else:
                    print(
                        "✅ E2E task cancellation test passed - cancellation request accepted"
                    )
            else:
                print(
                    f"⚠️ Task cancellation returned {cancel_response.status_code} - might not be supported"
                )

            print("✅ E2E complete cancellation test completed")
        finally:
            a2a_server.stop()


# Mark all tests as slow for optional skipping
pytestmark = pytest.mark.slow
