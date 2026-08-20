"""
Seller-side tests for the MPP opt-in on the FastAPI middleware.

Port of the middleware half of ``nevermined-io/payments`` #417. What these pin
is the edge's own job: routing MPP vs x402, single-use, the in-flight claim,
body binding, and which failures still hand the buyer a fresh challenge.
"""

import hashlib
import base64
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from payments_py.mpp.errors import (
    MppChallengeExpiredError,
    MppError,
    MppSettlementFailed,
    MppSettlementOutcomeUnknown,
    MppSettlementOutcomeUnknownError,
)
from payments_py.x402.fastapi import PaymentMiddleware, PaymentMiddlewareOptions
from payments_py.x402.fastapi import mpp_support

from .fixtures import mpp_credential_fixture


class FakeMppApi:
    """Stands in for ``payments.mpp`` at the seller edge."""

    def __init__(self):
        self.issued: List[Any] = []
        self.verified: List[Any] = []
        self.settled: List[Any] = []
        self.challenge_id = "chal-1"
        self.issue_error: Optional[Exception] = None
        self.verify_error: Optional[Exception] = None
        self.verify_result: Dict[str, Any] = {
            "isValid": True,
            "agentRequestId": "req-1",
        }
        self.settle_error: Optional[Exception] = None
        self.settle_result: Dict[str, Any] = {
            "success": True,
            "paymentReceipt": "RECEIPT-B64",
            "creditsRedeemed": "2",
        }

    def issue_challenge(self, params):
        self.issued.append(params)
        if self.issue_error:
            raise self.issue_error
        return {
            "challenge": f'Payment id="{self.challenge_id}", realm="r"',
            "id": self.challenge_id,
        }

    def verify_credential(self, params):
        self.verified.append(params)
        if self.verify_error:
            raise self.verify_error
        return self.verify_result

    def settle_credential(self, params):
        self.settled.append(params)
        if self.settle_error:
            raise self.settle_error
        return self.settle_result


@pytest.fixture(autouse=True)
def clean_stores():
    mpp_support._reset_stores_for_tests()
    yield
    mpp_support._reset_stores_for_tests()


@pytest.fixture
def payments():
    mock = MagicMock()
    mock.mpp = FakeMppApi()
    mock.environment_name = "sandbox"
    return mock


def build_app(payments, route: Dict[str, Any], options=None, handler=None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        PaymentMiddleware,
        payments=payments,
        routes={"POST /ask": route},
        options=options,
    )

    @app.post("/ask")
    async def ask(request: Request):
        if handler is not None:
            return await handler(request)
        body = await request.body()
        return JSONResponse({"echo": body.decode() or None})

    return app


def client(payments, route=None, options=None, handler=None) -> TestClient:
    route = route or {"plan_id": "plan-1", "credits": 2, "mpp": True}
    return TestClient(build_app(payments, route, options, handler))


CREDENTIAL = mpp_credential_fixture("chal-1")


class TestChallengeIssuance:
    def test_answers_an_unpaid_request_with_a_challenge_advertising_both_protocols(
        self, payments
    ):
        response = client(payments).post("/ask", json={"q": "hi"})

        assert response.status_code == 402
        assert response.headers["www-authenticate"].startswith("Payment ")
        # x402 stays advertised on the same 402, so an x402 buyer is unaffected.
        assert "payment-required" in response.headers
        # The opening request of every payment cycle is credential-less by
        # design, so no code rides along — nothing was rejected.
        assert "code" not in response.json()

    def test_seals_the_route_price_into_the_challenge(self, payments):
        client(payments).post("/ask", json={"q": "hi"})
        issued = payments.mpp.issued[0]
        assert issued.credits == "2"
        assert issued.plan_id == "plan-1"
        assert issued.http_verb == "POST"
        assert issued.resource == "/ask"

    def test_carries_the_query_string_into_the_bound_resource(self, payments):
        client(payments).post("/ask?k=v", json={"q": "hi"})
        assert payments.mpp.issued[0].resource == "/ask?k=v"

    def test_evaluates_a_credits_callable_once_and_seals_the_result(self, payments):
        calls = []

        def credits(request):
            calls.append(request)
            return 7

        client(payments, {"plan_id": "plan-1", "credits": credits, "mpp": True}).post(
            "/ask", json={"q": "hi"}
        )

        assert len(calls) == 1
        assert payments.mpp.issued[0].credits == "7"

    def test_a_throwing_credits_callable_answers_500_not_a_traceback(self, payments):
        def credits(request):
            raise RuntimeError("rate table down")

        response = client(
            payments, {"plan_id": "plan-1", "credits": credits, "mpp": True}
        ).post("/ask", json={"q": "hi"})

        assert response.status_code == 500
        assert "price" in response.json()["message"]
        assert payments.mpp.issued == []

    def test_a_failing_challenge_mint_answers_500_rather_than_propagating(
        self, payments
    ):
        payments.mpp.issue_error = MppError("MPP is not configured", "BCK.MPP.0002")
        response = client(payments).post("/ask", json={"q": "hi"})
        assert response.status_code == 500
        assert "challenge" in response.json()["message"]


