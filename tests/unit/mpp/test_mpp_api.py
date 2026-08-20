"""
Tests for ``payments.mpp``'s own HTTP surface.

Port of ``tests/unit/mpp/mpp-api.test.ts`` and ``errors.test.ts`` in
``nevermined-io/payments`` (#417/#418). The property that carries the most
weight is the ``burns`` classification: settlement is the one MPP call that
burns, so "definitely nothing happened" and "the credits may already be gone"
must never be reported through the same error.
"""

import json
from typing import Any, Optional

import pytest
import requests

from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.mpp.errors import (
    RETRYABLE_BCK_MPP_CODES,
    MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE,
    MppBodyDigestMismatchError,
    MppChallengeExpiredError,
    MppCredentialRejectedError,
    MppError,
    MppNotConfiguredError,
    MppSettlementOutcomeUnknownError,
    MppSpendReport,
    is_retryable_mpp_code,
    mpp_spend_of,
    to_mpp_error,
)
from payments_py.mpp.fetch import MppFetchOptions
from payments_py.mpp.mpp_api import (
    IssueMppChallengeParams,
    MppAPI,
    RedeemMppParams,
    normalize_credits,
)
from payments_py.x402.types import DelegationConfig

from .conftest import make_response

# The same JWT-shaped key the x402 token tests use — the SDK parses it, and
# nothing here reaches the network.
API_KEY = (
    "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
)


@pytest.fixture
def api() -> MppAPI:
    return MppAPI.get_instance(
        PaymentOptions(nvm_api_key=API_KEY, environment="sandbox")
    )


@pytest.fixture
def post(monkeypatch):
    """Install a stub over ``requests.post`` in the MPP API module."""

    def install(result: Any):
        calls = []

        def fake_post(url, **kwargs):
            calls.append({"url": url, **kwargs})
            if isinstance(result, BaseException):
                raise result
            return result

        monkeypatch.setattr("payments_py.mpp.mpp_api.requests.post", fake_post)
        return calls

    return install


class TestNormalizeCredits:
    @pytest.mark.parametrize(
        "value,expected",
        [
            ("5", "5"),
            ("0", "0"),
            (5, "5"),
            (0, "0"),
            (5.0, "5"),
            (10**30, "1" + "0" * 30),
        ],
        ids=repr,
    )
    def test_accepts_a_non_negative_integer_amount(self, value, expected):
        assert normalize_credits(value) == expected

    @pytest.mark.parametrize(
        "value",
        [
            "",
            " 5 ",
            "0x10",
            "1e3",
            "2.5",
            "-1",
            "1_0",
            -1,
            2.5,
            True,
            float("nan"),
            float("inf"),
        ],
        ids=repr,
    )
    def test_refuses_anything_else(self, value):
        # A corrupted amount here is not correctable downstream — it IS the
        # amount the challenge seals and the backend burns.
        with pytest.raises(MppError):
            normalize_credits(value)


