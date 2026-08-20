"""
Buyer-side tests for ``payments.mpp.fetch``.

Port of ``tests/unit/mpp/mpp-fetch.test.ts`` in ``nevermined-io/payments``
(#418). The money-path properties are what these pin: how many credentials were
minted, what the retry gate decides, and what every exit reports about credits
that may already have burned.
"""

import json

import pytest
import requests

from payments_py.common.payments_error import PaymentsError
from payments_py.mpp.errors import (
    RETRYABLE_BCK_MPP_CODES,
    MppCredentialRejectedError,
    MppError,
    MppSpendOutcomeUnknownError,
    mpp_spend_of,
)
from payments_py.mpp.fetch import MAX_ERROR_BODY_BYTES, MppFetchOptions, mpp_fetch
from payments_py.x402.types import DelegationConfig

from .conftest import DEFAULT_URL, FakeMinter, make_response
from .fixtures import b64url, b64url_json

PLAN_ID = "plan-123"


def challenge_header(
    challenge_id: str = "c1",
    credits="2",
    plan_id: str = PLAN_ID,
    agent_id=None,
) -> str:
    request = {"planId": plan_id, "credits": credits}
    if agent_id is not None:
        request["agentId"] = agent_id
    return (
        f'Payment id="{challenge_id}", realm="api.nevermined.app", '
        f'method="nevermined", intent="charge", request="{b64url_json(request)}"'
    )


def receipt_header(status: str = "success", reference: str = "c1") -> str:
    return b64url(
        json.dumps(
            {
                "method": "nevermined",
                "reference": reference,
                "status": status,
                "timestamp": "2026-08-12T10:00:30.000Z",
            }
        ).encode("utf-8")
    )


def options(**overrides) -> MppFetchOptions:
    base = {
        "delegation_config": DelegationConfig(delegation_id="del-1"),
    }
    base.update(overrides)
    return MppFetchOptions(**base)


def challenged(
    challenge_id: str = "c1", credits="2", body: bytes = b""
) -> requests.Response:
    return make_response(
        402, {"www-authenticate": challenge_header(challenge_id, credits)}, body
    )


def paid_ok(status: str = "success") -> requests.Response:
    return make_response(200, {"payment-receipt": receipt_header(status)}, b'{"ok":1}')


class TestHappyPath:
    def test_pays_a_402_and_retries_once_reporting_settlement_honestly(
        self, transport, minter
    ):
        fake = transport([challenged(), paid_ok()])

        result = mpp_fetch(minter, "POST", DEFAULT_URL, options(), json={"q": "hi"})

        assert fake.count == 2
        assert minter.count == 1
        assert result.response.status_code == 200
        assert result.settled is True
        assert result.paid is True
        assert result.credentials_presented == 1
        assert result.credits_presented == "2"
        assert result.receipt.status == "success"
        # The credential rides on the retry, never on the first attempt.
        assert "Authorization" not in (fake.calls[0].get("headers") or {})
        assert fake.calls[1]["headers"]["Authorization"].startswith("Payment ")

    def test_reads_the_plan_out_of_the_sealed_challenge(self, transport, minter):
        transport([challenged(), paid_ok()])
        mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.calls[0]["plan_id"] == PLAN_ID

    def test_honours_the_agent_id_the_challenge_names(self, transport, minter):
        transport(
            [
                make_response(
                    402, {"www-authenticate": challenge_header(agent_id="agent-9")}
                ),
                paid_ok(),
            ]
        )
        mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.calls[0]["agent_id"] == "agent-9"

    def test_an_explicit_agent_id_overrides_the_one_the_challenge_names(
        self, transport, minter
    ):
        transport(
            [
                make_response(
                    402, {"www-authenticate": challenge_header(agent_id="agent-9")}
                ),
                paid_ok(),
            ]
        )
        mpp_fetch(minter, "GET", DEFAULT_URL, options(agent_id="agent-mine"))
        assert minter.calls[0]["agent_id"] == "agent-mine"

    def test_returns_a_non_402_response_untouched_without_minting(
        self, transport, minter
    ):
        fake = transport([make_response(200, body=b'{"ok":1}')])

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert fake.count == 1
        assert minter.count == 0
        assert result.response.status_code == 200
        assert result.paid is False
        assert result.settled is False
        assert result.credentials_presented == 0
        assert result.credits_presented is None

    def test_returns_a_402_with_no_www_authenticate_untouched(self, transport, minter):
        transport([make_response(402, body=b"nope")])
        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 0
        assert result.response.status_code == 402
        assert result.credentials_presented == 0

    def test_returns_a_402_whose_challenge_is_another_scheme_untouched(
        self, transport, minter
    ):
        transport([make_response(402, {"www-authenticate": 'Bearer realm="x"'})])
        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 0
        assert result.response.status_code == 402
        assert result.credentials_presented == 0