class TestCredentialRedemption:
    def test_serves_the_handler_and_attaches_the_receipt(self, payments):
        response = client(payments).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 200
        assert response.headers["payment-receipt"] == "RECEIPT-B64"
        assert len(payments.mpp.verified) == 1
        assert len(payments.mpp.settled) == 1
        assert payments.mpp.settled[0].resource == "/ask"
        assert payments.mpp.settled[0].http_verb == "POST"

    def test_takes_the_mpp_path_when_the_credential_rides_beside_another_scheme(
        self, payments
    ):
        response = client(payments).post(
            "/ask",
            json={"q": "hi"},
            headers={"Authorization": f"{CREDENTIAL}, Bearer app-jwt"},
        )
        assert response.status_code == 200
        assert len(payments.mpp.settled) == 1

    def test_refuses_a_replayed_credential_with_a_fresh_challenge(self, payments):
        c = client(payments)
        first = c.post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})
        second = c.post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        assert first.status_code == 200
        assert second.status_code == 402
        body = second.json()
        # Terminal for THIS credential, with a challenge on the same response so
        # the buyer can still make progress by paying again.
        assert body["code"] == "BCK.MPP.0003"
        assert body["retryable"] is False
        assert second.headers["www-authenticate"].startswith("Payment ")
        # A replay costs no backend round-trip.
        assert len(payments.mpp.verified) == 1

    def test_refuses_a_credential_with_no_decodable_challenge_id(self, payments):
        response = client(payments).post(
            "/ask",
            json={"q": "hi"},
            headers={"Authorization": "Payment !!!not-base64url!!!"},
        )

        assert response.status_code == 402
        assert response.json()["code"] == "BCK.MPP.0003"
        # Refused at the edge, so the backend is never asked.
        assert payments.mpp.verified == []

    def test_forwards_a_backend_rejection_code_and_its_retryability(self, payments):
        payments.mpp.verify_error = MppChallengeExpiredError()

        response = client(payments).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 402
        body = response.json()
        assert body["code"] == "BCK.MPP.0004"
        assert body["retryable"] is True
        # The buyer sees a fixed generic message, never the backend's detail.
        assert body["message"] == "Credential rejected"

    def test_never_forwards_a_non_bck_mpp_code_as_if_it_were_ours(self, payments):
        payments.mpp.verify_error = MppError("upstream blew up", "http_500")

        response = client(payments).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 402
        assert "code" not in response.json()

    def test_marks_a_soft_invalid_verification_as_a_coded_rejection(self, payments):
        payments.mpp.verify_result = {"isValid": False, "invalidReason": "no balance"}

        response = client(payments).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 402
        # Positional wire contract: any 402 answering a request that presented a
        # credential must carry a code, or the buyer mints a second credential
        # for a rejection that already proved terminal.
        assert response.json()["code"] == "BCK.MPP.0003"
        assert "no balance" not in response.text
        assert payments.mpp.settled == []

    def test_refuses_a_credential_already_claimed_by_a_concurrent_request(
        self, payments
    ):
        mpp_support.claim_credential("chal-1")

        response = client(payments).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 409
        assert payments.mpp.settled == []

    def test_releases_the_claim_when_the_handler_raises(self, payments):
        async def boom(request):
            raise RuntimeError("handler exploded")

        c = client(payments, handler=boom)
        with pytest.raises(RuntimeError):
            c.post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        # Claimed and released: a retry with the same credential is not 409'd
        # forever, and nothing settled for a run that failed.
        assert mpp_support.claim_credential("chal-1") is True
        assert payments.mpp.settled == []


