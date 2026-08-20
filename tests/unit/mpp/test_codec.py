"""
Wire-format tests for the MPP codec.

Port of ``tests/unit/mpp/codec.test.ts`` in ``nevermined-io/payments`` (#417).
The fixtures are shared from :mod:`tests.unit.mpp.fixtures` — see that module
for why they stand in for an ``mppx`` dependency.
"""

import base64
import json

import pytest

from payments_py.mpp.codec import (
    build_credential_header,
    extract_credential_challenge_id,
    extract_payment_scheme,
    parse_challenge_header,
    parse_receipt_header,
)
from payments_py.mpp.errors import MppError
from payments_py.mpp.types import MppChallengeRequest, MppReceipt

from .fixtures import (
    CHALLENGE_HEADER,
    CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION,
    CHALLENGE_ID,
    OPAQUE_ENCODED,
    RECEIPT_HEADER,
    REQUEST_ENCODED,
    b64url,
    b64url_json,
    build_challenge_params,
    build_challenge_with_request,
    decode_credential,
)


class TestParseChallengeHeader:
    def test_parses_every_auth_param_and_decodes_the_sealed_request(self):
        challenge = parse_challenge_header(CHALLENGE_HEADER)
        assert challenge is not None
        assert challenge.id == CHALLENGE_ID
        assert challenge.realm == "api.nevermined.app"
        assert challenge.method == "nevermined"
        assert challenge.intent == "charge"
        assert challenge.expires == "2026-08-12T10:05:00.000Z"
        assert challenge.request == MppChallengeRequest(
            plan_id=(
                "44742763076047497640080230236781474129970992727896593861997347"
                "13561313557107"
            ),
            credits="2",
        )

    def test_keeps_request_and_opaque_as_the_exact_base64url_strings_received(self):
        challenge = parse_challenge_header(CHALLENGE_HEADER)
        assert challenge.request_encoded == REQUEST_ENCODED
        assert challenge.opaque == OPAQUE_ENCODED

    def test_returns_none_when_the_header_carries_no_payment_scheme(self):
        assert parse_challenge_header("Bearer abc") is None

    def test_picks_the_payment_scheme_out_of_a_merged_header(self):
        assert parse_challenge_header(f"Bearer abc, {CHALLENGE_HEADER}") is not None

    def test_decodes_every_param_when_a_comma_sits_inside_a_quoted_description(self):
        # The comma inside "Standard, non-refundable request" must not truncate
        # the scheme, and ``opaque`` — ordered AFTER the comma-bearing
        # ``description`` — must still be decoded, or the HMAC re-derivation at
        # the backend fails and the credential is rejected.
        challenge = parse_challenge_header(CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION)
        assert challenge is not None
        assert challenge.description == "Standard, non-refundable request"
        assert challenge.opaque == OPAQUE_ENCODED
        assert challenge.id == CHALLENGE_ID
        assert challenge.realm == "api.nevermined.app"
        assert challenge.method == "nevermined"
        assert challenge.intent == "charge"
        assert challenge.request_encoded == REQUEST_ENCODED


