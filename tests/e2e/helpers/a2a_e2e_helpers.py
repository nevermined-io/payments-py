"""
E2E test helpers for A2A functionality.

This module provides utilities, factories, and assertions for E2E testing
of A2A payment flows with real network requests.
"""

import asyncio
import logging
import os
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import uuid4

import httpx
from payments_py import Payments
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config


@dataclass
class E2ETestConfig:
    """Configuration for E2E tests."""

    BUILDER_API_KEY: str = os.getenv("E2E_BUILDER_API_KEY", "test-builder-key")
    SUBSCRIBER_API_KEY: str = os.getenv("E2E_SUBSCRIBER_API_KEY", "test-subscriber-key")
    TIMEOUT: int = 30
    SERVER_STARTUP_TIMEOUT: int = 10
    RETRY_ATTEMPTS: int = 3
    RETRY_DELAY: float = 1.0

    # Test server URLs
    AGENT_SERVER_URL: str = "http://localhost:8001"
    WEBHOOK_SERVER_URL: str = "http://localhost:8002"

    # Network config
    NETWORK_RETRY_ATTEMPTS: int = 5
    NETWORK_RETRY_DELAY: float = 2.0


class A2AE2EUtils:
    """Utilities for A2A E2E testing."""

    @staticmethod
    def create_payments_instance(
        api_key: str, environment: str = "testing"
    ) -> Payments:
        """Create a Payments instance for E2E testing."""
        return Payments(api_key=api_key, environment=environment)

    @staticmethod
    async def retry_with_backoff(
        operation,
        operation_name: str,
        max_attempts: int = 3,
        base_delay: float = 1.0,
    ) -> Any:
        """Retry an operation with exponential backoff."""
        last_exception = None

        for attempt in range(max_attempts):
            try:
                return await operation()
            except Exception as e:
                last_exception = e
                if attempt < max_attempts - 1:
                    delay = base_delay * (2**attempt)
                    logging.warning(
                        f"{operation_name} attempt {attempt + 1} failed, retrying in {delay}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logging.error(
                        f"{operation_name} failed after {max_attempts} attempts"
                    )

        raise last_exception

    @staticmethod
    async def wait_for_server_ready(url: str, timeout: int = 10) -> bool:
        """Wait for a server to be ready."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # Try a simple JSON-RPC ping instead of health check
                async with httpx.AsyncClient() as client:
                    ping_payload = {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "ping",
                        "params": {},
                    }
                    response = await client.post(
                        url,
                        json=ping_payload,
                        timeout=3.0,
                        headers={"Content-Type": "application/json"},
                    )
                    # Even if ping fails (no auth), server is running if we get a response
                    if response.status_code in [200, 401, 402]:
                        return True
            except Exception:
                pass

            await asyncio.sleep(0.5)

        return False

    @staticmethod
    async def send_http_request(
        method: str,
        url: str,
        json_data: Optional[Dict] = None,
        headers: Optional[Dict[str, str]] = None,
        timeout: float = 10.0,
    ) -> httpx.Response:
        """Send HTTP request with proper error handling."""
        async with httpx.AsyncClient() as client:
            return await client.request(
                method=method,
                url=url,
                json=json_data,
                headers=headers,
                timeout=timeout,
            )


class A2AE2EFactory:
    """Factory for creating test objects."""

    @staticmethod
    def create_test_message(
        content: str, message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a test message for A2A communication."""
        return {
            "messageId": message_id or str(uuid4()),
            "contextId": str(uuid4()),
            "role": "user",
            "parts": [{"kind": "text", "text": content}],
        }

    @staticmethod
    def create_payment_metadata(
        agent_id: str,
        credits: int = 100,
        plan_id: Optional[str] = None,
        payment_type: str = "credits",
    ) -> Dict[str, Any]:
        """Create payment metadata for agent card."""
        return {
            "agentId": agent_id,
            "credits": credits,
            "planId": plan_id or "test-plan",
            "paymentType": payment_type,
        }

    @staticmethod
    def create_agent_card(
        name: str,
        agent_id: str,
        streaming: bool = True,
        push_notifications: bool = True,
    ) -> Dict[str, Any]:
        """Create a test agent card."""
        return {
            "name": name,
            "description": f"Test agent {name}",
            "capabilities": {
                "streaming": streaming,
                "pushNotifications": push_notifications,
                "stateTransitionHistory": True,
                "extensions": [],
            },
            "defaultInputModes": ["text"],
            "defaultOutputModes": ["text"],
            "skills": [],
            "url": f"http://localhost:8001/{agent_id}",
            "version": "1.0.0",
        }

    @staticmethod
    def create_webhook_config(
        url: str,
        auth_scheme: str = "bearer",
        credentials: str = "test-token",
    ) -> Dict[str, Any]:
        """Create webhook configuration for push notifications."""
        return {
            "url": url,
            "authentication": {
                "schemes": [auth_scheme],
                "credentials": credentials,
            },
        }