class TestReChallengeGateDefaultsToStop:
    def test_does_not_re_mint_when_a_seller_rejects_without_a_code(
        self, transport, minter
    ):
        # Identical challenge id replayed and no code: a credential already
        # proven invalid is never paid for twice.
        transport([challenged("c1"), challenged("c1", body=b'{"message":"nope"}')])

        with pytest.raises(MppError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert minter.count == 1
        assert "rejected the credential" in str(excinfo.value)

    def test_mints_once_per_fresh_re_challenge_then_stops_at_the_loop_bound(
        self, transport, minter
    ):
        fake = transport([challenged("c1"), challenged("c2"), challenged("c3")])

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        # Two mints, then the budget is spent and the last 402 comes back
        # rather than raising — a credential was presented and may have burned.
        assert minter.count == 2
        assert fake.count == 3
        assert result.response.status_code == 402
        assert result.paid is False
        assert result.credentials_presented == 2
        assert result.credits_presented == "4"

    def test_surfaces_a_coded_rejection_as_credential_rejected_with_one_mint(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2")},
                    json.dumps({"code": "BCK.MPP.0003", "message": "replayed"}),
                ),
            ]
        )

        with pytest.raises(MppCredentialRejectedError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        # A fresh challenge id sits on that 402, and it is deliberately ignored:
        # the code decides alone.
        assert minter.count == 1

    @pytest.mark.parametrize("code", sorted(RETRYABLE_BCK_MPP_CODES))
    def test_retries_exactly_once_on_a_retryable_code(self, transport, minter, code):
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2")},
                    json.dumps({"code": code, "message": "retry"}),
                ),
                paid_ok(),
            ]
        )

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert minter.count == 2
        assert result.paid is True
        assert result.credits_presented == "4"

    @pytest.mark.parametrize(
        "code", ["BCK.MPP.0002", "BCK.MPP.0003", "BCK.MPP.0099", "http_500"]
    )
    def test_treats_every_other_code_as_terminal(self, transport, minter, code):
        # Including a non-BCK.MPP one — the synthetic network_error/http_500
        # shape MppAPI._post can produce and this SDK's own seller forwards.
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2")},
                    json.dumps({"code": code, "message": "no"}),
                ),
            ]
        )

        with pytest.raises(MppError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 1

    def test_treats_an_unreadable_non_json_402_body_as_terminal(
        self, transport, minter
    ):
        # An HTML WAF page is not evidence of a fresh challenge, even though a
        # fresh challenge id sits in the header.
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2")},
                    "<html>blocked</html>",
                ),
            ]
        )

        with pytest.raises(MppError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 1

    def test_attributes_and_truncates_the_remote_rejection_message(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {},
                    json.dumps({"code": "BCK.MPP.0003", "message": "x" * 500}),
                ),
            ]
        )

        with pytest.raises(MppError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        message = str(excinfo.value)
        assert "https://agent.example" in message
        assert "x" * 200 in message
        assert "x" * 201 not in message

    def test_coerces_a_non_string_message_field_to_the_fallback(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {},
                    json.dumps({"code": "BCK.MPP.0003", "error": {"reason": "nope"}}),
                ),
            ]
        )

        with pytest.raises(MppError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert "MPP request failed" in str(excinfo.value)


class TestMalformedChallengeAndReceipt:
    def test_raises_a_typed_error_when_the_challenge_cannot_be_decoded(
        self, transport, minter
    ):
        transport(
            [
                make_response(
                    402,
                    {
                        "www-authenticate": (
                            'Payment id="c1", realm="r", method="nevermined", '
                            'intent="charge", request="zzz"'
                        )
                    },
                )
            ]
        )

        with pytest.raises(MppError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert minter.count == 0
        assert "No payment was attempted" in str(excinfo.value)

    def test_refuses_a_challenge_that_names_no_plan_id_before_minting(
        self, transport, minter
    ):
        transport(
            [
                make_response(
                    402,
                    {
                        "www-authenticate": (
                            'Payment id="c1", realm="r", method="nevermined", '
                            f'intent="charge", request="{b64url_json({"credits": "2"})}"'
                        )
                    },
                )
            ]
        )

        with pytest.raises(MppError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 0

    def test_coerces_a_numeric_credits_rather_than_refusing_it(self, transport, minter):
        transport([challenged(credits=2), paid_ok()])
        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert result.paid is True
        assert result.credits_presented == "2"

    @pytest.mark.parametrize("credits", ["2.5", "-1", "1e3", "abc"])
    def test_refuses_a_non_decimal_credits_string_before_minting(
        self, transport, minter, credits
    ):
        transport([challenged(credits=credits)])
        with pytest.raises(MppError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 0
        assert "refusing to mint" in str(excinfo.value)

    def test_a_malformed_receipt_is_absent_and_warned_not_raised(
        self, transport, minter, caplog
    ):
        transport([challenged(), make_response(200, {"payment-receipt": "zzz"})])

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert result.response.status_code == 200
        assert result.receipt is None
        assert result.settled is False
        assert result.credentials_presented == 1
        assert "Payment-Receipt could not be decoded" in caplog.text


class TestPaidAndSettledReflectEvidenceNotStatus:
    def test_settled_true_on_a_valid_receipt_even_when_the_response_is_non_2xx(
        self, transport, minter
    ):
        transport(
            [
                challenged(),
                make_response(500, {"payment-receipt": receipt_header()}, b"boom"),
            ]
        )

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert result.settled is True
        assert result.paid is False
        assert result.credentials_presented == 1

    def test_paid_false_for_a_2xx_with_no_receipt(self, transport, minter):
        transport([challenged(), make_response(200, body=b'{"ok":1}')])

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert result.response.status_code == 200
        assert result.settled is False
        assert result.paid is False
        assert result.credentials_presented == 1
        assert result.credits_presented == "2"

    @pytest.mark.parametrize(
        "status", ["failed", "FAILED", " Declined ", "Failure", "ERROR"]
    )
    def test_an_explicit_failure_status_is_not_settled(self, transport, minter, status):
        transport([challenged(), paid_ok(status)])
        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert result.settled is False
        assert result.paid is False
        assert result.receipt is not None

    @pytest.mark.parametrize("status", ["completed", "ok", "SUCCESS", "settled"])
    def test_an_unrecognized_status_is_still_settled(self, transport, minter, status):
        # Success is deliberately not recognized: reporting an unpaid call that
        # was in fact paid is the wrong direction to be wrong in.
        transport([challenged(), paid_ok(status)])
        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert result.settled is True
        assert result.paid is True


class TestGuardsArePaymentsErrors:
    def test_refuses_a_challenge_that_names_a_different_pinned_plan(
        self, transport, minter
    ):
        transport([challenged()])
        with pytest.raises(PaymentsError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options(plan_id="other-plan"))
        assert minter.count == 0

    def test_refuses_a_challenge_above_the_callers_cap(self, transport, minter):
        transport([challenged(credits="10")])
        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits="5"))
        assert minter.count == 0
        assert "above the caller's cap" in str(excinfo.value)

    def test_allows_a_challenge_within_the_cap(self, transport, minter):
        transport([challenged(credits="5"), paid_ok()])
        result = mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits="5"))
        assert result.paid is True

    @pytest.mark.parametrize(
        "value", ["abc", "2.5", "-1", -1, 1.5, True, " 5x"], ids=repr
    )
    def test_refuses_an_invalid_max_credits_at_entry(self, transport, minter, value):
        fake = transport([challenged()])
        with pytest.raises(PaymentsError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits=value))
        # Before the first request, not mid-flight on whatever 402 arrives.
        assert fake.count == 0

    def test_refuses_a_single_read_body_once_a_retry_is_required(
        self, transport, minter
    ):
        def body_stream():
            yield b"chunk"

        transport([challenged()])
        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(minter, "POST", DEFAULT_URL, options(), data=body_stream())
        assert minter.count == 0
        assert "cannot retry a single-read request body" in str(excinfo.value)

    def test_passes_a_single_read_body_through_when_never_challenged(
        self, transport, minter
    ):
        def body_stream():
            yield b"chunk"

        fake = transport([make_response(200, body=b'{"ok":1}')])
        result = mpp_fetch(minter, "POST", DEFAULT_URL, options(), data=body_stream())
        assert fake.count == 1
        assert result.response.status_code == 200
        assert result.paid is False


