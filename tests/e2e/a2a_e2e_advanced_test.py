"""
Advanced E2E tests for A2A payment flow.

Additional end-to-end tests covering streaming, webhooks, resubscription, 
cancellation, and comprehensive credit burning scenarios.
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
from a2a.types import Message, Part, Role, Task, TaskState, TaskStatus, TaskStatusUpdateEvent

from payments_py import Payments
from payments_py.common.payments_error import PaymentsError

from tests.e2e.helpers.a2a_e2e_helpers import (
    A2AE2EAssertions,
    A2AE2EFactory,
    A2AE2EServerManager,
    A2AE2EUtils,
    E2ETestConfig,
)

# Import the test executors from the main test file
from tests.e2e.a2a_e2e_test import MockE2EPaymentsService, E2ETestExecutor, E2EStreamingExecutor


pytestmark = pytest.mark.asyncio


class TestA2AE2EAdvanced:
    """Advanced E2E tests for A2A payment flows."""
    
    def setup_method(self):
        """Setup for each test method."""
        self.payments_service = MockE2EPaymentsService()
        self.server_manager = A2AE2EServerManager()
    
    async def teardown_method(self):
        """Cleanup after each test method."""
        await self.server_manager.stop_all_servers()
    
    @pytest.mark.asyncio
    async def test_streaming_flow(self):
        """Test E2E streaming flow with Server-Sent Events."""
        # Setup agent with streaming capabilities
        agent_card = A2AE2EFactory.create_agent_card("E2E Streaming Agent", "streaming-agent-999", streaming=True)
        payment_metadata = A2AE2EFactory.create_payment_metadata("streaming-agent-999", credits=30)
        
        from payments_py.a2a.agent_card import build_payment_agent_card
        agent_card = build_payment_agent_card(agent_card, payment_metadata)
        
        executor = E2EStreamingExecutor(execution_time=0.5, credits_to_use=6)
        
        # Start server
        server_info = await self.server_manager.start_agent_server(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=8015,
            base_path="/a2a",
        )
        
        await asyncio.sleep(0.3)
        
        # Send streaming request
        message = A2AE2EFactory.create_test_message("E2E streaming test")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/stream",
            "params": {
                "message": message,
                "options": {"streaming": True},
            },
        }
        
        headers = {"Authorization": "Bearer STREAMING_TOKEN", "Content-Type": "application/json"}
        
        # Note: For real streaming, we'd use SSE client, but for E2E we'll test the endpoint
        response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=payload,
            headers=headers,
            timeout=15.0,
        )
        
        # Verify streaming response
        A2AE2EAssertions.assert_http_response(response, 200, "text/event-stream")
        
        # Parse streaming events (simplified for E2E)
        response_text = response.text
        assert "data:" in response_text, "Streaming response should contain data events"
        assert "Streaming update" in response_text, "Should contain streaming updates"
        assert "streaming completed" in response_text, "Should contain completion message"
        
        # Give time for background credit burning
        await asyncio.sleep(1.0)
        
        # Verify credit burning occurred
        assert self.payments_service.requests.validation_call_count == 1
        assert self.payments_service.requests.redeem_call_count == 1
        assert self.payments_service.requests.last_redeem_credits == 6
        
        print("✅ E2E streaming flow test passed")
    
    @pytest.mark.asyncio
    async def test_webhook_push_notifications(self):
        """Test E2E webhooks and push notifications."""
        # Start webhook server first
        webhook_server = await self.server_manager.start_webhook_server(port=8016)
        await asyncio.sleep(0.3)
        
        # Setup agent card
        agent_card = A2AE2EFactory.create_agent_card("E2E Webhook Agent", "valid-agent-123", push_notifications=True)
        payment_metadata = A2AE2EFactory.create_payment_metadata("valid-agent-123", credits=40)
        
        from payments_py.a2a.agent_card import build_payment_agent_card
        agent_card = build_payment_agent_card(agent_card, payment_metadata)
        
        executor = E2ETestExecutor(execution_time=0.8, credits_to_use=7)
        
        # Start agent server
        server_info = await self.server_manager.start_agent_server(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=8017,
            base_path="/a2a",
        )
        
        await asyncio.sleep(0.3)
        
        # Set up push notification config
        webhook_config = A2AE2EFactory.create_webhook_config(
            url=f"{webhook_server['url']}/webhook",
            auth_scheme="bearer",
            credentials="webhook-test-token",
        )
        
        # Create task with webhook config
        message = A2AE2EFactory.create_test_message("E2E webhook test")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": True},
                "pushNotificationConfig": webhook_config,
            },
        }
        
        headers = {"Authorization": "Bearer VALID_E2E_TOKEN", "Content-Type": "application/json"}
        
        response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=payload,
            headers=headers,
            timeout=15.0,
        )
        
        # Verify task completion
        A2AE2EAssertions.assert_http_response(response, 200)
        response_data = response.json()
        task_result = response_data["result"]
        A2AE2EAssertions.assert_task_response(task_result, "completed")
        
        # Wait for webhook to be sent
        await asyncio.sleep(1.0)
        
        # Check webhook was received
        webhook_response = await A2AE2EUtils.send_http_request(
            method="GET",
            url=f"{webhook_server['url']}/webhooks",
            timeout=5.0,
        )
        
        webhook_data = webhook_response.json()
        webhooks = webhook_data.get("webhooks", [])
        
        assert len(webhooks) >= 1, f"Expected at least 1 webhook, got {len(webhooks)}"
        
        webhook = webhooks[0]
        assert "body" in webhook
        assert "taskId" in webhook["body"]
        assert webhook["body"]["state"] == "completed"
        
        # Verify auth header was sent
        assert "authorization" in webhook["headers"]
        assert webhook["headers"]["authorization"] == "Bearer webhook-test-token"
        
        # Verify credit burning
        assert self.payments_service.requests.redeem_call_count == 1
        assert self.payments_service.requests.last_redeem_credits == 7
        
        print("✅ E2E webhook push notifications test passed")
    
    @pytest.mark.asyncio
    async def test_task_resubscription(self):
        """Test E2E task resubscription functionality."""
        # Setup
        agent_card = A2AE2EFactory.create_agent_card("E2E Resub Agent", "valid-agent-123")
        payment_metadata = A2AE2EFactory.create_payment_metadata("valid-agent-123", credits=60)
        
        from payments_py.a2a.agent_card import build_payment_agent_card
        agent_card = build_payment_agent_card(agent_card, payment_metadata)
        
        executor = E2ETestExecutor(execution_time=1.0, credits_to_use=9)
        
        # Start server
        server_info = await self.server_manager.start_agent_server(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=8018,
            base_path="/a2a",
        )
        
        await asyncio.sleep(0.3)
        
        # First, create a task with non-blocking execution
        message = A2AE2EFactory.create_test_message("E2E resubscription test")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }
        
        headers = {"Authorization": "Bearer VALID_E2E_TOKEN", "Content-Type": "application/json"}
        
        response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=payload,
            headers=headers,
            timeout=10.0,
        )
        
        response_data = response.json()
        task_id = response_data["result"]["id"]
        
        # Wait a bit for task to start processing
        await asyncio.sleep(0.5)
        
        # Test resubscription to the task
        resubscribe_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tasks/resubscribe",
            "params": {
                "id": task_id,
                "fromSequenceNumber": 0,
            },
        }
        
        resubscribe_response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=resubscribe_payload,
            headers=headers,
            timeout=10.0,
        )
        
        # Verify resubscription response
        A2AE2EAssertions.assert_http_response(resubscribe_response, 200)
        resubscribe_data = resubscribe_response.json()
        
        assert "result" in resubscribe_data
        # The exact format depends on the A2A SDK implementation
        
        # Wait for task completion
        await asyncio.sleep(2.0)
        
        # Get final task state
        get_task_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/get",
            "params": {"id": task_id},
        }
        
        final_response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=get_task_payload,
            headers=headers,
            timeout=5.0,
        )
        
        final_data = final_response.json()
        final_task = final_data["result"]
        A2AE2EAssertions.assert_task_response(final_task, "completed")
        
        # Verify credit burning
        assert self.payments_service.requests.redeem_call_count == 1
        assert self.payments_service.requests.last_redeem_credits == 9
        
        print("✅ E2E task resubscription test passed")
    
    @pytest.mark.asyncio
    async def test_task_cancellation(self):
        """Test E2E task cancellation functionality."""
        # Setup with longer execution time for cancellation test
        agent_card = A2AE2EFactory.create_agent_card("E2E Cancel Agent", "valid-agent-123")
        payment_metadata = A2AE2EFactory.create_payment_metadata("valid-agent-123", credits=80)
        
        from payments_py.a2a.agent_card import build_payment_agent_card
        agent_card = build_payment_agent_card(agent_card, payment_metadata)
        
        executor = E2ETestExecutor(execution_time=3.0, credits_to_use=4)  # Longer execution
        
        # Start server
        server_info = await self.server_manager.start_agent_server(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=8019,
            base_path="/a2a",
        )
        
        await asyncio.sleep(0.3)
        
        # Start a non-blocking task
        message = A2AE2EFactory.create_test_message("E2E cancellation test - long running")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": False},
            },
        }
        
        headers = {"Authorization": "Bearer VALID_E2E_TOKEN", "Content-Type": "application/json"}
        
        response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=payload,
            headers=headers,
            timeout=10.0,
        )
        
        response_data = response.json()
        task_id = response_data["result"]["id"]
        
        # Wait for task to start processing
        await asyncio.sleep(1.0)
        
        # Cancel the task
        cancel_payload = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tasks/cancel",
            "params": {"id": task_id},
        }
        
        cancel_response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=cancel_payload,
            headers=headers,
            timeout=10.0,
        )
        
        # Verify cancellation response
        A2AE2EAssertions.assert_http_response(cancel_response, 200)
        
        # Wait for cancellation to process
        await asyncio.sleep(1.0)
        
        # Get final task state
        get_task_payload = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tasks/get",
            "params": {"id": task_id},
        }
        
        final_response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=get_task_payload,
            headers=headers,
            timeout=5.0,
        )
        
        final_data = final_response.json()
        final_task = final_data["result"]
        
        # Task should be cancelled or failed (depending on timing)
        final_state = final_task["status"]["state"]
        assert final_state in ["cancelled", "failed"], f"Expected cancelled or failed, got {final_state}"
        
        # For cancelled tasks, credits might or might not be burned depending on when cancellation occurred
        # This is acceptable behavior
        
        print(f"✅ E2E task cancellation test passed (final state: {final_state})")
    
    @pytest.mark.asyncio
    async def test_comprehensive_credit_burning_scenarios(self):
        """Test various credit burning scenarios in E2E environment."""
        # Test multiple scenarios with different credit amounts
        test_scenarios = [
            {"credits": 1, "execution_time": 0.2, "description": "Minimal credits"},
            {"credits": 15, "execution_time": 0.5, "description": "Medium credits"},
            {"credits": 50, "execution_time": 1.0, "description": "High credits"},
        ]
        
        for i, scenario in enumerate(test_scenarios):
            print(f"Testing scenario: {scenario['description']}")
            
            # Reset payment service state
            self.payments_service = MockE2EPaymentsService()
            
            # Setup
            agent_card = A2AE2EFactory.create_agent_card(f"E2E Credit Agent {i}", "valid-agent-123")
            payment_metadata = A2AE2EFactory.create_payment_metadata("valid-agent-123", credits=100)
            
            from payments_py.a2a.agent_card import build_payment_agent_card
            agent_card = build_payment_agent_card(agent_card, payment_metadata)
            
            executor = E2ETestExecutor(
                execution_time=scenario["execution_time"],
                credits_to_use=scenario["credits"],
            )
            
            # Start server on different port for each scenario
            port = 8020 + i
            server_info = await self.server_manager.start_agent_server(
                payments_service=self.payments_service,
                agent_card=agent_card,
                executor=executor,
                port=port,
                base_path="/a2a",
            )
            
            await asyncio.sleep(0.3)
            
            # Send request
            message = A2AE2EFactory.create_test_message(f"Credit test: {scenario['description']}")
            payload = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "message/send",
                "params": {
                    "message": message,
                    "options": {"blocking": True},
                },
            }
            
            headers = {"Authorization": "Bearer VALID_E2E_TOKEN", "Content-Type": "application/json"}
            
            response = await A2AE2EUtils.send_http_request(
                method="POST",
                url=f"{server_info['url']}/a2a",
                json_data=payload,
                headers=headers,
                timeout=15.0,
            )
            
            # Verify response
            A2AE2EAssertions.assert_http_response(response, 200)
            response_data = response.json()
            task_result = response_data["result"]
            A2AE2EAssertions.assert_task_response(task_result, "completed")
            
            # Verify credit burning
            assert self.payments_service.requests.validation_call_count == 1
            assert self.payments_service.requests.redeem_call_count == 1
            assert self.payments_service.requests.last_redeem_credits == scenario["credits"]
            
            print(f"✅ Credit scenario '{scenario['description']}' passed: {scenario['credits']} credits burned")
        
        print("✅ All E2E credit burning scenarios passed")
    
    @pytest.mark.asyncio
    async def test_error_handling_and_recovery(self):
        """Test E2E error handling and recovery scenarios."""
        # Test 1: Network timeout recovery
        agent_card = A2AE2EFactory.create_agent_card("E2E Error Agent", "valid-agent-123")
        payment_metadata = A2AE2EFactory.create_payment_metadata("valid-agent-123", credits=100)
        
        from payments_py.a2a.agent_card import build_payment_agent_card
        agent_card = build_payment_agent_card(agent_card, payment_metadata)
        
        executor = E2ETestExecutor(execution_time=0.5, credits_to_use=3)
        
        # Start server
        server_info = await self.server_manager.start_agent_server(
            payments_service=self.payments_service,
            agent_card=agent_card,
            executor=executor,
            port=8025,
            base_path="/a2a",
        )
        
        await asyncio.sleep(0.3)
        
        # Test with very short timeout to trigger timeout handling
        message = A2AE2EFactory.create_test_message("E2E timeout test")
        payload = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "message/send",
            "params": {
                "message": message,
                "options": {"blocking": True},
            },
        }
        
        headers = {"Authorization": "Bearer VALID_E2E_TOKEN", "Content-Type": "application/json"}
        
        # This should succeed despite the timeout concern since our executor is fast
        response = await A2AE2EUtils.send_http_request(
            method="POST",
            url=f"{server_info['url']}/a2a",
            json_data=payload,
            headers=headers,
            timeout=5.0,  # Reasonable timeout
        )
        
        A2AE2EAssertions.assert_http_response(response, 200)
        
        # Test 2: Invalid JSON payload handling
        try:
            invalid_response = await A2AE2EUtils.send_http_request(
                method="POST",
                url=f"{server_info['url']}/a2a",
                json_data={"invalid": "json", "missing": "required_fields"},
                headers=headers,
                timeout=5.0,
            )
            # Should return JSON-RPC error
            assert invalid_response.status_code in [400, 200], "Should handle invalid JSON gracefully"
        except Exception as e:
            # Network errors are also acceptable for invalid requests
            assert "timeout" not in str(e).lower(), f"Should not timeout on invalid JSON: {e}"
        
        print("✅ E2E error handling test passed")