class A2AE2EAssertions:
    """Assertions for A2A E2E testing."""

    @staticmethod
    def assert_valid_client(client: Any) -> None:
        """Assert that a client is valid."""
        assert client is not None, "Client should not be None"
        assert hasattr(client, "send_message"), "Client should have send_message method"
        assert hasattr(
            client, "send_message_stream"
        ), "Client should have send_message_stream method"
        assert hasattr(client, "get_task"), "Client should have get_task method"

    @staticmethod
    def assert_valid_a2a_response(response: Any) -> None:
        """Assert that an A2A response is valid."""
        assert response is not None, "Response should not be None"
        # Add more specific assertions based on expected response structure

    @staticmethod
    def assert_valid_agent_card(agent_card: Dict[str, Any]) -> None:
        """Assert that an agent card is valid."""
        assert "name" in agent_card, "Agent card should have name"
        assert "capabilities" in agent_card, "Agent card should have capabilities"

        if "extensions" in agent_card.get("capabilities", {}):
            extensions = agent_card["capabilities"]["extensions"]
            if extensions:
                payment_ext = next(
                    (
                        ext
                        for ext in extensions
                        if ext.get("uri") == "urn:nevermined:payment"
                    ),
                    None,
                )
                if payment_ext:
                    params = payment_ext.get("params", {})
                    assert "agentId" in params, "Payment extension should have agentId"
                    assert "credits" in params, "Payment extension should have credits"
                    assert (
                        "paymentType" in params
                    ), "Payment extension should have paymentType"

    @staticmethod
    def assert_task_response(response: Dict[str, Any], expected_state: str) -> None:
        """Assert task response structure and state."""
        assert "kind" in response, "Response should have kind field"
        assert response["kind"] == "task", f"Expected task, got {response['kind']}"
        assert "status" in response, "Task should have status"
        assert "state" in response["status"], "Task status should have state"
        assert (
            response["status"]["state"] == expected_state
        ), f"Expected state {expected_state}, got {response['status']['state']}"

    @staticmethod
    def assert_message_response(
        response: Dict[str, Any], expected_role: str = "agent"
    ) -> None:
        """Assert message response structure and role."""
        assert "kind" in response, "Response should have kind field"
        assert (
            response["kind"] == "message"
        ), f"Expected message, got {response['kind']}"
        assert "role" in response, "Message should have role"
        assert (
            response["role"] == expected_role
        ), f"Expected role {expected_role}, got {response['role']}"
        assert "parts" in response, "Message should have parts"
        assert len(response["parts"]) > 0, "Message should have at least one part"

    @staticmethod
    def assert_http_response(
        response: httpx.Response,
        expected_status: int,
        expected_content_type: Optional[str] = None,
    ) -> None:
        """Assert HTTP response properties."""
        assert (
            response.status_code == expected_status
        ), f"Expected status {expected_status}, got {response.status_code}. Response: {response.text}"

        if expected_content_type:
            content_type = response.headers.get("content-type", "")
            assert (
                expected_content_type in content_type
            ), f"Expected content type {expected_content_type}, got {content_type}"


class A2AE2EServerManager:
    """Manager for A2A test servers."""

    def __init__(self):
        self.running_servers: List[Dict[str, Any]] = []

    async def start_agent_server(
        self,
        payments_service: Any,
        agent_card: Dict[str, Any],
        executor: Any,
        port: int = 8001,
        **kwargs,
    ) -> Dict[str, Any]:
        """Start an A2A agent server for testing."""
        from payments_py.a2a.server import PaymentsA2AServer

        server_config = {
            "payments_service": payments_service,
            "agent_card": agent_card,
            "executor": executor,
            "port": port,
            "run_async": False,  # Simplified: use blocking mode for E2E tests
            **kwargs,
        }

        server_result = PaymentsA2AServer.start(**server_config)

        # For run_async=False, the server runs synchronously and we get an app
        server_url = f"http://localhost:{port}"

        server_info = {
            "server_result": server_result,
            "url": server_url,
            "port": port,
            "config": server_config,
        }

        self.running_servers.append(server_info)
        return server_info

    async def start_webhook_server(self, port: int = 8002) -> Dict[str, Any]:
        """Start a webhook server for testing push notifications."""
        import uvicorn
        from fastapi import FastAPI, Request

        app = FastAPI()
        received_webhooks = []

        @app.post("/webhook")
        async def webhook_handler(request: Request):
            body = await request.json()
            headers = dict(request.headers)
            received_webhooks.append(
                {
                    "body": body,
                    "headers": headers,
                    "timestamp": time.time(),
                }
            )
            return {"status": "received"}

        @app.get("/health")
        async def health_check():
            return {"status": "ok"}

        @app.get("/webhooks")
        async def get_webhooks():
            return {"webhooks": received_webhooks}

        # Start server in background
        config = uvicorn.Config(app, host="localhost", port=port, log_level="error")
        server = uvicorn.Server(config)

        # Note: In real E2E tests, you might want to use a proper background server
        # This is a simplified version for demonstration

        server_info = {
            "app": app,
            "server": server,
            "url": f"http://localhost:{port}",
            "port": port,
            "received_webhooks": received_webhooks,
        }

        self.running_servers.append(server_info)
        return server_info

    async def stop_all_servers(self) -> None:
        """Stop all running servers."""
        for server_info in self.running_servers:
            try:
                if "server" in server_info:
                    await server_info["server"].shutdown()
                elif "server_result" in server_info and hasattr(
                    server_info["server_result"], "stop"
                ):
                    await server_info["server_result"].stop()
            except Exception as e:
                logging.warning(f"Failed to stop server: {e}")

        self.running_servers.clear()