class TestBuildCredentialHeader:
    def test_round_trips_through_the_wire_with_request_and_opaque_intact(self):
        challenge = parse_challenge_header(CHALLENGE_HEADER)
        header = build_credential_header(challenge, {"accessToken": "BASE64_MPP_TOKEN"})

        assert header.startswith("Payment ")
        decoded = decode_credential(header)
        assert decoded["challenge"]["request"] == REQUEST_ENCODED
        assert decoded["challenge"]["opaque"] == OPAQUE_ENCODED
        assert decoded["challenge"]["id"] == CHALLENGE_ID
        assert decoded["challenge"]["expires"] == "2026-08-12T10:05:00.000Z"
        assert decoded["payload"] == {"accessToken": "BASE64_MPP_TOKEN"}
        assert "meta" not in decoded["challenge"]

    def test_emits_base64url_without_padding(self):
        challenge = parse_challenge_header(CHALLENGE_HEADER)
        encoded = build_credential_header(challenge, {"accessToken": "x"})[
            len("Payment ") :
        ]
        assert not any(ch in encoded for ch in "+/=")

    def test_decodes_to_the_same_fields_as_the_mppx_modelled_credential(self):
        # This does not assert byte-equality with mppx's own output — the two
        # ``Payment …`` values differ (mppx orders challenge keys expires, id,
        # intent, method, realm, opaque, request; build_credential_header
        # orders id, realm, method, intent, expires, …, opaque, request), and
        # that is fine: key order is irrelevant because the server parses the
        # JSON. Comparing parsed objects is the right assertion for that claim.
        # The property that WOULD break settlement — a silent re-encode of
        # request/opaque — is pinned byte-exactly elsewhere in this file.
        mppx_credential = (
            "Payment eyJjaGFsbGVuZ2UiOnsiZXhwaXJlcyI6IjIwMjYtMDgtMTJUMTA6MDU6MDAu"
            "MDAwWiIsImlkIjoiQ1Fzek9uZ2Z2VDFSSUdTYWppcFpKdmctbEJDRUR1Z1dMREY3U0Rf"
            "dzFvZyIsImludGVudCI6ImNoYXJnZSIsIm1ldGhvZCI6Im5ldmVybWluZWQiLCJyZWFs"
            "bSI6ImFwaS5uZXZlcm1pbmVkLmFwcCIsIm9wYXF1ZSI6ImV5SmZiWEJ3ZUY5elkyOXda"
            "U0k2SWxCUFUxUWdMMkZ6YXlJc0ltNXZibU5sSWpvaU1URXhNVEV4TVRFdE1qSXlNaTB6"
            "TXpNekxUUTBORFF0TlRVMU5UVTFOVFUxTlRVMUluMCIsInJlcXVlc3QiOiJleUpqY21W"
            "a2FYUnpJam9pTWlJc0luQnNZVzVKWkNJNklqUTBOelF5TnpZek1EYzJNRFEzTkRrM05q"
            "UXdNRGd3TWpNd01qTTJOemd4TkRjME1USTVPVGN3T1RreU56STNPRGsyTlRrek9EWXhP"
            "VGszTXpRM01UTTFOakV6TVRNMU5UY3hNRGNpZlEifSwicGF5bG9hZCI6eyJhY2Nlc3NU"
            "b2tlbiI6IkJBU0U2NF9NUFBfVE9LRU4ifX0"
        )
        challenge = parse_challenge_header(CHALLENGE_HEADER)
        ours = decode_credential(
            build_credential_header(challenge, {"accessToken": "BASE64_MPP_TOKEN"})
        )
        assert ours == decode_credential(mppx_credential)


class TestParseReceiptHeader:
    def test_decodes_the_receipt(self):
        assert parse_receipt_header(RECEIPT_HEADER) == MppReceipt(
            method="nevermined",
            reference=CHALLENGE_ID,
            status="success",
            timestamp="2026-08-12T10:00:30.000Z",
        )


