"""Unit tests for v3 access tokens — single-use, seller/resource-bound.

Covers the client half of nvm-monorepo#2646: sending ``resource`` /
``httpVerb`` / ``tokenVersion`` at mint, detecting the version from the token
that came BACK, and surfacing ``BCK.X402.0059`` as its own actionable error.
"""

import json
from unittest.mock import MagicMock, patch

import pytest

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.errors import (
    AccessTokenAlreadyUsedError,
    X402_TOKEN_ALREADY_USED_CODE,
    is_access_token_already_used,
    x402_error_from_response,
)
from payments_py.x402.facilitator_api import FacilitatorAPI
from payments_py.x402.helpers import build_payment_required
from payments_py.x402.token import (
    X402TokenAPI,
    X402_TOKEN_VERSION_V2,
    X402_TOKEN_VERSION_V3,
    encode_access_token,
    detect_access_token_version,
    is_single_use_access_token,
    with_detected_token_version,
)
from payments_py.x402.types import (
    DelegationConfig,
    X402Resource,
    X402TokenOptions,
)


@pytest.fixture
def mock_options():
    """Create mock PaymentOptions."""
    mock = MagicMock()
    mock.nvm_api_key = "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
    mock.environment = "sandbox"
    mock.return_url = ""
    mock.app_id = None
    mock.version = None
    return mock


def make_token(**authorization) -> str:
    """Encode a token whose ``payload.authorization`` carries the given fields."""
    return encode_access_token(
        {
            "x402Version": 2,
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "payload": {"authorization": authorization, "signature": "0xsig"},
        }
    )


V2_TOKEN = make_token(**{"from": "0xabc", "planId": "plan-1"})
V3_TOKEN = make_token(
    **{
        "from": "0xabc",
        "planId": "plan-1",
        "agentId": "agent-1",
        "resourceUrl": "https://seller.example/api/v1/tasks",
        "httpVerb": "POST",
        "nonce": "0x0123456789abcdef",
    }
)


def _mock_mint(mock_post, access_token: str) -> None:
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"accessToken": access_token}
    mock_post.return_value = response


def _sent_body(mock_post) -> dict:
    return json.loads(mock_post.call_args.kwargs.get("data", "{}"))


class TestVersionDetector:
    """The version must come from the token, never from what was requested."""

    def test_nonce_marks_v3(self):
        assert is_single_use_access_token(V3_TOKEN) is True
        assert detect_access_token_version(V3_TOKEN) == X402_TOKEN_VERSION_V3

    def test_no_nonce_is_v2(self):
        assert is_single_use_access_token(V2_TOKEN) is False
        assert detect_access_token_version(V2_TOKEN) == X402_TOKEN_VERSION_V2

    @pytest.mark.parametrize("nonce", ["", "   ", None, 0, 123, {"n": 1}])
    def test_blank_or_non_string_nonce_is_not_v3(self, nonce):
        """The backend signs an absent field as the empty string, so a blank
        nonce is 'no nonce'. A non-string is malformed and equally not a v3
        marker — neither may be read as replay protection that isn't there."""
        assert is_single_use_access_token(make_token(nonce=nonce)) is False

    @pytest.mark.parametrize(
        "token",
        [
            None,
            "",
            "not-valid-base64-json",
            encode_access_token({"payload": "not-a-dict"}),
            encode_access_token({"payload": {"authorization": "not-a-dict"}}),
            encode_access_token({"no": "payload"}),
        ],
    )
    def test_undecodable_or_malformed_token_falls_back_to_v2(self, token):
        """v2 is the safe default: it only ever makes a caller re-mint more
        often than needed, never fewer times than needed."""
        assert is_single_use_access_token(token) is False
        assert detect_access_token_version(token) == X402_TOKEN_VERSION_V2

    def test_with_detected_token_version_annotates(self):
        assert with_detected_token_version({"accessToken": V3_TOKEN}) == {
            "accessToken": V3_TOKEN,
            "tokenVersion": 3,
        }

    @pytest.mark.parametrize("response", [{}, {"accessToken": ""}, {"error": "nope"}])
    def test_with_detected_token_version_leaves_tokenless_response_alone(
        self, response
    ):
        """No token means no version to report — inventing one would be a lie."""
        assert "tokenVersion" not in with_detected_token_version(dict(response))