class TestSettlement:
    def test_does_not_settle_a_non_2xx_handler_response(self, payments):
        async def refuse(request):
            return JSONResponse({"error": "nope"}, status_code=400)

        response = client(payments, handler=refuse).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 400
        assert payments.mpp.settled == []
        # The credential was never spent, so the buyer can use it again.
        assert mpp_support.is_credential_spent("chal-1") is False

    def test_keeps_the_2xx_when_settlement_fails_and_reports_zero_credits(
        self, payments
    ):
        payments.mpp.settle_error = MppError("settle refused", "BCK.MPP.0003")
        seen: List[Any] = []

        async def on_payment_error(error, request):
            seen.append(error)
            return None

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_payment_error=on_payment_error),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        # The agent already delivered the value; an internal settle failure is
        # not the buyer's problem — but the seller must hear about it.
        assert response.status_code == 200
        assert "payment-receipt" not in response.headers
        assert len(seen) == 1

    def test_reports_a_definite_settlement_failure_to_the_after_settle_hook(
        self, payments
    ):
        payments.mpp.settle_error = MppError("settle refused", "BCK.MPP.0003")
        settlements: List[Any] = []

        async def on_after_settle(request, credits, settlement):
            settlements.append((credits, settlement))

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        assert response.status_code == 200
        # Delivered and definitely not paid is the count a seller most needs.
        # Reporting only settled and unknown would leave it as an ABSENCE from
        # the hook their ledger is built on — indistinguishable from a request
        # that was never an MPP request at all.
        assert len(settlements) == 1
        credits, settlement = settlements[0]
        assert isinstance(settlement, MppSettlementFailed)
        assert settlement.outcome == "failed"
        assert credits == 0

    def test_reports_an_unknown_settlement_outcome_to_the_after_settle_hook(
        self, payments
    ):
        payments.mpp.settle_error = MppSettlementOutcomeUnknownError()
        settlements: List[Any] = []

        async def on_after_settle(request, credits, settlement):
            settlements.append((credits, settlement))

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        assert response.status_code == 200
        # A burn that may have happened must not vanish from the seller's own
        # accounting, so the hook still runs — with the outcome named.
        assert len(settlements) == 1
        credits, settlement = settlements[0]
        assert isinstance(settlement, MppSettlementOutcomeUnknown)
        assert settlement.outcome == "unknown"
        assert credits == 2

    def test_reports_the_amount_the_backend_says_it_burned(self, payments):
        payments.mpp.settle_result = {
            "success": True,
            "paymentReceipt": "R",
            "creditsRedeemed": "9",
        }
        settlements: List[Any] = []

        async def on_after_settle(request, credits, settlement):
            settlements.append(credits)

        client(
            payments,
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        # The challenge sealed the amount on an EARLIER request, so what burned
        # is what the settlement reports — not what this request would charge.
        assert settlements == [9]

    def test_reports_zero_for_a_settlement_that_returned_unsuccessful(self, payments):
        payments.mpp.settle_result = {"success": False, "errorReason": "insufficient"}
        settlements: List[Any] = []

        async def on_after_settle(request, credits, settlement):
            settlements.append(credits)

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        assert response.status_code == 200
        assert "payment-receipt" not in response.headers
        # A failed settle burned nothing: a seller writing revenue records off
        # this argument must not over-report it at the full charge.
        assert settlements == [0]

    def test_a_throwing_after_settle_hook_does_not_break_the_response(self, payments):
        async def on_after_settle(request, credits, settlement):
            raise RuntimeError("hook bug")

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        assert response.status_code == 200
        assert response.headers["payment-receipt"] == "RECEIPT-B64"


class TestBodyBinding:
    ROUTE = {"plan_id": "plan-1", "credits": 2, "mpp": {"bind_body": True}}

    def test_binds_the_challenge_to_the_digest_of_the_body_sent(self, payments):
        c = client(payments, self.ROUTE)
        c.post("/ask", content=b'{"q":"hi"}')

        expected = base64.b64encode(hashlib.sha256(b'{"q":"hi"}').digest()).decode()
        assert payments.mpp.issued[0].digest == f"sha-256={expected}"

    def test_the_handler_still_receives_the_body_the_buyer_sent(self, payments):
        # Reading the raw body in the middleware consumes the ASGI receive
        # channel; without the re-arm the handler would see an empty body.
        response = client(payments, self.ROUTE).post(
            "/ask", content=b'{"q":"hi"}', headers={"Authorization": CREDENTIAL}
        )

        assert response.status_code == 200
        assert response.json() == {"echo": '{"q":"hi"}'}

    def test_binds_the_digest_of_zero_bytes_when_the_request_has_no_body(
        self, payments
    ):
        client(payments, self.ROUTE).post("/ask")

        # Not "unbound": leaving it empty would let the buyer mint with an empty
        # request and attach any body they liked to the paid retry.
        assert payments.mpp.issued[0].digest == mpp_support.EMPTY_BODY_DIGEST

    def test_forwards_the_digest_to_verify_and_settle(self, payments):
        client(payments, self.ROUTE).post(
            "/ask", content=b'{"q":"hi"}', headers={"Authorization": CREDENTIAL}
        )

        expected = base64.b64encode(hashlib.sha256(b'{"q":"hi"}').digest()).decode()
        digest = f"sha-256={expected}"
        assert payments.mpp.verified[0].body_digest == digest
        assert payments.mpp.settled[0].body_digest == digest

    def test_does_not_touch_the_body_when_bind_body_is_off(self, payments):
        response = client(payments).post(
            "/ask", content=b'{"q":"hi"}', headers={"Authorization": CREDENTIAL}
        )
        assert response.json() == {"echo": '{"q":"hi"}'}
        assert payments.mpp.issued == []


class TestHookPolicy:
    def test_does_not_notify_on_the_credential_less_opening_request(self, payments):
        seen: List[Any] = []

        async def on_payment_error(error, request):
            seen.append(error)
            return None

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_payment_error=on_payment_error),
        ).post("/ask", json={"q": "hi"})

        # Notifying here would fire on every successful payment's first turn,
        # drowning the rejections the hook exists to surface.
        assert response.status_code == 402
        assert seen == []

    def test_notifies_when_an_authorization_header_carries_no_payment_scheme(
        self, payments
    ):
        seen: List[Any] = []

        async def on_payment_error(error, request):
            seen.append(error)
            return None

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_payment_error=on_payment_error),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": "Bearer app-jwt"})

        # An intermediary rewriting the header puts the buyer in a silent
        # infinite loop that is invisible on the only side that can fix it.
        assert response.status_code == 402
        assert len(seen) == 1

    def test_runs_the_before_and_after_verify_hooks(self, payments):
        order: List[str] = []

        async def on_before_verify(request, payment_required):
            order.append("before")

        async def on_after_verify(request, verification):
            order.append("after")

        client(
            payments,
            options=PaymentMiddlewareOptions(
                on_before_verify=on_before_verify, on_after_verify=on_after_verify
            ),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        # Adding mpp=True to a working route must not silently disable a
        # documented hook.
        assert order == ["before", "after"]

    def test_an_after_verify_hook_bug_is_not_reported_as_a_payment_rejection(
        self, payments
    ):
        async def on_after_verify(request, verification):
            raise RuntimeError("hook bug")

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_after_verify=on_after_verify),
        ).post("/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL})

        # A 402 here would tell the buyer to pay again for a credential that was
        # already proven valid.
        assert response.status_code == 500
        assert "hook" in response.json()["message"]
        assert payments.mpp.settled == []


class TestHookOwnershipOnFailurePaths:
    def test_a_hook_that_answers_wins_when_challenge_issuance_fails(self, payments):
        payments.mpp.issue_error = MppError("MPP is not configured", "BCK.MPP.0002")

        async def on_payment_error(error, request):
            return JSONResponse({"branded": True}, status_code=503)

        response = client(
            payments,
            options=PaymentMiddlewareOptions(on_payment_error=on_payment_error),
        ).post("/ask", json={"q": "hi"})

        # The credits callable next door honours the same hook, and both are
        # reachable from the same BCK.MPP.0002 condition — issuance was the one
        # server-side failure a seller could not shape.
        assert response.status_code == 503
        assert response.json() == {"branded": True}

    def test_a_hook_that_answers_wins_when_the_credits_callable_throws(self, payments):
        def credits(request):
            raise RuntimeError("rate table down")

        async def on_payment_error(error, request):
            return JSONResponse({"branded": True}, status_code=503)

        response = client(
            payments,
            {"plan_id": "plan-1", "credits": credits, "mpp": True},
            options=PaymentMiddlewareOptions(on_payment_error=on_payment_error),
        ).post("/ask", json={"q": "hi"})

        assert response.status_code == 503


class TestRouteOptionValidation:
    @pytest.mark.parametrize(
        "option",
        [{"bindBody": True}, {"bind-body": True}, {"bind_body": "true"}],
        ids=["camelCase-key", "kebab-key", "string-value"],
    )
    def test_refuses_a_mistyped_mpp_option_at_startup(self, payments, option):
        # Silently resolving these to bind_body=False turns OFF a security
        # control: with no digest bound the backend skips the comparison, so the
        # buyer decides whether body binding applies — mint against an empty
        # request, attach any body to the paid retry. The outer route dict
        # already raises for an unknown key; this was the one nested place that
        # accepted anything.
        with pytest.raises(TypeError):
            build_app(
                payments, {"plan_id": "plan-1", "credits": 2, "mpp": option}
            ).build_middleware_stack()

    @pytest.mark.parametrize("option", [True, False, None, {"bind_body": True}, {}])
    def test_accepts_every_supported_shape(self, payments, option):
        build_app(
            payments, {"plan_id": "plan-1", "credits": 2, "mpp": option}
        ).build_middleware_stack()


class TestSingleUseTtl:
    """The spent-store window follows the challenge, not a copied constant."""

    def iso(self, seconds_from_now: float) -> str:
        return (
            (datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now))
            .isoformat()
            .replace("+00:00", "Z")
        )

    def test_defaults_to_the_floor_when_the_challenge_states_no_expiry(self):
        assert mpp_support._ttl_for(None) == mpp_support.SPENT_CREDENTIAL_TTL_SECONDS

    def test_follows_a_backend_ttl_longer_than_the_floor(self):
        # This is the drift the constant alone could not notice: if the backend
        # raises MPP_CHALLENGE_TTL_SECONDS, a store pinned to 300 forgets a
        # credential the backend still honours, and "single use" quietly becomes
        # "replayable after 300 seconds".
        assert 550 < mpp_support._ttl_for(self.iso(600)) <= 600

    @pytest.mark.parametrize(
        "expires", [None, "not-a-date", ""], ids=["absent", "garbage", "empty"]
    )
    def test_never_drops_below_the_floor_on_an_unusable_value(self, expires):
        assert mpp_support._ttl_for(expires) == mpp_support.SPENT_CREDENTIAL_TTL_SECONDS

    def test_never_drops_below_the_floor_on_an_already_past_expiry(self):
        # The value is buyer-supplied and the seller's clock may be skewed, so a
        # value that reads as expired must not shrink the replay window.
        assert (
            mpp_support._ttl_for(self.iso(-9999))
            == mpp_support.SPENT_CREDENTIAL_TTL_SECONDS
        )

    def test_is_bounded_above_so_a_crafted_expiry_cannot_pin_memory(self):
        assert (
            mpp_support._ttl_for(self.iso(10**7))
            == mpp_support.SPENT_CREDENTIAL_MAX_TTL_SECONDS
        )

    def test_the_seller_passes_the_credentials_own_expiry_through(
        self, payments, monkeypatch
    ):
        seen: List[Any] = []
        real = mpp_support.mark_credential_spent
        monkeypatch.setattr(
            mpp_support,
            "mark_credential_spent",
            lambda cid, expires=None: (seen.append(expires), real(cid, expires))[1],
        )
        monkeypatch.setattr(
            "payments_py.x402.fastapi.mpp_flow.mark_credential_spent",
            mpp_support.mark_credential_spent,
        )

        expires = self.iso(600)
        credential = mpp_credential_fixture("chal-ttl", expires=expires)
        client(payments).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": credential}
        )

        assert seen == [expires]