class TestAuthorizationHeaderHandling:
    def test_appends_the_credential_to_a_caller_supplied_authorization(
        self, transport, minter
    ):
        fake = transport([challenged(), paid_ok()])

        mpp_fetch(
            minter,
            "GET",
            DEFAULT_URL,
            options(),
            headers={"Authorization": "Bearer app-jwt"},
        )

        sent = fake.calls[1]["headers"]["Authorization"]
        assert sent.startswith("Payment ")
        assert sent.endswith(", Bearer app-jwt")

    def test_appends_regardless_of_the_callers_header_casing(self, transport, minter):
        fake = transport([challenged(), paid_ok()])

        mpp_fetch(
            minter,
            "GET",
            DEFAULT_URL,
            options(),
            headers={"authorization": "Bearer app-jwt"},
        )

        headers = fake.calls[1]["headers"]
        # Exactly one Authorization header goes out, and it carries both schemes.
        assert [k for k in headers if k.lower() == "authorization"] == ["Authorization"]
        assert headers["Authorization"].endswith(", Bearer app-jwt")


class TestEveryExitReportsWhatMayHaveBeenSpent:
    def test_carries_the_spend_accounting_on_the_terminal_rejection(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1", credits="7"),
                make_response(402, {}, json.dumps({"code": "BCK.MPP.0003"})),
            ]
        )

        with pytest.raises(MppError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        spend = mpp_spend_of(excinfo.value)
        assert spend is not None
        assert spend.credentials_presented == 1
        assert spend.credits_presented == "7"
        assert spend.challenge_id == "c1"

    def test_wraps_a_transport_failure_on_the_credential_bearing_retry(
        self, transport, minter
    ):
        transport([challenged(), requests.exceptions.ConnectionError("reset")])

        with pytest.raises(MppSpendOutcomeUnknownError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        # It must reach the documented `except MppError` handler.
        assert isinstance(excinfo.value, MppError)
        spend = mpp_spend_of(excinfo.value)
        assert spend.credentials_presented == 1
        assert "may or may not have been burned" in str(excinfo.value)

    def test_leaves_a_transport_failure_before_any_credential_untouched(
        self, transport, minter
    ):
        transport([requests.exceptions.ConnectionError("refused")])

        with pytest.raises(requests.exceptions.ConnectionError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert mpp_spend_of(excinfo.value) is None

    def test_carries_the_accounting_on_a_guard_raised_on_the_re_challenge_turn(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1", credits="3"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2", credits="99")},
                    b"",
                ),
            ]
        )

        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits="10"))

        spend = mpp_spend_of(excinfo.value)
        assert spend is not None
        assert spend.credentials_presented == 1
        assert spend.credits_presented == "3"

    def test_reports_no_spend_on_a_first_turn_plan_mismatch(self, transport, minter):
        transport([challenged()])
        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options(plan_id="other"))
        assert mpp_spend_of(excinfo.value) is None

    def test_reports_no_spend_on_a_first_turn_cap_refusal(self, transport, minter):
        transport([challenged(credits="10")])
        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits="1"))
        assert mpp_spend_of(excinfo.value) is None

    def test_reports_no_spend_when_the_mint_itself_fails(self, transport):
        failing = FakeMinter(error=PaymentsError.validation("mint refused"))
        transport([challenged()])

        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(failing, "GET", DEFAULT_URL, options())

        # Nothing reached the seller: the credential was never built.
        assert mpp_spend_of(excinfo.value) is None

    def test_still_reports_the_spend_when_the_error_cannot_carry_the_field(
        self, transport, minter
    ):
        # An error that refuses the annotation would otherwise recreate exactly
        # the invisible-spend failure the boundary exists to close, so it is
        # wrapped in one that holds the report in its own field.
        class UnannotatableError(MppError):
            _sealed = False

            def __init__(self, message):
                super().__init__(message)
                self._sealed = True

            def __setattr__(self, name, value):
                if name == "spend" and getattr(self, "_sealed", False):
                    raise AttributeError("frozen")
                super().__setattr__(name, value)

        transport([challenged(), UnannotatableError("cannot carry a report")])

        with pytest.raises(MppSpendOutcomeUnknownError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options())

        spend = mpp_spend_of(excinfo.value)
        assert spend is not None
        assert spend.credentials_presented == 1
        assert spend.credits_presented == "2"

    def test_returns_the_402_when_a_retryable_code_carries_no_challenge(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1"),
                make_response(402, {}, json.dumps({"code": "BCK.MPP.0004"})),
            ]
        )

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        # Retryable, but there is nothing to mint against on the next turn — so
        # the 402 comes back rather than raising, with the spend visible.
        assert result.response.status_code == 402
        assert result.paid is False
        assert result.credentials_presented == 1
        assert result.credits_presented == "2"


