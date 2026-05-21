"""End-to-end tests for the X402 card-delegation flow against a Visa
Agentic-Tokens delegation.

Intended to run **locally only**. The Visa delegation backing the
fixture has a finite ``durationSecs`` and refreshing it requires a
manual browser flow (VGS Collect iframe + WebAuthn passkey ceremony),
so this suite is not safe to enable in CI — once the delegation
expires it would start failing and block unrelated PRs. The suite is
gated on the three env vars below and is skipped when any are missing
or malformed, so CI without the fixture stays green by default.

Visa card enrolment and Visa delegation creation both require a real
browser, so the SDK cannot do either step programmatically. The plan
itself also has to exist beforehand — the backend binds each Visa
delegation to a single plan at creation time (BCK.VISA.0015) and
rejects a mismatch between the delegation's planId and the planId
used to mint or verify the access token. So this suite creates
nothing: it exercises only the *consume* side of an already-
provisioned plan + card + delegation triple:

  1. list_payment_methods → find the visa-provider card.
  2. get_x402_access_token using the pre-created delegation_id + plan_id.
  3. verify_permissions against the real backend.

Settlement is intentionally NOT exercised: the sandbox card providers
(Stripe sandbox, Visa sandbox CMP) do not actually charge, so a real
settle assertion like ``credits_redeemed == '2'`` cannot be made
truthful in this environment. End-to-end settlement is validated
separately at the platform level.

Required env vars:
  - NVM_TEST_VISA_PLAN_ID            (plan id the delegation is bound
                                       to, created by the builder
                                       whose key is TEST_BUILDER_API_KEY)
  - NVM_TEST_VISA_DELEGATION_ID      (uuid returned by /delegation/create)
  - NVM_TEST_VISA_PAYMENT_METHOD_ID  (Visa Agentic token id, format vat_…)

Optional env vars (inherited from conftest.py):
  - TEST_SUBSCRIBER_API_KEY, TEST_BUILDER_API_KEY, TEST_ENVIRONMENT

See ``docs/api/11-x402.md`` → "Visa e2e fixture" for the one-time
provisioning runbook.
"""

import os
import re

import pytest

from payments_py.x402.types import (
    DelegationConfig,
    X402PaymentRequired,
    X402Resource,
    X402Scheme,
    X402TokenOptions,
)
from tests.e2e.utils import retry_with_backoff
from tests.e2e.conftest import TEST_TIMEOUT

_VISA_PLAN_ID = os.getenv("NVM_TEST_VISA_PLAN_ID")
_VISA_DELEGATION_ID = os.getenv("NVM_TEST_VISA_DELEGATION_ID")
_VISA_PAYMENT_METHOD_ID = os.getenv("NVM_TEST_VISA_PAYMENT_METHOD_ID")

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)
_PLAN_ID_RE = re.compile(r"^[0-9]+$")
_VAT_RE = re.compile(r"^vat_")


def _skip_reason() -> str | None:
    """Return the reason this suite should be skipped, or None to run.

    Truthiness alone isn't enough: silently skipping when only some env
    vars are set hides developer typos. Same for malformed values like
    ``NVM_TEST_VISA_DELEGATION_ID=TODO`` — those would slip through and
    fail on the API call instead of at gate time. Emit a specific reason
    so the skip message points at the actual misconfiguration.
    """
    present = [
        bool(_VISA_PLAN_ID),
        bool(_VISA_DELEGATION_ID),
        bool(_VISA_PAYMENT_METHOD_ID),
    ]
    if not any(present):
        return "Visa e2e fixture env vars not set (see docs/api/11-x402.md)"
    if not all(present):
        return (
            "Visa e2e: only some of NVM_TEST_VISA_{PLAN_ID,DELEGATION_ID,"
            "PAYMENT_METHOD_ID} are set; all three are required"
        )
    if not _PLAN_ID_RE.match(_VISA_PLAN_ID or ""):
        return "Visa e2e: NVM_TEST_VISA_PLAN_ID is not a decimal uint256"
    if not _UUID_RE.match(_VISA_DELEGATION_ID or ""):
        return "Visa e2e: NVM_TEST_VISA_DELEGATION_ID is not a UUID"
    if not _VAT_RE.match(_VISA_PAYMENT_METHOD_ID or ""):
        return "Visa e2e: NVM_TEST_VISA_PAYMENT_METHOD_ID does not start with 'vat_'"
    return None


_SKIP_REASON = _skip_reason()

pytestmark = pytest.mark.skipif(_SKIP_REASON is not None, reason=_SKIP_REASON or "")


def _find_visa_card(payment_methods, payment_method_id: str):
    for pm in payment_methods:
        if getattr(pm, "provider", None) == "visa" and pm.id == payment_method_id:
            return pm
    return None


class TestX402CardDelegationFlowVisa:
    """Test X402 Visa Agentic delegation against an already-provisioned fixture."""

    x402_access_token = None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_list_visa_card(self, payments_subscriber):
        """Subscriber's listed payment methods include the pre-provisioned Visa card."""
        methods = payments_subscriber.delegation.list_payment_methods()
        card = _find_visa_card(methods, _VISA_PAYMENT_METHOD_ID)
        assert (
            card is not None
        ), f"No visa-provider PM with id {_VISA_PAYMENT_METHOD_ID} among {len(methods)} methods"
        assert card.provider == "visa"
        print(f"Using Visa card: {card.brand} ...{card.last4} (id: {card.id})")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_mint_token_against_visa_delegation(self, payments_subscriber):
        """Mint an x402 access token against the pre-created Visa delegationId."""
        response = retry_with_backoff(
            lambda: payments_subscriber.x402.get_x402_access_token(
                _VISA_PLAN_ID,
                token_options=X402TokenOptions(
                    scheme="nvm:card-delegation",
                    network="visa",
                    delegation_config=DelegationConfig(
                        delegation_id=_VISA_DELEGATION_ID
                    ),
                ),
            ),
            label="Visa Token Generation",
            attempts=3,
        )
        assert response is not None
        TestX402CardDelegationFlowVisa.x402_access_token = response.get("accessToken")
        assert self.x402_access_token
        print(
            f"Generated Visa delegation token (length: {len(self.x402_access_token)})"
        )

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify_visa_network(self, payments_agent):
        """Facilitator accepts the visa-network paymentRequired without
        provider-specific branching."""
        assert (
            self.x402_access_token is not None
        ), "test_mint_token_against_visa_delegation must run first"

        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/test/endpoint"),
            accepts=[
                X402Scheme(
                    scheme="nvm:card-delegation",
                    network="visa",
                    plan_id=_VISA_PLAN_ID,
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
            label="Visa Delegation Verify",
            attempts=3,
        )

        assert response is not None
        assert response.is_valid is True
        assert response.network == "visa"
        print(f"Visa verify: is_valid={response.is_valid}, network={response.network}")
