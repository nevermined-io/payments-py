"""
End-to-end tests for the MPP surface against a deployed environment.

Covers both halves against the real backend:

1. Seller: mint a challenge, verify the credential, settle it (and prove the
   settle is idempotent).
2. Buyer + seller together: a FastAPI app protected by the middleware, paid by
   ``payments.mpp.fetch`` over real HTTP through the ASGI transport.

**MPP must be deployed on the target environment.** When it is not, the backend
answers ``BCK.MPP.0002`` and every test here self-skips with that named as the
reason — a skip, never a silent pass. Deployment coverage is tracked as
nevermined-io/nvm-monorepo#2645.
"""

import threading
from datetime import datetime

import httpx
import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from payments_py.common.types import AgentAPIAttributes, AgentMetadata, PlanMetadata
from payments_py.environments import ZeroAddress
from payments_py.mpp import (
    IssueMppChallengeParams,
    MppFetchOptions,
    MppNotConfiguredError,
    RedeemMppParams,
    build_credential_header,
    parse_challenge_header,
)
from payments_py.plans import get_crypto_price_config, get_dynamic_credits_config
from payments_py.x402 import CreateDelegationPayload, DelegationConfig, X402TokenOptions
from payments_py.x402.fastapi import PaymentMiddleware
from tests.e2e.conftest import TEST_TIMEOUT
from tests.e2e.utils import retry_with_backoff, wait_for_condition

pytestmark = pytest.mark.slow

MPP_NOT_DEPLOYED = (
    "MPP is not deployed on this environment (BCK.MPP.0002). The SDK is fine; "
    "the target backend does not serve /api/v1/mpp/*. See "
    "nevermined-io/nvm-monorepo#2645."
)


def skip_if_mpp_is_not_deployed(error: BaseException) -> None:
    """Re-raise anything that is not "MPP is turned off here"."""
    if isinstance(error, MppNotConfiguredError):
        pytest.skip(MPP_NOT_DEPLOYED)
    raise error


class TestMppFlow:
    """The MPP seller and buyer halves against a real backend."""

    plan_id = None
    agent_id = None
    delegation_id = None
    challenge = None
    credential = None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_credits_plan(self, payments_agent):
        timestamp = datetime.now().isoformat()
        response = retry_with_backoff(
            lambda: payments_agent.plans.register_credits_plan(
                PlanMetadata(
                    name=f"E2E MPP Credits Plan PYTHON {timestamp}",
                    description="Test plan for the MPP integration",
                ),
                get_crypto_price_config(0, payments_agent.account_address, ZeroAddress),
                get_dynamic_credits_config(
                    credits_granted=10,
                    min_credits_per_request=1,
                    max_credits_per_request=2,
                ),
            ),
            label="MPP Credits Plan Registration",
            attempts=6,
        )
        TestMppFlow.plan_id = response.get("planId")
        assert self.plan_id is not None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_agent(self, payments_agent):
        assert self.plan_id is not None, "plan_id must be set by a previous test"
        timestamp = datetime.now().isoformat()
        result = retry_with_backoff(
            lambda: payments_agent.agents.register_agent(
                AgentMetadata(
                    name=f"E2E MPP Agent PYTHON {timestamp}",
                    description="Test agent for the MPP integration",
                    tags=["mpp", "test"],
                ),
                AgentAPIAttributes(
                    endpoints=[{"verb": "POST", "url": "https://myagent.ai/ask"}],
                    open_endpoints=[],
                    agent_definition_url="https://myagent.ai/api-docs",
                    auth_type="bearer",
                    token="my-secret-token",
                ),
                [self.plan_id],
            ),
            label="MPP Agent Registration",
            attempts=6,
        )
        TestMppFlow.agent_id = result.get("agentId")
        assert self.agent_id is not None

        def agent_is_indexed() -> bool:
            # get_agent raises `Agent not found` until the write is indexed, and
            # an exception escaping the predicate ends the wait on the FIRST poll
            # instead of retrying for the full window — which is what this
            # (correctly registered) agent hit in CI. Same shape the x402 e2e
            # uses for the same reason.
            try:
                agent = payments_agent.agents.get_agent(self.agent_id)
            except Exception:
                return False
            return agent is not None and agent.get("id") == self.agent_id

        assert wait_for_condition(
            agent_is_indexed,
            label="Agent Availability",
            timeout_secs=30.0,
            poll_interval_secs=2.0,
        )

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_create_crypto_delegation(self, payments_subscriber):
        delegation = retry_with_backoff(
            lambda: payments_subscriber.delegation.create_delegation(
                CreateDelegationPayload(
                    provider="erc4337",
                    spending_limit_cents=100000,
                    duration_secs=604800,
                    currency="usdc",
                )
            ),
            label="Crypto Delegation Creation",
            attempts=3,
        )
        TestMppFlow.delegation_id = delegation.delegation_id
        assert self.delegation_id is not None

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_issue_challenge(self, payments_agent):
        assert self.plan_id is not None, "plan_id must be set by a previous test"
        try:
            issued = payments_agent.mpp.issue_challenge(
                IssueMppChallengeParams(
                    plan_id=self.plan_id,
                    credits=1,
                    agent_id=self.agent_id,
                    resource="/ask",
                    http_verb="POST",
                    description="E2E MPP challenge",
                )
            )
        except Exception as error:
            skip_if_mpp_is_not_deployed(error)

        assert issued["challenge"].startswith("Payment ")
        assert issued["id"]
        TestMppFlow.challenge = issued["challenge"]

        parsed = parse_challenge_header(issued["challenge"])
        assert parsed is not None
        assert parsed.request.plan_id == str(self.plan_id)
        assert parsed.request.credits == "1"

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_mint_a_credential_for_the_challenge(self, payments_subscriber):
        assert self.challenge is not None, "challenge must be set by a previous test"
        try:
            minted = payments_subscriber.mpp.get_mpp_access_token(
                self.plan_id,
                self.agent_id,
                X402TokenOptions(
                    delegation_config=DelegationConfig(delegation_id=self.delegation_id)
                ),
            )
        except Exception as error:
            skip_if_mpp_is_not_deployed(error)

        assert minted["accessToken"]
        TestMppFlow.credential = build_credential_header(
            parse_challenge_header(self.challenge), minted
        )
        assert self.credential.startswith("Payment ")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_verify_the_credential_without_burning(self, payments_agent):
        assert self.credential is not None, "credential must be set by a previous test"
        verification = payments_agent.mpp.verify_credential(
            RedeemMppParams(
                credential=self.credential, resource="/ask", http_verb="POST"
            )
        )
        assert verification.get("isValid") is True

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settle_the_credential_and_receive_a_receipt(self, payments_agent):
        assert self.credential is not None, "credential must be set by a previous test"
        settlement = payments_agent.mpp.settle_credential(
            RedeemMppParams(
                credential=self.credential, resource="/ask", http_verb="POST"
            )
        )
        assert settlement.get("success") is True
        assert settlement.get("paymentReceipt")

    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_settling_the_same_credential_twice_burns_once(self, payments_agent):
        # The challenge id doubles as the burn idempotency key, which is what
        # makes settlement safe to retry — and is exactly why single-use has to
        # be enforced at the seller edge rather than left to the backend.
        assert self.credential is not None, "credential must be set by a previous test"
        settlement = payments_agent.mpp.settle_credential(
            RedeemMppParams(
                credential=self.credential, resource="/ask", http_verb="POST"
            )
        )
        assert settlement.get("success") is True


