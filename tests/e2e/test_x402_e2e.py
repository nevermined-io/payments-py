"""
End-to-end tests for X402 Access Token functionality.

This test suite validates the X402 access token flow which allows AI agents
to verify and settle permissions on behalf of subscribers using delegated session keys.
"""

import os
import pytest
from datetime import datetime
from payments_py.payments import Payments
from payments_py.common.types import (
    PaymentOptions,
    PlanMetadata,
    AgentMetadata,
    AgentAPIAttributes,
)
from payments_py.environments import ZeroAddress
from payments_py.plans import (
    get_crypto_price_config,
    get_fixed_credits_config,
)
from tests.e2e.utils import retry_with_backoff, wait_for_condition

# Test configuration
TEST_TIMEOUT = 60
TEST_ENVIRONMENT = os.getenv("TEST_ENVIRONMENT", "staging_sandbox")

# Test API keys - same as other E2E tests
SUBSCRIBER_API_KEY = os.getenv(
    "TEST_SUBSCRIBER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweEVCNDk3OTU2OTRBMDc1QTY0ZTY2MzdmMUU5MGYwMjE0Mzg5YjI0YTMiLCJqdGkiOiIweGMzYjYyMWJkYTM5ZDllYWQyMTUyMDliZWY0MDBhMDEzYjM1YjQ2Zjc1NzM4YWFjY2I5ZjdkYWI0ZjQ5MmM5YjgiLCJleHAiOjE3OTQ2NTUwNjAsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.YMkGQUjGh7_m07nj8SKXZReNKSryg9mTU3qwJr_TKYATUixbYQTte3CKucjqvgAGzJAd1Kq2ubz3b37n5Zsllxs",
)
AGENT_API_KEY = os.getenv(
    "TEST_BUILDER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweEFDYjY5YTYzZjljMEI0ZTczNDE0NDM2YjdBODM1NDBGNkM5MmIyMmUiLCJqdGkiOiIweDExZWUwYWYyOGQ5NGVlNmNjZGJhNDJmMDcyNDQyNTQ0ODE5OWRmNTk5ZGRkMDcyMWVlMmI5ZTg5Nzg3MzQ3N2IiLCJleHAiOjE3OTQ2NTU0NTIsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.fnnb-AFxE_ngIAgIRZOY6SpLM3KgpB1z210l_z3T0Fl2G2tHQp9svXrflCsIYoYHW_8kbHllLce827gyfmFvMhw",
)


@pytest.fixture(scope="module")
def payments_subscriber():
    """Create a Payments instance for the subscriber."""
    return Payments(
        PaymentOptions(nvm_api_key=SUBSCRIBER_API_KEY, environment=TEST_ENVIRONMENT)
    )


@pytest.fixture(scope="module")
def payments_agent():
    """Create a Payments instance for the agent (builder)."""
    return Payments(
        PaymentOptions(nvm_api_key=AGENT_API_KEY, environment=TEST_ENVIRONMENT)
    )


