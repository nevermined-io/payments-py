"""Unit tests for v3 access tokens — single-use, seller/resource-bound.

Covers the client half of nvm-monorepo#2646: sending ``resource`` /
``httpVerb`` / ``tokenVersion`` at mint, detecting the version from the token
that came BACK, and surfacing ``BCK.X402.0059`` as its own actionable error.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

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
    MppTokenOptions,
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
                token_version=3,
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
    @pytest.mark.parametrize("shape", [str, X402Resource])
    @patch("payments_py.x402.token.requests.post")
    def test_blank_resource_url_raises_before_any_http_call(
        self, mock_post, mock_options, blank_url, shape
    ):
        """A blank signed URL is indistinguishable from 'absent' and only
        surfaces later as a forgery rejection at settle — fail fast instead,
        mirroring the blank delegation_id guard."""
        api = X402TokenAPI(mock_options)

        with pytest.raises(PaymentsError) as excinfo:
            api.get_x402_access_token(
                "plan-1",
                token_options=X402TokenOptions(
                    resource=(
                        blank_url if shape is str else X402Resource(url=blank_url)
                    ),
                    token_version=3,
                ),
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
    def test_unrequested_v3_token_is_reported_as_v3(self, mock_post, mock_options):
        """The mirror case, and the one that goes live the day the backend
        flips its default (nvm-monorepo#3259): ask for nothing, get v3.

        Without it, an implementation that echoes the request instead of
        reading the token — ``tokenVersion = 3 if requested else 2`` — passes
        the whole suite, and every caller branching on this key would then
        cache and replay a spent token."""
        _mock_mint(mock_post, V3_TOKEN)

        result = X402TokenAPI(mock_options).get_x402_access_token("plan-1")

        assert "tokenVersion" not in _sent_body(mock_post)
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


class TestMppHasNoTokenVersion:
    """MPP carries no token version at all (nvm-monorepo#3266).

    The two protocols stopped sharing a version ladder because their single-use
    unit differs: for x402 it is the TOKEN (the v3 one-time nonce), for MPP it
    is the CHALLENGE, whose id doubles as the burn idempotency key. One MPP
    access token is presented across many challenges by design, so a per-token
    nonce would kill every buyer's second challenge. The backend refuses ANY
    ``tokenVersion`` on an MPP mint with ``BCK.MPP.0007`` — ``2`` included,
    since that ordinal belongs to x402's ladder.
    """

    @pytest.mark.parametrize("version", [2, 3])
    @patch("payments_py.mpp.mpp_api.requests.post")
    def test_mpp_mint_refuses_any_token_version(self, mock_post, mock_options, version):
        """Refused client-side, before the request: the caller would otherwise
        meet a 400 whose cause is a field they set two layers up."""
        from payments_py.mpp.mpp_api import MppAPI

        with pytest.raises(PaymentsError) as excinfo:
            MppAPI(mock_options).get_mpp_access_token(
                "plan-1",
                "agent-1",
                token_options=X402TokenOptions(token_version=version),
            )

        assert excinfo.value.code == "validation"
        assert "BCK.MPP.0007" in str(excinfo.value)
        mock_post.assert_not_called()

    @patch("payments_py.x402.token.requests.post")
    def test_x402_mint_still_accepts_token_version(self, mock_post, mock_options):
        """The guard is scoped to the MPP mint — x402 keeps its ladder."""
        _mock_mint(mock_post, V3_TOKEN)

        X402TokenAPI(mock_options).get_x402_access_token(
            "plan-1", token_options=X402TokenOptions(token_version=3)
        )

        assert _sent_body(mock_post)["tokenVersion"] == 3

    @patch("payments_py.mpp.mpp_api.requests.post")
    def test_mpp_mint_reports_no_token_version(self, mock_post, mock_options):
        """There is no version to report, so the key must be absent rather than
        defaulted to 2 — MPP is not "x402 v2 by another name"."""
        from payments_py.mpp.mpp_api import MppAPI

        _mock_mint(mock_post, V2_TOKEN)
        mock_post.return_value.ok = True
        mock_post.return_value.status_code = 200

        result = MppAPI(mock_options).get_mpp_access_token("plan-1", "agent-1")

        assert "tokenVersion" not in result
        assert "tokenVersion" not in _sent_body(mock_post)

    @patch("payments_py.mpp.mpp_api.requests.post")
    def test_mpp_mint_refuses_the_v3_binding(self, mock_post, mock_options):
        """resource / http_verb are refused too, not just the version.

        An MPP token's struct has no members for them, so they bind nothing —
        but redemption runs through the shared erc4337 ``verify``, where the
        presence of the token's ``resource.url`` is what arms
        ``enforceEndpointAllowlist``. Sending them would switch on a check the
        caller never configured while adding no binding at all."""
        from payments_py.mpp.mpp_api import MppAPI

        with pytest.raises(PaymentsError) as excinfo:
            MppAPI(mock_options).get_mpp_access_token(
                "plan-1",
                "agent-1",
                token_options=X402TokenOptions(
                    resource="https://seller.example/ask",
                    http_verb="POST",
                    token_version=3,
                ),
            )

        assert excinfo.value.code == "validation"
        mock_post.assert_not_called()

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"token_version": 3},
            {"token_version": 2},
            {"resource": "https://seller.example/ask"},
            {"http_verb": "POST"},
        ],
    )
    def test_mpp_token_options_refuses_the_binding_at_construction(self, kwargs):
        """The type is the first line of defence, and it must REFUSE rather
        than silently drop: pydantic's default ``extra='ignore'`` would discard
        the value at construction and mint something the caller did not ask
        for, with no error anywhere."""
        with pytest.raises(ValidationError):
            MppTokenOptions(**kwargs)

    def test_x402_token_options_stays_assignable_to_mpp_token_options(self):
        """The compatibility trade this PR makes deliberately: an existing
        caller passing X402TokenOptions to the MPP mint still type-checks, so
        the runtime guard in the request builder is what actually enforces the
        split."""
        assert issubclass(X402TokenOptions, MppTokenOptions)
        for field in ("token_version", "resource", "http_verb"):
            assert field not in MppTokenOptions.model_fields
            assert field in X402TokenOptions.model_fields


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
        # The literal, not the constant: building the mock from
        # X402_TOKEN_ALREADY_USED_CODE would pass under any renumbering and so
        # could never detect drift from the backend catalogue.
        error = x402_error_from_response(
            self._response("BCK.X402.0059"), "Permission settlement failed"
        )

        assert isinstance(error, AccessTokenAlreadyUsedError)
        assert error.code == "BCK.X402.0059"
        assert X402_TOKEN_ALREADY_USED_CODE == "BCK.X402.0059"
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


class TestV3BindingRequiresV3:
    """resource / http_verb only mean something on a v3 token."""

    @pytest.mark.parametrize(
        "binding",
        [
            {"resource": "https://seller.example/api/v1/tasks"},
            {"http_verb": "POST"},
            {"resource": "https://seller.example/api/v1/tasks", "http_verb": "POST"},
        ],
    )
    @pytest.mark.parametrize("token_version", [None, 2])
    @patch("payments_py.x402.token.requests.post")
    def test_binding_without_v3_is_refused(
        self, mock_post, mock_options, binding, token_version
    ):
        """Neither dropped nor forwarded. Dropping would mint an unbound token
        while the caller believes it is bound; forwarding arms the backend's
        endpoint allowlist on a token that binds nothing, which for an agent
        registered with `endpoints` fails as BCK.PROTOCOL.0031."""
        api = X402TokenAPI(mock_options)

        with pytest.raises(PaymentsError) as excinfo:
            api.get_x402_access_token(
                "plan-1",
                token_options=X402TokenOptions(token_version=token_version, **binding),
            )

        assert excinfo.value.code == "validation"
        assert "token_version=3" in str(excinfo.value)
        mock_post.assert_not_called()

    @patch("payments_py.x402.token.requests.post")
    def test_v2_mint_stays_byte_identical_without_binding(
        self, mock_post, mock_options
    ):
        """The v2 body must be what it was before v3 existed."""
        _mock_mint(mock_post, V2_TOKEN)

        X402TokenAPI(mock_options).get_x402_access_token("plan-1", "agent-1")

        assert _sent_body(mock_post) == {
            "accepted": {
                "scheme": "nvm:erc4337",
                "network": "eip155:84532",
                "planId": "plan-1",
                "extra": {"agentId": "agent-1"},
            }
        }


class TestHttpVerbNormalisation:
    """http_verb is signed on v3 and compared at settle against a
    framework-supplied `request.method`, which is upper case everywhere."""

    @pytest.mark.parametrize("verb", ["post", "  post  ", "PosT"])
    @patch("payments_py.x402.token.requests.post")
    def test_verb_is_stripped_and_upper_cased(self, mock_post, mock_options, verb):
        _mock_mint(mock_post, V3_TOKEN)

        X402TokenAPI(mock_options).get_x402_access_token(
            "plan-1",
            token_options=X402TokenOptions(
                resource="https://seller.example/api/v1/tasks",
                http_verb=verb,
                token_version=3,
            ),
        )

        assert _sent_body(mock_post)["accepted"]["extra"]["httpVerb"] == "POST"

    @pytest.mark.parametrize("blank", ["", "   "])
    @patch("payments_py.x402.token.requests.post")
    def test_blank_verb_raises_before_any_http_call(
        self, mock_post, mock_options, blank
    ):
        """Same rationale as the blank-URL guard: a blank signed member is
        indistinguishable from an absent one and surfaces only at settle."""
        with pytest.raises(PaymentsError) as excinfo:
            X402TokenAPI(mock_options).get_x402_access_token(
                "plan-1",
                token_options=X402TokenOptions(http_verb=blank, token_version=3),
            )

        assert excinfo.value.code == "validation"
        assert "http_verb" in str(excinfo.value)
        mock_post.assert_not_called()


class TestTokenVersionIsARestrictedLiteral:
    """X402TokenVersion mirrors the backend DTO's @IsIn([2, 3])."""

    @pytest.mark.parametrize("bad", [0, 1, 4, 30, -1])
    def test_out_of_range_version_is_refused_at_construction(self, bad):
        with pytest.raises(ValidationError):
            X402TokenOptions(token_version=bad)

    @pytest.mark.parametrize("good", [2, 3])
    def test_supported_versions_construct(self, good):
        assert X402TokenOptions(token_version=good).token_version == good