class TestMintRequestBody:
    """resource / httpVerb / tokenVersion must reach the wire."""

    @patch("payments_py.x402.token.requests.post")
    def test_v3_request_sends_resource_verb_and_version(self, mock_post, mock_options):
        _mock_mint(mock_post, V3_TOKEN)

        api = X402TokenAPI(mock_options)
        api.get_x402_access_token(
            "plan-1",
            "agent-1",
            token_options=X402TokenOptions(
                delegation_config=DelegationConfig(delegation_id="deleg-1"),
                resource="https://seller.example/api/v1/tasks",
                http_verb="POST",
                token_version=3,
            ),
        )

        body = _sent_body(mock_post)
        assert body["resource"] == {"url": "https://seller.example/api/v1/tasks"}
        assert body["accepted"]["extra"]["httpVerb"] == "POST"
        assert body["accepted"]["extra"]["agentId"] == "agent-1"
        assert body["tokenVersion"] == 3

    @patch("payments_py.x402.token.requests.post")
    def test_resource_model_carries_description_and_mime_type(
        self, mock_post, mock_options
    ):
        _mock_mint(mock_post, V3_TOKEN)

        api = X402TokenAPI(mock_options)
        api.get_x402_access_token(
            "plan-1",
            token_options=X402TokenOptions(
                resource=X402Resource(
                    url="https://seller.example/api/v1/tasks",
                    description="Task runner",
                    mime_type="application/json",
                ),
            ),
        )

        assert _sent_body(mock_post)["resource"] == {
            "url": "https://seller.example/api/v1/tasks",
            "description": "Task runner",
            "mimeType": "application/json",
        }

    @patch("payments_py.x402.token.requests.post")
    def test_omitted_fields_are_absent_not_blank(self, mock_post, mock_options):
        """A field absent at mint is signed as the empty string, and the
        unsigned envelope copy must then also be absent — so the SDK must not
        volunteer empty placeholders."""
        _mock_mint(mock_post, V2_TOKEN)

        api = X402TokenAPI(mock_options)
        api.get_x402_access_token("plan-1")

        body = _sent_body(mock_post)
        assert "resource" not in body
        assert "tokenVersion" not in body
        assert "httpVerb" not in body["accepted"]["extra"]

    @pytest.mark.parametrize("blank_url", ["", "   "])
    @patch("payments_py.x402.token.requests.post")
    def test_blank_resource_url_raises_before_any_http_call(
        self, mock_post, mock_options, blank_url
    ):
        """A blank signed URL is indistinguishable from 'absent' and only
        surfaces later as a forgery rejection at settle — fail fast instead,
        mirroring the blank delegation_id guard."""
        api = X402TokenAPI(mock_options)

        with pytest.raises(PaymentsError) as excinfo:
            api.get_x402_access_token(
                "plan-1", token_options=X402TokenOptions(resource=blank_url)
            )

        assert excinfo.value.code == "validation"
        assert "resource.url" in str(excinfo.value)
        mock_post.assert_not_called()


class TestMintResponseVersion:
    """The mint reports the version it GOT."""

    @patch("payments_py.x402.token.requests.post")
    def test_v3_token_reported_as_v3(self, mock_post, mock_options):
        _mock_mint(mock_post, V3_TOKEN)

        result = X402TokenAPI(mock_options).get_x402_access_token(
            "plan-1", token_options=X402TokenOptions(token_version=3)
        )

        assert result["tokenVersion"] == 3

    @patch("payments_py.x402.token.requests.post")
    def test_silently_stripped_token_version_is_reported_as_v2(
        self, mock_post, mock_options
    ):
        """The backend's ValidationPipe runs with whitelist:true and WITHOUT
        forbidNonWhitelisted, so a pre-#2646 deployment drops tokenVersion:3
        and mints v2 with no error. Asking for 3 must never be reported as
        getting 3."""
        _mock_mint(mock_post, V2_TOKEN)

        result = X402TokenAPI(mock_options).get_x402_access_token(
            "plan-1", token_options=X402TokenOptions(token_version=3)
        )

        assert _sent_body(mock_post)["tokenVersion"] == 3
        assert result["tokenVersion"] == 2