class TestIssueChallenge:
    def test_sends_the_normalized_amount_and_the_binding(self, api, post):
        calls = post(make_response(200, body=json.dumps({"challenge": "c", "id": "1"})))

        api.issue_challenge(
            IssueMppChallengeParams(
                plan_id="plan-1",
                credits=5,
                resource="/ask",
                http_verb="POST",
                digest="sha-256=abc",
                description="ask",
            )
        )

        body = json.loads(calls[0]["data"])
        assert body["planId"] == "plan-1"
        assert body["credits"] == "5"
        assert body["resource"] == "/ask"
        assert body["httpVerb"] == "POST"
        assert body["digest"] == "sha-256=abc"

    def test_omits_the_optional_fields_that_were_not_given(self, api, post):
        calls = post(make_response(200, body=json.dumps({"challenge": "c", "id": "1"})))

        api.issue_challenge(
            IssueMppChallengeParams(
                plan_id="plan-1", credits="1", resource="/ask", http_verb="GET"
            )
        )

        body = json.loads(calls[0]["data"])
        assert "digest" not in body
        assert "agentId" not in body
        assert "description" not in body

    def test_maps_a_backend_code_onto_the_typed_hierarchy(self, api, post):
        post(
            make_response(
                400,
                body=json.dumps({"code": "BCK.MPP.0002", "message": "MPP is off"}),
            )
        )

        with pytest.raises(MppNotConfiguredError) as excinfo:
            api.issue_challenge(
                IssueMppChallengeParams(
                    plan_id="plan-1", credits="1", resource="/ask", http_verb="GET"
                )
            )
        assert excinfo.value.code == "BCK.MPP.0002"

    def test_folds_a_backend_hint_onto_the_message(self, api, post):
        post(
            make_response(
                400,
                body=json.dumps(
                    {"code": "BCK.MPP.0003", "message": "refused", "hint": "expired"}
                ),
            )
        )

        with pytest.raises(MppCredentialRejectedError) as excinfo:
            api.issue_challenge(
                IssueMppChallengeParams(
                    plan_id="plan-1", credits="1", resource="/ask", http_verb="GET"
                )
            )
        assert "expired" in str(excinfo.value)

    def test_a_non_json_success_body_raises_a_typed_error(self, api, post):
        post(make_response(200, body="<html>gateway</html>"))

        with pytest.raises(MppError) as excinfo:
            api.issue_challenge(
                IssueMppChallengeParams(
                    plan_id="plan-1", credits="1", resource="/ask", http_verb="GET"
                )
            )
        assert excinfo.value.code == "http_200"

    def test_a_network_failure_is_a_definite_failure(self, api, post):
        post(requests.exceptions.ConnectionError("refused"))

        with pytest.raises(MppError) as excinfo:
            api.issue_challenge(
                IssueMppChallengeParams(
                    plan_id="plan-1", credits="1", resource="/ask", http_verb="GET"
                )
            )
        assert excinfo.value.code == "network_error"
        assert not isinstance(excinfo.value, MppSettlementOutcomeUnknownError)


class TestSettleCredentialBurns:
    def redeem(self) -> RedeemMppParams:
        return RedeemMppParams(
            credential="Payment abc", resource="/ask", http_verb="POST"
        )

    def test_forwards_the_body_digest_when_the_challenge_bound_one(self, api, post):
        calls = post(make_response(200, body=json.dumps({"success": True})))

        api.settle_credential(
            RedeemMppParams(
                credential="Payment abc",
                resource="/ask",
                http_verb="POST",
                body_digest="sha-256=abc",
            )
        )

        assert json.loads(calls[0]["data"])["bodyDigest"] == "sha-256=abc"

    def test_a_read_timeout_is_an_unknown_outcome(self, api, post):
        # The request was written and the answer never arrived: the burn may
        # have committed.
        post(requests.exceptions.ReadTimeout("timed out"))

        with pytest.raises(MppSettlementOutcomeUnknownError) as excinfo:
            api.settle_credential(self.redeem())
        assert excinfo.value.code == MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE

    def test_a_connect_timeout_is_a_definite_failure(self, api, post):
        # Nothing was written, so nothing can have burned — reporting it as
        # unknown would inflate the seller's records with burns that never
        # happened.
        post(requests.exceptions.ConnectTimeout("no route"))

        with pytest.raises(MppError) as excinfo:
            api.settle_credential(self.redeem())
        assert not isinstance(excinfo.value, MppSettlementOutcomeUnknownError)
        assert excinfo.value.code == "network_error"

    def test_a_connection_reset_after_the_write_is_an_unknown_outcome(self, api, post):
        post(
            requests.exceptions.ConnectionError(
                "Connection aborted.", ConnectionResetError(104, "reset by peer")
            )
        )

        with pytest.raises(MppSettlementOutcomeUnknownError):
            api.settle_credential(self.redeem())

    def test_a_refused_connection_stays_a_definite_failure(self, api, post):
        post(requests.exceptions.ConnectionError("Connection refused"))

        with pytest.raises(MppError) as excinfo:
            api.settle_credential(self.redeem())
        assert not isinstance(excinfo.value, MppSettlementOutcomeUnknownError)

    @pytest.mark.parametrize("status", [500, 502, 504, 408])
    def test_a_5xx_or_408_is_an_unknown_outcome(self, api, post, status):
        post(make_response(status, body=json.dumps({"message": "upstream"})))

        with pytest.raises(MppSettlementOutcomeUnknownError):
            api.settle_credential(self.redeem())

    def test_a_4xx_is_a_definite_rejection(self, api, post):
        # The backend's own rejections are definite — reporting those as
        # unknown would corrupt the accounting in the other direction.
        post(make_response(400, body=json.dumps({"code": "BCK.MPP.0003"})))

        with pytest.raises(MppCredentialRejectedError):
            api.settle_credential(self.redeem())

    def test_an_unreadable_2xx_body_is_an_unknown_outcome(self, api, post):
        # The backend already answered 2xx — the burn committed — and only the
        # body was lost. If anything this is MORE likely to have burned than the
        # pre-response timeout the error was introduced for.
        post(make_response(200, body="<html>truncated"))

        with pytest.raises(MppSettlementOutcomeUnknownError):
            api.settle_credential(self.redeem())

    def test_a_non_burning_call_never_reports_an_unknown_outcome(self, api, post):
        post(requests.exceptions.ReadTimeout("timed out"))

        with pytest.raises(MppError) as excinfo:
            api.verify_credential(self.redeem())
        assert not isinstance(excinfo.value, MppSettlementOutcomeUnknownError)


