"""
End-to-end tests for X402 card-delegation flow (Stripe).

These tests require:
- A running API with .env.backend1 config (Base Sepolia + Stripe/Privy)
- A valid Stripe card enrollment

Until staging is deployed with PR #1102, these tests will be skipped.
Set CARD_DELEGATION_E2E=1 to enable.
"""

import os
import pytest
from datetime import datetime
from payments_py.common.types import (
    PlanMetadata,
    AgentMetadata,
    AgentAPIAttributes,
)
from payments_py.environments import ZeroAddress
from payments_py.plans import (
    get_crypto_price_config,
    get_dynamic_credits_config,
)
from payments_py.x402 import (
    CreateDelegationPayload,
    DelegationConfig,
    X402TokenOptions,
    X402PaymentRequired,
    X402Scheme,
    X402Resource,
)
from tests.e2e.utils import retry_with_backoff, wait_for_condition
from tests.e2e.conftest import TEST_TIMEOUT

# Skip these tests unless CARD_DELEGATION_E2E is explicitly enabled
SKIP = not os.environ.get("CARD_DELEGATION_E2E")
pytestmark = pytest.mark.skipif(SKIP, reason="CARD_DELEGATION_E2E not set")


class TestX402CardDelegationFlow:
    """Test X402 card delegation (Stripe) integration."""

    plan_id = None
    agent_id = None
    delegation_id = None
    x402_access_token = None
    agent_address = None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_setup(self, payments_agent):
        """Initialize account addresses."""
        TestX402CardDelegationFlow.agent_address = payments_agent.account_address
        assert self.agent_address is not None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_fiat_plan(self, payments_agent):
        """Create a fiat credits plan for card delegation testing."""
        timestamp = datetime.now().isoformat()
        plan_metadata = PlanMetadata(
            name=f"E2E Card Delegation Plan PYTHON {timestamp}",
            description="Test plan for card delegation integration",
        )

        price_config = get_crypto_price_config(0, self.agent_address, ZeroAddress)
        credits_config = get_dynamic_credits_config(10, 1, 2)

        response = retry_with_backoff(
            lambda: payments_agent.plans.register_credits_plan(
                plan_metadata, price_config, credits_config
            ),
            label="Card Delegation Plan Registration",
            attempts=6,
        )

        assert response is not None
        TestX402CardDelegationFlow.plan_id = response.get("planId")
        assert self.plan_id is not None
        print(f"Created card delegation plan with ID: {self.plan_id}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_agent(self, payments_agent):
        """Create an agent for card delegation testing."""
        assert self.plan_id is not None

        timestamp = datetime.now().isoformat()
        agent_metadata = AgentMetadata(
            name=f"E2E Card Agent PYTHON {timestamp}",
            description="Test agent for card delegation",
            tags=["card-delegation", "test"],
        )

        agent_api = AgentAPIAttributes(
            endpoints=[{"verb": "POST", "url": "http://localhost/ask"}],
            open_endpoints=[],
            agent_definition_url="http://localhost/agent-definition",
            auth_type="bearer",
        )

        result = retry_with_backoff(
            lambda: payments_agent.agents.register_agent(
                agent_metadata, agent_api, [self.plan_id]
            ),
            label="Card Agent Registration",
            attempts=6,
        )

        assert result is not None
        TestX402CardDelegationFlow.agent_id = result.get("agentId")
        assert self.agent_id is not None

        def _check():
            try:
                agent = payments_agent.agents.get_agent(self.agent_id)
                return agent is not None and agent.get("id") == self.agent_id
            except Exception:
                return False

        assert wait_for_condition(_check, "Agent Availability", 30.0, 2.0)

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_card_delegation(self, payments_subscriber):
        """Create a card delegation using an enrolled Stripe card."""
        cards = payments_subscriber.delegation.list_payment_methods()
        assert len(cards) > 0, "No enrolled payment methods found"

        card = cards[0]
        print(f"Using card: {card.brand} ...{card.last4}")

        delegation = retry_with_backoff(
            lambda: payments_subscriber.delegation.create_delegation(
                CreateDelegationPayload(
                    provider="stripe",
                    provider_payment_method_id=card.id,
                    spending_limit_cents=10000,
                    duration_secs=604800,
                )
            ),
            label="Stripe Delegation Creation",
            attempts=3,
        )

        assert delegation is not None
        assert delegation.delegation_id is not None
        TestX402CardDelegationFlow.delegation_id = delegation.delegation_id
        print(f"Created card delegation: {self.delegation_id}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_generate_token_with_card_delegation(self, payments_subscriber):
        """Generate X402 access token using card delegation."""
        assert self.plan_id is not None
        assert self.delegation_id is not None

        response = retry_with_backoff(
            lambda: payments_subscriber.x402.get_x402_access_token(
                self.plan_id,
                self.agent_id,
                token_options=X402TokenOptions(
                    scheme="nvm:card-delegation",
                    delegation_config=DelegationConfig(
                        delegation_id=self.delegation_id
                    ),
                ),
            ),
            label="Card Delegation Token Generation",
            attempts=3,
        )

        assert response is not None
        TestX402CardDelegationFlow.x402_access_token = response.get("accessToken")
        assert self.x402_access_token is not None
        print(
            f"Generated card delegation token (length: {len(self.x402_access_token)})"
        )

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify_with_card_delegation(self, payments_agent):
        """Verify permissions using card delegation token."""
        assert self.x402_access_token is not None

        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/test/endpoint"),
            accepts=[
                X402Scheme(
                    scheme="nvm:card-delegation",
                    network="stripe",
                    plan_id=self.plan_id,
                )
            ],
            extensions={},
        )

        response = payments_agent.facilitator.verify_permissions(
            payment_required=payment_required,
            x402_access_token=self.x402_access_token,
            max_amount="2",
        )

        assert response is not None
        assert response.is_valid is True
        print(f"Card delegation verify response: {response}")
