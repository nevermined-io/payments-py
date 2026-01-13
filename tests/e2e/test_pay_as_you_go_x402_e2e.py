"""
End-to-end tests for Pay As You Go functionality.

This test suite validates the Pay As You Go flow which allows AI agents
to charge users per request/usage rather than upfront. The payment is made
when the service is consumed (settle), not when ordering.

Pay As You Go uses the PayAsYouGoTemplate contract and the ONLY_SUBSCRIBER
redemption type.
"""

import pytest
from datetime import datetime
from payments_py.common.types import (
    PlanMetadata,
    AgentMetadata,
    AgentAPIAttributes,
)
from payments_py.plans import (
    get_pay_as_you_go_price_config,
    get_pay_as_you_go_credits_config,
)
from tests.e2e.utils import retry_with_backoff, wait_for_condition
from tests.e2e.conftest import TEST_TIMEOUT, TEST_ERC20_TOKEN


class TestPayAsYouGoFlow:
    """Test Pay As You Go integration using the PayAsYouGoTemplate."""

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

        TestPayAsYouGoFlow.subscriber_address = payments_subscriber.account_address
        TestPayAsYouGoFlow.agent_address = payments_agent.account_address

        print(f"Subscriber address: {self.subscriber_address}")
        print(f"Agent address: {self.agent_address}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_pay_as_you_go_plan(self, payments_agent):
        """Test creating a Pay As You Go plan using helper functions."""
        timestamp = datetime.now().isoformat()
        plan_metadata = PlanMetadata(
            name=f"E2E Pay As You Go Plan PYTHON {timestamp}",
            description="Test plan for Pay As You Go integration",
        )

        # Create a pay-as-you-go price config (100 units per request)
        # Use PlansAPI method which automatically fetches contract address from API
        price_config = payments_agent.plans.get_pay_as_you_go_price_config(
            amount=100,
            receiver=self.agent_address,
            token_address=TEST_ERC20_TOKEN,
        )

        # Verify the price config has a template address (from API)
        assert (
            price_config.template_address is not None
        ), "Price config should have a template address from API"
        assert (
            price_config.template_address.lower()
            == payments_agent.contracts.pay_as_you_go_template.lower()
        ), "Price config should use contract address from API"

        # Configure credits (values default to 1, not functionally used for Pay As You Go)
        credits_config = get_pay_as_you_go_credits_config()

        print(f"Creating Pay As You Go plan with price config: {price_config}")
        print(f"Credits config: {credits_config}")

        response = retry_with_backoff(
            lambda: payments_agent.plans.register_credits_plan(
                plan_metadata, price_config, credits_config
            ),
            label="Pay As You Go Plan Registration",
            attempts=6,
        )

        assert response is not None
        TestPayAsYouGoFlow.plan_id = response.get("planId")
        assert self.plan_id is not None
        assert int(self.plan_id) > 0
        print(f"Created Pay As You Go Plan with ID: {self.plan_id}")

        # Wait for plan to be available and verify template address
        def _check_plan_with_template():
            try:
                plan = payments_agent.plans.get_plan(self.plan_id)
                if not plan:
                    return False
                # Check if templateAddress is set correctly
                registry = plan.get("registry", {})
                price = registry.get("price", {})
                template_addr = price.get("templateAddress", "")
                expected_addr = payments_agent.contracts.pay_as_you_go_template
                print(f"Plan template address: {template_addr}")
                print(f"Expected template address: {expected_addr}")
                return template_addr.lower() == expected_addr.lower()
            except Exception as e:
                print(f"Error checking plan: {e}")
                return False

        plan_ready = wait_for_condition(
            _check_plan_with_template,
            label="Plan Template Address Verification",
            timeout_secs=45.0,
            poll_interval_secs=3.0,
        )
        assert plan_ready, "Plan template address was not set correctly"

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_agent_for_pay_as_you_go(self, payments_agent):
        """Test creating an agent associated with the Pay As You Go plan."""
        assert self.plan_id is not None, "plan_id must be set by previous test"

        timestamp = datetime.now().isoformat()
        agent_metadata = AgentMetadata(
            name=f"E2E Pay As You Go Agent PYTHON {timestamp}",
            description="Test agent for Pay As You Go integration",
            tags=["pay-as-you-go", "test"],
        )

        agent_api = AgentAPIAttributes(
            endpoints=[
                {
                    "verb": "POST",
                    "url": "https://myagent.ai/api/v1/secret/:agentId/tasks",
                },
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
            label="Pay As You Go Agent Registration",
            attempts=6,
        )

        assert result is not None
        TestPayAsYouGoFlow.agent_id = result.get("agentId")
        assert self.agent_id is not None
        print(f"Created Pay As You Go Agent with ID: {self.agent_id}")

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
    def test_get_x402_access_token_for_pay_as_you_go(self, payments_subscriber):
        """Test generating X402 access token for the Pay As You Go plan."""
        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert self.agent_id is not None, "agent_id must be set by previous test"

        print(
            f"Generating X402 Access Token for Pay As You Go plan: {self.plan_id}, agent: {self.agent_id}"
        )

        response = retry_with_backoff(
            lambda: payments_subscriber.x402.get_x402_access_token(
                self.plan_id, self.agent_id
            ),
            label="X402 Access Token Generation for Pay As You Go",
            attempts=3,
        )

        assert response is not None
        TestPayAsYouGoFlow.x402_access_token = response.get("accessToken")
        assert self.x402_access_token is not None
        assert len(self.x402_access_token) > 0
        print(f"Generated X402 Access Token (length: {len(self.x402_access_token)})")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify_pay_as_you_go_permissions(self, payments_agent):
        """Test verifying permissions for Pay As You Go using X402 access token."""
        from payments_py.x402 import X402PaymentRequired, X402Scheme, X402Resource

        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert (
            self.x402_access_token is not None
        ), "x402_access_token must be set by previous test"

        print(f"Verifying Pay As You Go permissions for plan: {self.plan_id}")

        # Note: planId and subscriberAddress are extracted from the token
        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/test/endpoint"),
            accepts=[
                X402Scheme(
                    scheme="nvm:erc4337",
                    network="eip155:84532",
                    plan_id=self.plan_id,
                )
            ],
            extensions={},
        )
        response = retry_with_backoff(
            lambda: payments_agent.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=self.x402_access_token,
                max_amount="1",
            ),
            label="Pay As You Go Verify Permissions",
            attempts=3,
        )

        assert response is not None
        assert response.is_valid is True
        print(f"Pay As You Go verify permissions response: {response}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settle_pay_as_you_go(self, payments_agent, payments_subscriber):
        """Test settling (ordering) Pay As You Go plan using X402 access token."""
        from payments_py.x402 import X402PaymentRequired, X402Scheme, X402Resource

        assert self.plan_id is not None, "plan_id must be set by previous test"
        assert (
            self.x402_access_token is not None
        ), "x402_access_token must be set by previous test"

        print(f"Settling Pay As You Go for plan: {self.plan_id}")

        # Note: planId and subscriberAddress are extracted from the token
        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/test/endpoint"),
            accepts=[
                X402Scheme(
                    scheme="nvm:erc4337",
                    network="eip155:84532",
                    plan_id=self.plan_id,
                )
            ],
            extensions={},
        )
        response = retry_with_backoff(
            lambda: payments_agent.facilitator.settle_permissions(
                payment_required=payment_required,
                x402_access_token=self.x402_access_token,
                max_amount="1",
            ),
            label="Pay As You Go Settle",
            attempts=3,
        )

        assert response is not None
        assert response.success is True
        print(f"Pay As You Go settle response: {response}")
        print("Pay As You Go E2E test suite completed successfully!")
