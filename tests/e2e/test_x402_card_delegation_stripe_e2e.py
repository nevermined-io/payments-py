"""
End-to-end tests for X402 card-delegation flow (Stripe).

These tests require:
- A running API with .env.backend1 config (Base Sepolia + Stripe/Privy)
- A valid Stripe card enrollment

Until staging is deployed with PR #1102, these tests will be skipped.
Set CARD_DELEGATION_E2E=1 to enable.
"""

import pytest
from datetime import datetime
from payments_py.common.types import (
    PlanMetadata,
)
from payments_py.environments import ZeroAddress
from payments_py.plans import (
    get_fiat_price_config,
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


def _find_stripe_card(payment_methods):
    """Find the first Stripe payment method of type 'card'."""
    for pm in payment_methods:
        if (
            getattr(pm, "type", None) == "card"
            and getattr(pm, "provider", "stripe") == "stripe"
        ):
            return pm
    return None


class TestX402CardDelegationFlow:
    """Test X402 card delegation (Stripe) integration."""

    plan_id = None
    delegation_id = None
    x402_access_token = None
    x402_auto_token = None
    agent_address = None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_setup(self, payments_agent):
        """Initialize account addresses."""
        TestX402CardDelegationFlow.agent_address = payments_agent.account_address
        assert self.agent_address is not None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_plan(self, payments_agent):
        """Create a credits plan for card delegation testing."""
        timestamp = datetime.now().isoformat()
        plan_metadata = PlanMetadata(
            name=f"E2E Card Delegation Plan PYTHON {timestamp}",
            description="Test plan for card delegation integration",
        )

        # Fiat plan (isCrypto=false): 1000000 = $1.00 in USDC 6-decimal format
        # Must be >= Stripe minimum ($0.50) for card delegation settle to work
        price_config = get_fiat_price_config(1000000, self.agent_address)
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
    def test_create_card_delegation(self, payments_subscriber):
        """Create a card delegation using an enrolled Stripe card."""
        methods = payments_subscriber.delegation.list_payment_methods()
        card = _find_stripe_card(methods)
        assert (
            card is not None
        ), f"No payment method of type 'card' found among {len(methods)} methods"

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
    def test_generate_token_with_explicit_delegation(self, payments_subscriber):
        """Generate X402 access token using an explicit delegationId (Pattern B)."""
        assert self.plan_id is not None
        assert self.delegation_id is not None

        response = retry_with_backoff(
            lambda: payments_subscriber.x402.get_x402_access_token(
                self.plan_id,
                token_options=X402TokenOptions(
                    scheme="nvm:card-delegation",
                    delegation_config=DelegationConfig(
                        delegation_id=self.delegation_id
                    ),
                ),
            ),
            label="Card Delegation Token Generation (explicit)",
            attempts=3,
        )

        assert response is not None
        TestX402CardDelegationFlow.x402_access_token = response.get("accessToken")
        assert self.x402_access_token is not None
        print(
            f"Generated card delegation token (length: {len(self.x402_access_token)})"
        )

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_generate_token_with_auto_delegation(self, payments_subscriber):
        """Generate X402 access token with auto-created delegation (Pattern A)."""
        assert self.plan_id is not None

        methods = payments_subscriber.delegation.list_payment_methods()
        card = _find_stripe_card(methods)
        assert card is not None, "No card-type payment method found"

        response = retry_with_backoff(
            lambda: payments_subscriber.x402.get_x402_access_token(
                self.plan_id,
                token_options=X402TokenOptions(
                    scheme="nvm:card-delegation",
                    delegation_config=DelegationConfig(
                        provider_payment_method_id=card.id,
                        spending_limit_cents=5000,
                        duration_secs=3600,
                    ),
                ),
            ),
            label="Card Delegation Token Generation (auto)",
            attempts=3,
        )

        assert response is not None
        TestX402CardDelegationFlow.x402_auto_token = response.get("accessToken")
        assert self.x402_auto_token is not None
        print(f"Generated auto-delegation token (length: {len(self.x402_auto_token)})")

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

        response = retry_with_backoff(
            lambda: payments_agent.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=self.x402_access_token,
                max_amount="2",
            ),
            label="Card Delegation Verify",
            attempts=3,
        )

        assert response is not None
        assert response.is_valid is True
        assert response.network == "stripe"
        print(f"Card delegation verify response: {response}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settle_with_card_delegation(self, payments_agent, payments_subscriber):
        """Settle (burn credits) using card delegation token."""
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

        response = retry_with_backoff(
            lambda: payments_agent.facilitator.settle_permissions(
                payment_required=payment_required,
                x402_access_token=self.x402_access_token,
                max_amount="2",
            ),
            label="Card Delegation Settle",
            attempts=3,
        )

        assert response is not None
        assert response.success is True
        assert response.credits_redeemed == "2"
        print(f"Card delegation settle: credits_redeemed={response.credits_redeemed}")

        # Wait for balance to reflect settlement (should be 8 from 10)
        def _check_balance():
            try:
                balance = payments_subscriber.plans.get_plan_balance(self.plan_id)
                if not balance:
                    return False
                bal = int(balance.balance)
                print(f"Balance after card settle: {bal}")
                return bal == 8
            except Exception as e:
                print(f"Error checking balance: {e}")
                return False

        balance_updated = wait_for_condition(
            _check_balance,
            label="Balance After Card Settlement",
            timeout_secs=30.0,
            poll_interval_secs=2.0,
        )
        assert (
            balance_updated
        ), "Balance was not updated after card delegation settlement"