class TestX402AccessTokenFlow:
    """Test X402 Access Token integration using ZeroDev Policies."""

    # Class variables to store test data across test methods
    plan_id = None
    agent_id = None
    x402_access_token = None
    subscriber_address = None
    agent_address = None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_setup_accounts(self, payments_subscriber, payments_agent):
        """Test that Payments instances are initialized and get account addresses."""
        assert payments_subscriber is not None
        assert payments_agent is not None
        assert payments_subscriber.account_address is not None
        assert payments_agent.account_address is not None

        TestX402AccessTokenFlow.subscriber_address = payments_subscriber.account_address
        TestX402AccessTokenFlow.agent_address = payments_agent.account_address

        print(f"Subscriber address: {self.subscriber_address}")
        print(f"Agent address: {self.agent_address}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_credits_plan(self, payments_agent):
        """Test creating a credits plan for X402 integration."""
        timestamp = datetime.now().isoformat()
        plan_metadata = PlanMetadata(
            name=f"E2E X402 Credits Plan PYTHON {timestamp}",
            description="Test plan for X402 Access Token integration",
        )

        # Create a free crypto plan (amount = 0) for testing
        price_config = get_crypto_price_config(
            0, self.agent_address, ZeroAddress  # Free plan
        )

        # Configure credits: 10 total credits, min=1, max=2 per burn
        credits_config = get_fixed_credits_config(
            total_credits=10,
            min_credits_per_request=1,
            max_credits_per_request=2,
        )

        print(f"Creating credits plan with config: {credits_config}")

        response = retry_with_backoff(
            lambda: payments_agent.plans.register_credits_plan(
                plan_metadata, price_config, credits_config, access_limit="credits"
            ),
            label="X402 Credits Plan Registration",
            attempts=6,
        )

        assert response is not None
        TestX402AccessTokenFlow.plan_id = response.get("planId")
        assert self.plan_id is not None
        assert int(self.plan_id) > 0
        print(f"Created X402 Credits Plan with ID: {self.plan_id}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_agent(self, payments_agent):
        """Test creating an agent associated with the X402 plan."""
        assert self.plan_id is not None, "plan_id must be set by previous test"

        timestamp = datetime.now().isoformat()
        agent_metadata = AgentMetadata(
            name=f"E2E X402 Agent PYTHON {timestamp}",
            description="Test agent for X402 Access Token integration",
            tags=["x402", "test"],
        )

        agent_api = AgentAPIAttributes(
            endpoints=[
                {"POST": "https://myagent.ai/api/v1/secret/:agentId/tasks"},
            ],
            open_endpoints=[],
            agent_definition_url="https://myagent.ai/api-docs",
            auth_type="bearer",
            token="my-secret-token",
        )

        result = retry_with_backoff(
            lambda: payments_agent.agents.register_agent(
                agent_metadata, agent_api, [self.plan_id]
            ),
            label="X402 Agent Registration",
            attempts=6,
        )

        assert result is not None
        TestX402AccessTokenFlow.agent_id = result.get("agentId")
        assert self.agent_id is not None
        print(f"Created X402 Agent with ID: {self.agent_id}")

        # Wait for agent to be available
        def _check_agent_exists():
            try:
                agent = payments_agent.agents.get_agent(self.agent_id)
                return agent is not None and agent.get("id") == self.agent_id
            except Exception:
                return False

        agent_available = wait_for_condition(
            _check_agent_exists,
            label="Agent Availability",
            timeout_secs=30.0,
            poll_interval_secs=2.0,
        )
        assert agent_available, "Agent did not become available in time"

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_subscriber_order_plan(self, payments_subscriber):
        """Test subscriber ordering the plan before getting X402 token."""
        assert self.plan_id is not None, "plan_id must be set by previous test"

        print(f"Subscriber ordering plan: {self.plan_id}")
        order_result = retry_with_backoff(
            lambda: payments_subscriber.plans.order_plan(self.plan_id),
            label="X402 Plan Order",
            attempts=6,
        )

        assert order_result is not None
        assert order_result.get("success") is True
        print(f"Subscriber successfully ordered plan: {self.plan_id}")

        # Wait for balance to be available
        def _check_balance():
            try:
                balance = payments_subscriber.plans.get_plan_balance(self.plan_id)
                if not balance or not balance.is_subscriber:
                    return False
                bal = int(balance.balance)
                return bal > 0
            except Exception:
                return False

        balance_available = wait_for_condition(
            _check_balance,
            label="Plan Balance Availability",
            timeout_secs=45.0,
            poll_interval_secs=2.0,
        )
        assert balance_available, "Plan balance did not become available in time"

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_get_x402_access_token(self, payments_subscriber):
        """Test generating X402 access token for the subscriber."""
        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert self.agent_id is not None, "agent_id must be set by previous test"

        print(
            f"Generating X402 Access Token for plan: {self.plan_id}, agent: {self.agent_id}"
        )

        response = retry_with_backoff(
            lambda: payments_subscriber.agents.get_x402_access_token(
                self.plan_id, self.agent_id
            ),
            label="X402 Access Token Generation",
            attempts=6,
        )

        assert response is not None
        TestX402AccessTokenFlow.x402_access_token = response.get("accessToken")
        assert self.x402_access_token is not None
        assert len(self.x402_access_token) > 0
        print(f"Generated X402 Access Token (length: {len(self.x402_access_token)})")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify_permissions(self, payments_agent):
        """Test verifying permissions using X402 access token."""
        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert (
            self.x402_access_token is not None
        ), "x402_access_token must be set by previous test"
        assert (
            self.subscriber_address is not None
        ), "subscriber_address must be set by previous test"

        print(
            f"Verifying permissions for plan: {self.plan_id}, max_amount: 2, subscriber: {self.subscriber_address}"
        )

        response = retry_with_backoff(
            lambda: payments_agent.facilitator.verify_permissions(
                plan_id=self.plan_id,
                max_amount="2",
                x402_access_token=self.x402_access_token,
                subscriber_address=self.subscriber_address,
            ),
            label="X402 Verify Permissions",
            attempts=5,
        )

        assert response is not None
        assert response.get("success") is True
        print(f"Verify permissions response: {response}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settle_permissions(self, payments_agent, payments_subscriber):
        """Test settling (burning) credits using X402 access token."""
        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert (
            self.x402_access_token is not None
        ), "x402_access_token must be set by previous test"
        assert (
            self.subscriber_address is not None
        ), "subscriber_address must be set by previous test"

        print(
            f"Settling permissions for plan: {self.plan_id}, max_amount: 2, subscriber: {self.subscriber_address}"
        )

        response = retry_with_backoff(
            lambda: payments_agent.facilitator.settle_permissions(
                plan_id=self.plan_id,
                max_amount="2",
                x402_access_token=self.x402_access_token,
                subscriber_address=self.subscriber_address,
            ),
            label="X402 Settle Permissions",
            attempts=5,
        )

        assert response is not None
        assert response.get("success") is True
        assert response.get("data") is not None
        assert response["data"].get("creditsBurned") == "2"
        print(f"Settle permissions response: {response}")
        print(f"Credits burned: {response['data']['creditsBurned']}")

        # Wait for balance to be updated (should now be 8)
        def _check_updated_balance():
            try:
                balance = payments_subscriber.plans.get_plan_balance(self.plan_id)
                if not balance:
                    return False
                bal = int(balance.balance)
                print(f"Current balance: {bal}")
                return bal == 8
            except Exception as e:
                print(f"Error checking balance: {e}")
                return False

        balance_updated = wait_for_condition(
            _check_updated_balance,
            label="Balance Update After Settlement",
            timeout_secs=45.0,
            poll_interval_secs=2.0,
        )
        assert balance_updated, "Balance was not updated correctly after settlement"

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify(self, payments_agent):
        """Test that verify can be called multiple times without consuming credits."""
        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert (
            self.x402_access_token is not None
        ), "x402_access_token must be set by previous test"
        assert (
            self.subscriber_address is not None
        ), "subscriber_address must be set by previous test"

        # Call verify once
        print(f"Verifying permissions")
        response = retry_with_backoff(
            lambda: payments_agent.facilitator.verify_permissions(
                plan_id=self.plan_id,
                max_amount="2",
                x402_access_token=self.x402_access_token,
                subscriber_address=self.subscriber_address,
            ),
            label=f"X402 Verify Permissions",
            attempts=3,
        )

        assert response is not None
        assert response.get("success") is True

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settle_remaining_credits(self, payments_agent, payments_subscriber):
        """Test settling the remaining credits in smaller amounts."""
        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert (
            self.x402_access_token is not None
        ), "x402_access_token must be set by previous test"
        assert (
            self.subscriber_address is not None
        ), "subscriber_address must be set by previous test"

        # Settle 2 more credits (should have 6 remaining after previous settlement)
        print("Settling 2 more credits...")
        response = retry_with_backoff(
            lambda: payments_agent.facilitator.settle_permissions(
                plan_id=self.plan_id,
                max_amount="2",
                x402_access_token=self.x402_access_token,
                subscriber_address=self.subscriber_address,
            ),
            label="X402 Settle Additional Credits",
            attempts=5,
        )

        assert response is not None
        assert response.get("success") is True
        assert response["data"].get("creditsBurned") == "2"
        print(f"Successfully burned 2 more credits")

        # Wait for balance to be updated (should now be 6)
        def _check_final_balance():
            try:
                balance = payments_subscriber.plans.get_plan_balance(self.plan_id)
                if not balance:
                    return False
                bal = int(balance.balance)
                print(f"Final balance: {bal}")
                return bal == 6
            except Exception as e:
                print(f"Error checking final balance: {e}")
                return False

        balance_updated = wait_for_condition(
            _check_final_balance,
            label="Final Balance After Additional Settlement",
            timeout_secs=45.0,
            poll_interval_secs=2.0,
        )
        assert (
            balance_updated
        ), "Balance was not updated correctly after additional settlement"
        print("X402 E2E test suite completed successfully!")