class TestGetMppAccessToken:
    def test_posts_to_the_mpp_permissions_route(self, api, post):
        calls = post(make_response(200, body=json.dumps({"accessToken": "tok"})))

        api.get_mpp_access_token("plan-1")

        # A sibling route of /api/v1/x402, never a child: the tokens are
        # byte-identical on the wire, so the route is what isolates them.
        assert calls[0]["url"].endswith("/api/v1/mpp/permissions")


class TestFetchGuard:
    def test_refuses_a_delegation_config_with_no_delegation_id(self, api):
        with pytest.raises(PaymentsError) as excinfo:
            api.fetch(
                "GET",
                "https://agent.example/ask",
                MppFetchOptions(
                    delegation_config=DelegationConfig(spending_limit_cents=100)
                ),
            )
        # The retry loop can mint twice per call, so an inline create-on-the-fly
        # config would silently create two delegations as a side effect.
        assert "delegation_id" in str(excinfo.value)

    def test_refuses_a_missing_delegation_config(self, api):
        with pytest.raises(PaymentsError):
            api.fetch(
                "GET",
                "https://agent.example/ask",
                MppFetchOptions(delegation_config=None),
            )


class TestErrorHierarchy:
    @pytest.mark.parametrize(
        "code,expected",
        [
            ("BCK.MPP.0002", MppNotConfiguredError),
            ("BCK.MPP.0003", MppCredentialRejectedError),
            ("BCK.MPP.0004", MppChallengeExpiredError),
            ("BCK.MPP.0005", MppBodyDigestMismatchError),
        ],
    )
    def test_maps_each_backend_code_to_its_type(self, code, expected):
        error = to_mpp_error(code, "boom")
        assert isinstance(error, expected)
        assert error.code == code

    def test_an_unknown_code_stays_a_plain_mpp_error(self):
        error = to_mpp_error("BCK.OTHER.0001", "boom")
        assert type(error) is MppError
        assert error.code == "BCK.OTHER.0001"

    @pytest.mark.parametrize("code", sorted(RETRYABLE_BCK_MPP_CODES))
    def test_the_retryable_set_is_retryable(self, code):
        assert is_retryable_mpp_code(code) is True

    @pytest.mark.parametrize(
        "code", ["BCK.MPP.0002", "BCK.MPP.0003", "BCK.MPP.0099", None, "network_error"]
    )
    def test_everything_else_is_terminal(self, code):
        assert is_retryable_mpp_code(code) is False

    def test_the_sdk_invented_codes_can_never_collide_with_a_backend_one(self):
        assert not MPP_SETTLEMENT_OUTCOME_UNKNOWN_CODE.startswith("BCK.MPP.")

    def test_mpp_spend_of_reads_the_report_off_any_error(self):
        report = MppSpendReport(credentials_presented=1, credits_presented="2")
        error = PaymentsError.validation("nope")
        error.spend = report
        # It rides on PaymentsError too — the two hierarchies share no base.
        assert mpp_spend_of(error) is report

    @pytest.mark.parametrize(
        "error", [MppError("plain"), PaymentsError.validation("nope"), None, "x"]
    )
    def test_mpp_spend_of_is_none_when_nothing_was_spent(self, error):
        # A truthy report on a plain validation failure would send a caller
        # following the documented pattern into the "credits may be burned"
        # branch for an error that never reached the seller.
        assert mpp_spend_of(error) is None