class TestMaxCreditsIsABudgetForTheCall:
    def test_refuses_the_second_turn_when_the_two_challenges_together_exceed(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1", credits="6"),
                make_response(
                    402, {"www-authenticate": challenge_header("c2", credits="6")}
                ),
            ]
        )

        with pytest.raises(PaymentsError) as excinfo:
            mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits="10"))

        assert minter.count == 1
        assert "already presented on 1 credential(s)" in str(excinfo.value)

    def test_allows_both_turns_when_the_total_fits_and_reports_the_sum(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1", credits="4"),
                make_response(
                    402, {"www-authenticate": challenge_header("c2", credits="4")}
                ),
                paid_ok(),
            ]
        )

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options(max_credits="10"))

        assert minter.count == 2
        assert result.paid is True
        assert result.credits_presented == "8"


class TestHostile402Bodies:
    def test_a_code_null_body_is_codeless_so_a_fresh_challenge_is_retried(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2")},
                    json.dumps({"code": None, "message": "try again"}),
                ),
                paid_ok(),
            ]
        )

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert minter.count == 2
        assert result.paid is True

    def test_stops_reading_a_402_body_at_the_cap_landing_on_the_terminal_path(
        self, transport, minter
    ):
        # A body far past the cap truncates mid-JSON, which does not parse — so
        # it is treated as unreadable, i.e. terminal, not as a fresh challenge.
        huge = b'{"message":"' + b"x" * (MAX_ERROR_BODY_BYTES * 2) + b'"}'
        transport(
            [
                challenged("c1"),
                make_response(402, {"www-authenticate": challenge_header("c2")}, huge),
            ]
        )

        with pytest.raises(MppError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 1

    def test_retries_a_fresh_challenge_whose_402_carries_no_body_at_all(
        self, transport, minter
    ):
        # An empty body is an ordinary HTTP shape, not a WAF page: it carries no
        # code, so freshness decides and the fresh id is retried.
        transport(
            [
                challenged("c1"),
                make_response(402, {"www-authenticate": challenge_header("c2")}, b""),
                paid_ok(),
            ]
        )

        result = mpp_fetch(minter, "GET", DEFAULT_URL, options())

        assert minter.count == 2
        assert result.paid is True

    def test_keeps_a_terminal_code_terminal_when_padding_sits_outside_the_json(
        self, transport, minter
    ):
        transport(
            [
                challenged("c1"),
                make_response(
                    402,
                    {"www-authenticate": challenge_header("c2")},
                    b"   " + json.dumps({"code": "BCK.MPP.0003"}).encode() + b"   ",
                ),
            ]
        )

        with pytest.raises(MppCredentialRejectedError):
            mpp_fetch(minter, "GET", DEFAULT_URL, options())
        assert minter.count == 1