class TestProtocolRouting:
    def test_leaves_the_x402_path_alone_when_mpp_is_not_enabled(self, payments):
        response = client(payments, {"plan_id": "plan-1", "credits": 2}).post(
            "/ask", json={"q": "hi"}
        )

        assert response.status_code == 402
        assert "www-authenticate" not in response.headers
        assert payments.mpp.issued == []

    def test_falls_through_to_x402_when_a_token_is_present_and_no_credential_is(
        self, payments
    ):
        response = client(payments).post(
            "/ask", json={"q": "hi"}, headers={"payment-signature": "x402-token"}
        )

        # The x402 buyer of an MPP-enabled route is served by the x402 flow,
        # untouched.
        assert payments.mpp.issued == []
        assert payments.facilitator.verify_permissions.called
        assert response.status_code == 200

    def test_an_mpp_credential_wins_over_a_present_x402_token(self, payments):
        response = client(payments).post(
            "/ask",
            json={"q": "hi"},
            headers={"Authorization": CREDENTIAL, "payment-signature": "x402-token"},
        )

        assert response.status_code == 200
        assert len(payments.mpp.settled) == 1
        assert not payments.facilitator.settle_permissions.called


class TestPaymentContext:
    def test_exposes_the_mpp_framing_to_the_handler(self, payments):
        seen: List[Any] = []

        async def handler(request):
            seen.append(request.state.payment_context)
            return JSONResponse({"ok": True})

        client(payments, handler=handler).post(
            "/ask", json={"q": "hi"}, headers={"Authorization": CREDENTIAL}
        )

        context = seen[0]
        assert context.verified is True
        assert context.mpp.resource == "/ask"
        assert context.mpp.http_verb == "POST"
        assert context.mpp.credential.startswith("Payment ")
        assert context.agent_request_id == "req-1"