class TestExtractPaymentScheme:
    def test_finds_the_payment_scheme_among_several(self):
        assert extract_payment_scheme("Bearer xyz, Payment abc") == "Payment abc"

    def test_returns_none_when_absent(self):
        assert extract_payment_scheme("Bearer xyz") is None

    def test_stops_at_a_trailing_scheme_when_payment_is_a_bare_credential_token(self):
        # A credential is a token68 (no internal structure), so it can never
        # legitimately contain a comma. A following ", Bearer some-app-jwt"
        # must not be folded into the extracted scheme.
        assert extract_payment_scheme("Payment abc, Bearer xyz") == "Payment abc"

    def test_does_not_corrupt_the_credential_when_an_app_jwt_rides_alongside(self):
        assert (
            extract_payment_scheme("Payment eyJhYmMifQ, Bearer some-app-jwt")
            == "Payment eyJhYmMifQ"
        )

    @pytest.mark.parametrize("header", ["XPayment abc", "NotPayment abc"])
    def test_does_not_match_payment_mid_token(self, header):
        # An unanchored ``Payment\s+`` used to match inside a longer token.
        assert extract_payment_scheme(header) is None

    def test_does_not_divert_an_unrelated_authorization_value_onto_the_mpp_path(self):
        # The live regression: this feeds the MPP-vs-x402 routing predicate, so
        # an x402 buyer whose Authorization happens to contain "payment"
        # followed by whitespace — with no comma boundary in front of it — must
        # not be read as presenting an MPP credential.
        assert extract_payment_scheme("Bearer prepayment xyz") is None

    def test_ignores_payment_text_inside_a_preceding_schemes_quoted_value(self):
        assert (
            extract_payment_scheme('Digest username="my payment plan", Payment abc')
            == "Payment abc"
        )

    def test_does_not_truncate_a_structured_challenge_at_a_quoted_comma(self):
        assert (
            extract_payment_scheme(CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION)
            == CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION
        )

    def test_still_stops_at_a_genuine_trailing_scheme_after_a_quoted_comma(self):
        assert (
            extract_payment_scheme(
                f"{CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION}, Bearer some-app-jwt"
            )
            == CHALLENGE_HEADER_WITH_COMMA_DESCRIPTION
        )

    def test_is_not_confused_by_the_literal_text_payment_inside_a_quoted_value(self):
        header = (
            'Payment id="c1", realm="api.nevermined.app", method="nevermined", '
            'intent="charge", request="req", '
            'description="Ask about the Payment plan, then retry", opaque="op"'
        )
        assert extract_payment_scheme(header) == header
        assert extract_payment_scheme(f"{header}, Bearer some-app-jwt") == header


class TestEscapedQuotedStringValues:
    """Escaped quoted-string values, as mppx actually serializes them."""

    def test_does_not_swallow_a_trailing_scheme_on_an_odd_number_of_quotes(self):
        # '5" screen replacement plan' has one literal quote (odd count). mppx
        # serializes it as description="5\" screen replacement plan" — a
        # quote-only (not escape-aware) scanner flips its in-quotes state an odd
        # number of times on the escaped quote and never recovers, swallowing
        # everything after it, including a genuinely different trailing scheme.
        description = '5" screen replacement plan'
        header = f"Payment {build_challenge_params(description)}"

        assert extract_payment_scheme(f"{header}, Bearer some-app-jwt") == header

        challenge = parse_challenge_header(header)
        assert challenge is not None
        assert challenge.description == description
        assert challenge.opaque == OPAQUE_ENCODED
        assert challenge.id == CHALLENGE_ID
        assert challenge.request_encoded == REQUEST_ENCODED

    def test_decodes_the_full_unescaped_value_on_an_even_number_of_quotes(self):
        description = 'Access to the "Pro" tier'
        header = f"Payment {build_challenge_params(description)}"
        assert parse_challenge_header(header).description == description

    def test_decodes_a_value_containing_a_literal_backslash(self):
        description = "back\\slash"
        header = f"Payment {build_challenge_params(description)}"
        assert parse_challenge_header(header).description == description

    def test_keeps_request_and_opaque_verbatim_alongside_an_escaped_description(self):
        description = 'Contains "quotes" and a back\\slash, and a comma'
        header = f"Payment {build_challenge_params(description)}"
        challenge = parse_challenge_header(header)
        assert challenge.request_encoded == REQUEST_ENCODED
        assert challenge.opaque == OPAQUE_ENCODED

    def test_returns_the_whole_remainder_for_an_unterminated_quote(self):
        header = (
            f'Payment id="{CHALLENGE_ID}", realm="api.nevermined.app", '
            'method="nevermined", intent="charge", '
            f'request="{REQUEST_ENCODED}", description="unterminated'
        )
        assert extract_payment_scheme(header) == header


