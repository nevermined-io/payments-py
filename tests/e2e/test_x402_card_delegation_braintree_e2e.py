"""
End-to-end tests for X402 card-delegation flow (Braintree).

These tests require:
- A running API with Braintree credentials configured
- A Braintree-enrolled payment method for the subscriber account
- A Braintree-connected merchant (seller) for the agent account

Set BRAINTREE_DELEGATION_E2E=1 to enable.

## Braintree merchant tokens

The settle test requires a valid Braintree OAuth access token for the
merchant. Since the OAuth flow requires a browser redirect, the merchant
profile must be set up manually or via direct DB insertion.

See the nvm-monorepo E2E test at:
  apps/api/src/x402/x402-card-delegation-braintree.external.spec.ts
for the full setup pattern including DB-based merchant profile injection.
"""

import pytest
from datetime import datetime
from payments_py.common.types import PlanMetadata
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

# Skip unless explicitly enabled

def _find_braintree_method(payment_methods):
    """Find the first Braintree payment method (card or paypal)."""
    for pm in payment_methods:
        if getattr(pm, "provider", None) == "braintree":
            return pm
    return None


class TestX402BraintreeCardDelegationFlow:
    """Test X402 card delegation (Braintree) integration."""

    plan_id = None
    delegation_id = None
    x402_access_token = None
    agent_address = None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_setup(self, payments_agent):
        """Initialize account addresses."""
        TestX402BraintreeCardDelegationFlow.agent_address = (
            payments_agent.account_address
        )
        assert self.agent_address is not None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_plan(self, payments_agent):
        """Create a fiat credits plan for Braintree card delegation testing."""
        timestamp = datetime.now().isoformat()
        plan_metadata = PlanMetadata(
            name=f"E2E Braintree Card Delegation Plan PYTHON {timestamp}",
            description="Test plan for Braintree card delegation integration",
        )

        # Fiat plan (isCrypto=false): 1000000 = $1.00 in USDC 6-decimal format
        # Must be > 0 for card delegation settle to work
        price_config = get_fiat_price_config(1000000, self.agent_address)
        credits_config = get_dynamic_credits_config(10, 1, 2)

        response = retry_with_backoff(
            lambda: payments_agent.plans.register_credits_plan(
                plan_metadata, price_config, credits_config
            ),
            label="Braintree Card Delegation Plan Registration",
            attempts=6,
        )

        assert response is not None
        TestX402BraintreeCardDelegationFlow.plan_id = response.get("planId")
        assert self.plan_id is not None
        print(f"Created Braintree card delegation plan with ID: {self.plan_id}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_list_payment_methods(self, payments_subscriber):
        """List payment methods and find a Braintree-enrolled method."""
        methods = payments_subscriber.delegation.list_payment_methods()
        pm = _find_braintree_method(methods)
        assert pm is not None, (
            f"No Braintree payment method found among {len(methods)} methods. "
            "Enroll a card via Braintree Drop-in UI at https://nevermined.app"
        )
        print(
            f"Found Braintree payment method: {pm.brand} "
            f"{'*' + pm.last4 if pm.last4 else ''} "
            f"(provider: {pm.provider})"
        )

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_braintree_delegation(self, payments_subscriber):
        """Create a card delegation using a Braintree-enrolled payment method."""
        methods = payments_subscriber.delegation.list_payment_methods()
        pm = _find_braintree_method(methods)
        assert pm is not None, "No Braintree payment method found"

        delegation = retry_with_backoff(
            lambda: payments_subscriber.delegation.create_delegation(
                CreateDelegationPayload(
                    provider="braintree",
                    provider_payment_method_id=pm.id,
                    spending_limit_cents=10000,
                    duration_secs=604800,
                )
            ),
            label="Braintree Delegation Creation",
            attempts=3,
        )

        assert delegation is not None
        assert delegation.delegation_id is not None
        TestX402BraintreeCardDelegationFlow.delegation_id = delegation.delegation_id
        print(f"Created Braintree delegation: {self.delegation_id}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_generate_token_with_explicit_delegation(self, payments_subscriber):
        """Generate X402 access token using the Braintree delegation."""
        assert self.plan_id is not None
        assert self.delegation_id is not None

        response = retry_with_backoff(
            lambda: payments_subscriber.x402.get_x402_access_token(
                self.plan_id,
                token_options=X402TokenOptions(
                    scheme="nvm:card-delegation",
                    network="braintree",
                    delegation_config=DelegationConfig(
                        delegation_id=self.delegation_id
                    ),
                ),
            ),
            label="Braintree Delegation Token Generation",
            attempts=3,
        )

        assert response is not None
        TestX402BraintreeCardDelegationFlow.x402_access_token = response.get(
            "accessToken"
        )
        assert self.x402_access_token is not None
        print(
            f"Generated Braintree delegation token (length: {len(self.x402_access_token)})"
        )

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify_with_braintree_delegation(self, payments_agent):
        """Verify permissions using Braintree delegation token."""
        assert self.x402_access_token is not None

        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/test/endpoint"),
            accepts=[
                X402Scheme(
                    scheme="nvm:card-delegation",
                    network="braintree",
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
            label="Braintree Delegation Verify",
            attempts=3,
        )

        assert response is not None
        assert response.is_valid is True
        assert response.network == "braintree"
        print(f"Braintree delegation verify response: {response}")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settle_with_braintree_delegation(
        self, payments_agent, payments_subscriber
    ):
        """Settle (burn credits) using Braintree delegation token.

        NOTE: This test requires that the plan owner (agent) has a
        Braintree merchant account connected. Settlement charges the
        buyer's card via Braintree Shared Vault and routes funds to
        the merchant. If the merchant is not connected, settlement
        will fail with 'Plan owner has no Braintree account connected'.
        """
        assert self.x402_access_token is not None

        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/test/endpoint"),
            accepts=[
                X402Scheme(
                    scheme="nvm:card-delegation",
                    network="braintree",
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
            label="Braintree Delegation Settle",
            attempts=3,
        )

        assert response is not None
        assert response.success is True
        assert response.credits_redeemed == "2"
        assert response.network == "braintree"
        print(
            f"Braintree delegation settle: credits_redeemed={response.credits_redeemed}"
        )

        # Wait for balance to reflect settlement
        def _check_balance():
            try:
                balance = payments_subscriber.plans.get_plan_balance(self.plan_id)
                if not balance:
                    return False
                bal = int(balance.balance)
                print(f"Balance after Braintree settle: {bal}")
                return bal == 8
            except Exception as e:
                print(f"Error checking balance: {e}")
                return False

        balance_updated = wait_for_condition(
            _check_balance,
            label="Balance After Braintree Settlement",
            timeout_secs=30.0,
            poll_interval_secs=2.0,
        )
        assert (
            balance_updated
        ), "Balance was not updated after Braintree delegation settlement"