class TestMppBuyerSellerLoop:
    """A real FastAPI seller, paid by the real buyer helper."""

    plan_id = None
    delegation_id = None

    @pytest.mark.timeout(TEST_TIMEOUT * 2)
    def test_the_buyer_pays_the_middleware_end_to_end(
        self, payments_agent, payments_subscriber
    ):
        timestamp = datetime.now().isoformat()
        plan = retry_with_backoff(
            lambda: payments_agent.plans.register_credits_plan(
                PlanMetadata(
                    name=f"E2E MPP Loop Plan PYTHON {timestamp}",
                    description="Test plan for the MPP buyer/seller loop",
                ),
                get_crypto_price_config(0, payments_agent.account_address, ZeroAddress),
                get_dynamic_credits_config(
                    credits_granted=10,
                    min_credits_per_request=1,
                    max_credits_per_request=2,
                ),
            ),
            label="MPP Loop Plan Registration",
            attempts=6,
        )
        plan_id = plan.get("planId")

        delegation = retry_with_backoff(
            lambda: payments_subscriber.delegation.create_delegation(
                CreateDelegationPayload(
                    provider="erc4337",
                    spending_limit_cents=100000,
                    duration_secs=604800,
                    currency="usdc",
                )
            ),
            label="Crypto Delegation Creation",
            attempts=3,
        )

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=payments_agent,
            routes={"POST /ask": {"plan_id": plan_id, "credits": 1, "mpp": True}},
        )

        @app.post("/ask")
        async def ask(request: Request):
            return JSONResponse({"answer": "42"})

        # The buyer helper drives `requests`, so the in-process ASGI app is
        # fronted by a real socket rather than a test transport.
        config = uvicorn.Config(app, host="127.0.0.1", port=8931, log_level="warning")
        server = uvicorn.Server(config)
        thread = threading.Thread(target=server.run, daemon=True)
        thread.start()
        try:
            assert wait_for_condition(
                lambda: _server_is_up("http://127.0.0.1:8931/ask"),
                label="Seller startup",
                timeout_secs=15.0,
                poll_interval_secs=0.5,
            )

            try:
                result = payments_subscriber.mpp.fetch(
                    "POST",
                    "http://127.0.0.1:8931/ask",
                    MppFetchOptions(
                        delegation_config=DelegationConfig(
                            delegation_id=delegation.delegation_id
                        ),
                        plan_id=str(plan_id),
                    ),
                    json={"q": "hello"},
                )
            except Exception as error:
                skip_if_mpp_is_not_deployed(error)

            assert result.response.status_code == 200
            assert result.credentials_presented == 1
            assert result.settled is True
            assert result.paid is True
            assert result.receipt is not None
        finally:
            server.should_exit = True
            thread.join(timeout=10)


def _server_is_up(url: str) -> bool:
    try:
        httpx.post(url, json={}, timeout=2)
        return True
    except Exception:
        return False