class TestParseChallengeHeaderMalformedRequestParam:
    def test_raises_a_typed_mpp_error_when_request_is_not_valid_base64url_json(self):
        # Lenient base64url decoding silently drops invalid characters, so
        # garbage reaches the JSON parser and used to escape as a bare decoding
        # error mentioning neither MPP nor payment.
        with pytest.raises(MppError):
            parse_challenge_header(build_challenge_with_request("zzz"))

    @pytest.mark.parametrize(
        "value",
        [None, ["a"], {"credits": "2"}, {"planId": 42, "credits": "2"}],
        ids=["null", "array", "missing-planId", "non-string-planId"],
    )
    def test_rejects_an_unusable_request(self, value):
        with pytest.raises(MppError):
            parse_challenge_header(build_challenge_with_request(b64url_json(value)))

    def test_rejects_an_empty_string_plan_id(self):
        with pytest.raises(MppError):
            parse_challenge_header(
                build_challenge_with_request(
                    b64url_json({"planId": "", "credits": "2"})
                )
            )

    def test_coerces_a_json_number_credits_rather_than_rejecting_the_seller(self):
        # credits is not what anything spends: the amount the backend re-derives
        # comes from request_encoded, forwarded byte-verbatim. A third-party
        # seller encoding credits as a JSON number is a perfectly reasonable
        # reading of "credits" and must not become wholly unpayable over a field
        # this SDK does not itself act on.
        challenge = parse_challenge_header(
            build_challenge_with_request(b64url_json({"planId": "123", "credits": 2}))
        )
        assert challenge.request == MppChallengeRequest(plan_id="123", credits="2")

    def test_rejects_a_request_whose_agent_id_is_not_a_string(self):
        # Unlike credits, agentId IS load-bearing: the buyer helper forwards
        # challenge.request.agent_id straight into the token mint, so a
        # malformed value here reaches the spend path.
        with pytest.raises(MppError):
            parse_challenge_header(
                build_challenge_with_request(
                    b64url_json({"planId": "123", "credits": "2", "agentId": 42})
                )
            )

    def test_accepts_a_well_formed_agent_id_and_passes_it_through(self):
        challenge = parse_challenge_header(
            build_challenge_with_request(
                b64url_json({"planId": "123", "credits": "2", "agentId": "agent-1"})
            )
        )
        assert challenge.request == MppChallengeRequest(
            plan_id="123", credits="2", agent_id="agent-1"
        )

    def test_a_header_with_no_payment_scheme_still_returns_none(self):
        # Structurally absent stays None — that is how a caller tells "not an
        # MPP endpoint" from "malformed". Only a PRESENT-but-undecodable
        # challenge raises.
        assert parse_challenge_header("Bearer abc") is None

    def test_still_parses_a_well_formed_request(self):
        challenge = parse_challenge_header(
            build_challenge_with_request(b64url_json({"planId": "123", "credits": "2"}))
        )
        assert challenge.request == MppChallengeRequest(plan_id="123", credits="2")


class TestParseReceiptHeaderMalformedInput:
    def test_raises_a_typed_mpp_error_on_undecodable_base64url_json(self):
        with pytest.raises(MppError):
            parse_receipt_header("zzz")

    @pytest.mark.parametrize(
        "value",
        [
            None,
            ["a"],
            {"method": "nevermined"},
            {
                "method": "nevermined",
                "reference": "c1",
                "status": "success",
                "timestamp": 42,
            },
        ],
        ids=["null", "array", "missing-field", "wrong-typed-field"],
    )
    def test_raises_a_typed_mpp_error_on_an_unusable_receipt(self, value):
        # A malformed Payment-Receipt arrives on a successful, already-paid 200.
        # Returning it untyped used to let a caller's field access crash later
        # with nothing pointing back at the header that caused it.
        with pytest.raises(MppError):
            parse_receipt_header(b64url(json.dumps(value).encode("utf-8")))

    def test_still_decodes_a_well_formed_receipt(self):
        assert parse_receipt_header(RECEIPT_HEADER) == MppReceipt(
            method="nevermined",
            reference=CHALLENGE_ID,
            status="success",
            timestamp="2026-08-12T10:00:30.000Z",
        )