class TestMppMintReportsVersion:
    """The MPP mint shares the builder, so it reports its version the same way.

    MPP does NOT pin v3 (nvm-monorepo v1.30.0): one MPP token is reused across
    many challenges, so a one-time nonce would break the buyer's second
    challenge. The version is still detected and reported here — the point is
    that the two mints cannot drift, not that MPP is single-use.
    """

    @patch("payments_py.mpp.mpp_api.requests.post")
    def test_mpp_mint_annotates_token_version(self, mock_post, mock_options):
        from payments_py.mpp.mpp_api import MppAPI

        _mock_mint(mock_post, V3_TOKEN)
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200

        result = MppAPI(mock_options).get_mpp_access_token("plan-1", "agent-1")

        assert result["tokenVersion"] == 3

    @patch("payments_py.mpp.mpp_api.requests.post")
    def test_mpp_mint_sends_resource_and_verb(self, mock_post, mock_options):
        from payments_py.mpp.mpp_api import MppAPI

        _mock_mint(mock_post, V3_TOKEN)
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200

        MppAPI(mock_options).get_mpp_access_token(
            "plan-1",
            "agent-1",
            token_options=X402TokenOptions(
                resource="https://seller.example/ask", http_verb="POST"
            ),
        )

        body = _sent_body(mock_post)
        assert body["resource"] == {"url": "https://seller.example/ask"}
        assert body["accepted"]["extra"]["httpVerb"] == "POST"


class TestAlreadyUsedError:
    """BCK.X402.0059 is its own outcome: re-mint, do not retry."""

    def _response(self, code: str, status: int = 400):
        response = MagicMock()
        response.status_code = status
        response.json.return_value = {
            "code": code,
            "message": "access token already used",
        }
        return response

    def test_0059_becomes_access_token_already_used_error(self):
        error = x402_error_from_response(
            self._response(X402_TOKEN_ALREADY_USED_CODE), "Permission settlement failed"
        )

        assert isinstance(error, AccessTokenAlreadyUsedError)
        assert error.code == X402_TOKEN_ALREADY_USED_CODE
        assert is_access_token_already_used(error) is True
        assert "Mint a new access token" in str(error)
        # Still a PaymentsError, so existing handlers keep working.
        assert isinstance(error, PaymentsError)

    def test_other_codes_stay_generic(self):
        error = x402_error_from_response(
            self._response("BCK.X402.0005"), "Permission settlement failed"
        )

        assert not isinstance(error, AccessTokenAlreadyUsedError)
        assert error.code == "BCK.X402.0005"
        assert is_access_token_already_used(error) is False

    def test_is_access_token_already_used_reads_the_code_not_the_class(self):
        """The code is the wire-level discriminant, so it still answers
        correctly across a process boundary or a duplicated package install."""
        assert (
            is_access_token_already_used(
                PaymentsError("spent", X402_TOKEN_ALREADY_USED_CODE)
            )
            is True
        )
        assert is_access_token_already_used(None) is False
        assert is_access_token_already_used(ValueError("nope")) is False

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_second_settle_surfaces_the_typed_error(self, mock_post, mock_options):
        import requests

        response = self._response(X402_TOKEN_ALREADY_USED_CODE)
        response.raise_for_status.side_effect = requests.HTTPError("400")
        mock_post.return_value = response

        api = FacilitatorAPI(mock_options)
        payment_required = build_payment_required(
            plan_id="plan-1", agent_id="agent-1", network="eip155:84532"
        )

        with pytest.raises(AccessTokenAlreadyUsedError) as excinfo:
            api.settle_permissions(
                payment_required=payment_required, x402_access_token=V3_TOKEN
            )

        assert excinfo.value.code == X402_TOKEN_ALREADY_USED_CODE