class TestExtractCredentialChallengeId:
    CHALLENGE = {
        "id": CHALLENGE_ID,
        "realm": "api.nevermined.app",
        "method": "nevermined",
        "intent": "charge",
        "request": "eyJjcmVkaXRzIjoiMiIsInBsYW5JZCI6IjEyMyJ9",
    }

    @property
    def credential(self) -> str:
        return "Payment " + b64url(
            json.dumps(
                {"challenge": self.CHALLENGE, "payload": {"accessToken": "x"}}
            ).encode("utf-8")
        )

    def test_reads_the_challenge_id_out_of_a_credential_this_sdk_built(self):
        assert extract_credential_challenge_id(self.credential) == CHALLENGE_ID

    def test_returns_the_same_id_for_byte_variants_the_backend_collapses(self):
        # This is the whole point: the header bytes are not the credential's
        # identity. The scheme match is case-insensitive and returns its slice
        # verbatim, so these strings differ while naming one credential — and
        # the backend's idempotency key is this id, so all of them settle onto a
        # single burn. A guard keyed on the bytes is walked around by flipping
        # one byte of case.
        credential = self.credential
        lowercased = "payment" + credential[len("Payment") :]
        respaced = "Payment  " + credential[len("Payment ") :]
        assert lowercased != credential
        assert respaced != credential
        assert extract_credential_challenge_id(lowercased) == CHALLENGE_ID
        assert extract_credential_challenge_id(respaced) == CHALLENGE_ID

    def test_is_insensitive_to_the_buyer_re_ordering_the_json_keys(self):
        # The body is base64url of JSON the BUYER assembles, so key order is
        # theirs to choose and yields yet more distinct byte-strings.
        reordered = "Payment " + b64url(
            json.dumps(
                {
                    "payload": {"accessToken": "x"},
                    "challenge": {
                        "intent": "charge",
                        "id": CHALLENGE_ID,
                        "realm": "api.nevermined.app",
                    },
                }
            ).encode("utf-8")
        )
        assert reordered != self.credential
        assert extract_credential_challenge_id(reordered) == CHALLENGE_ID

    def test_reads_the_id_out_of_a_PADDED_credential(self):
        # RFC 7235 lets a token68 carry trailing '=', and base64url padding is
        # '='. Since an auth-param key also ends in '=', a padded credential
        # matched the structured-challenge test and was refused forever — while
        # the backend would have decoded it fine, which is the whole
        # justification for refusing without a round-trip. First-party buyers
        # never hit it because build_credential_header emits unpadded.
        # Grow one field until the encoding actually pads — base64 only emits
        # '=' when the payload length is not a multiple of 3, so a fixed
        # fixture would silently stop exercising the bug.
        for filler in range(1, 4):
            wire = json.dumps(
                {
                    "challenge": {
                        "id": CHALLENGE_ID,
                        "realm": "r" * filler,
                        "method": "nevermined",
                        "intent": "charge",
                        "request": "x",
                    },
                    "payload": {"accessToken": "T"},
                },
                separators=(",", ":"),
            ).encode("utf-8")
            padded = base64.urlsafe_b64encode(wire).decode("ascii")
            if padded.endswith("="):
                break
        assert padded.endswith("=")

        assert extract_credential_challenge_id(f"Payment {padded}") == CHALLENGE_ID
        assert (
            extract_credential_challenge_id(f"Payment {padded.rstrip('=')}")
            == CHALLENGE_ID
        )

    def test_a_padded_credential_still_stops_at_a_trailing_scheme(self):
        padded = base64.urlsafe_b64encode(b'{"challenge":{"id":"c1"}}').decode("ascii")
        assert extract_payment_scheme(f"Payment {padded}, Bearer jwt") == (
            f"Payment {padded}"
        )

    @pytest.mark.parametrize(
        "credential",
        [
            "Payment !!!not-base64url!!!",
            "Payment " + b64url(b"[]"),
            "Payment " + b64url(b'{"other":true}'),
            "Payment " + b64url(b'{"challenge":{}}'),
            "Payment " + b64url(b'{"challenge":{"id":""}}'),
            'Payment id="c1", realm="r"',
            "",
        ],
        ids=[
            "undecodable-base64url-json",
            "json-that-is-not-an-object",
            "object-with-no-challenge",
            "challenge-with-no-id",
            "challenge-id-not-a-non-empty-string",
            "structured-challenge-never-a-credential",
            "no-payment-scheme-at-all",
        ],
    )
    def test_returns_none_for_an_undecodable_credential(self, credential):
        assert extract_credential_challenge_id(credential) is None
