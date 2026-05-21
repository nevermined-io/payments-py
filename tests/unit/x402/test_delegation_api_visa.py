"""Unit tests for the Visa provider surface of the payments SDK.

Visa enrolment and Visa delegation creation both require a browser (VGS
Collect iframe + WebAuthn passkey ceremony), so the SDK is not expected
to perform either programmatically. These tests cover what the SDK is
actually responsible for:

  1. list_payment_methods() surfaces visa-provider cards unchanged.
  2. create_delegation() accepts provider='visa' and posts the payload
     verbatim — the backend handles all visa-specific orchestration.
  3. get_x402_access_token() generates a token against a visa
     delegation_id using the standard nvm:card-delegation scheme with
     network='visa'.
  4. verify_permissions() / settle_permissions() accept network='visa'.
  5. Backend error envelopes (NVMException code + hint) are preserved on
     PaymentsError so consumers can branch on e.g. ``BCK.VISA.0014``.
"""

from unittest.mock import patch, MagicMock

import pytest
import requests

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.delegation_api import DelegationAPI
from payments_py.x402.facilitator_api import FacilitatorAPI
from payments_py.x402.token import X402TokenAPI
from payments_py.x402.types import (
    CreateDelegationPayload,
    DelegationConfig,
    X402PaymentRequired,
    X402Resource,
    X402Scheme,
    X402TokenOptions,
)


@pytest.fixture
def mock_options():
    """Minimal PaymentOptions-shaped mock; the SDK only reads a few fields."""
    mock = MagicMock()
    mock.nvm_api_key = "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
    mock.environment = "sandbox"
    mock.return_url = ""
    mock.app_id = None
    mock.version = None
    return mock


def _http_error_response(
    status: int,
    body: dict | list | None = None,
    *,
    json_error: Exception | None = None,
) -> MagicMock:
    """Build a requests-like Response that raise_for_status() raises on.

    Pass ``json_error`` to simulate a non-JSON body (``.json()`` raises);
    otherwise the supplied ``body`` is returned from ``.json()``.
    """
    resp = MagicMock()
    resp.status_code = status
    if json_error is not None:
        resp.json.side_effect = json_error
    else:
        resp.json.return_value = body
    resp.raise_for_status.side_effect = requests.HTTPError(
        f"{status} Client Error", response=resp
    )
    return resp


class TestListPaymentMethodsVisa:
    @patch("payments_py.x402.delegation_api.requests.get")
    def test_handles_heterogeneous_list_including_erc4337_wallet(
        self, mock_get, mock_options
    ):
        """``/payment-methods`` deliberately returns a mixed list: enrolled
        cards plus the user's ERC-4337 smart account as a
        ``provider='erc4337'`` entry (see
        ``apps/api/src/delegation/delegation.service.ts::listPaymentMethods``).
        The SDK must surface all entries — filtering crypto wallets out
        of view would hide a real payment option from consumers."""
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "id": "vat_1abc",
                "type": "card",
                "brand": "visa",
                "last4": "1387",
                "expMonth": 12,
                "expYear": 2027,
                "provider": "visa",
            },
            {
                "id": "0xabc1234567890123456789012345678901231234",
                "type": "crypto_wallet",
                "brand": "ethereum",
                "last4": "1234",
                "expMonth": None,
                "expYear": None,
                "alias": "Crypto Wallet",
                "provider": "erc4337",
            },
        ]
        mock_get.return_value = mock_response

        methods = DelegationAPI(mock_options).list_payment_methods()

        assert len(methods) == 2
        providers = [m.provider for m in methods]
        assert providers == ["visa", "erc4337"]

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_visa_card_surfaces_unchanged(self, mock_get, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "id": "vat_1abc23def45",
                "type": "card",
                "brand": "visa",
                "last4": "1387",
                "expMonth": 12,
                "expYear": 2027,
                "provider": "visa",
                "alias": "Personal Visa",
            }
        ]
        mock_get.return_value = mock_response

        methods = DelegationAPI(mock_options).list_payment_methods()

        assert len(methods) == 1
        assert methods[0].id == "vat_1abc23def45"
        assert methods[0].provider == "visa"
        assert methods[0].brand == "visa"


class TestCreateDelegationVisa:
    @patch("payments_py.x402.delegation_api.requests.post")
    def test_posts_provider_visa_verbatim(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "delegationId": "11111111-1111-1111-1111-111111111111",
            "delegationToken": "tok_xyz",
        }
        mock_post.return_value = mock_response

        payload = CreateDelegationPayload(
            provider="visa",
            providerPaymentMethodId="vat_1abc23def45",
            spendingLimitCents=10_000,
            durationSecs=3_600,
            planId="42",
        )
        result = DelegationAPI(mock_options).create_delegation(payload)

        assert result.delegation_id == "11111111-1111-1111-1111-111111111111"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        import json

        body = json.loads(kwargs["data"])
        assert body["provider"] == "visa"
        assert body["providerPaymentMethodId"] == "vat_1abc23def45"
        assert body["spendingLimitCents"] == 10_000
        assert body["durationSecs"] == 3_600
        assert body["planId"] == "42"

    @patch("payments_py.x402.delegation_api.requests.post")
    def test_surfaces_BCK_VISA_0014_envelope_on_4xx(self, mock_post, mock_options):
        # Mirrors the real envelope nvm-monorepo emits when consumerPrompt /
        # assuranceData are missing for a Visa delegation create.
        mock_post.return_value = _http_error_response(
            400,
            {
                "code": "BCK.VISA.0014",
                "httpStatus": 400,
                "message": "Visa delegation creation requires consumerPrompt and assuranceData",
                "category": "business",
                "retryable": False,
            },
        )

        payload = CreateDelegationPayload(
            provider="visa",
            providerPaymentMethodId="vat_1abc23def45",
            spendingLimitCents=1_000,
            durationSecs=3_600,
        )
        with pytest.raises(PaymentsError) as excinfo:
            DelegationAPI(mock_options).create_delegation(payload)

        assert excinfo.value.code == "BCK.VISA.0014"
        assert (
            "Visa delegation creation requires consumerPrompt and assuranceData"
            in str(excinfo.value)
        )
        assert "HTTP 400" in str(excinfo.value)

    @patch("payments_py.x402.delegation_api.requests.get")
    @patch("payments_py.x402.delegation_api.requests.post")
    def test_authorization_header_is_bearer(self, mock_post, mock_get, mock_options):
        ok_get = MagicMock()
        ok_get.raise_for_status.return_value = None
        ok_get.json.return_value = []
        ok_post = MagicMock()
        ok_post.raise_for_status.return_value = None
        ok_post.json.return_value = {
            "delegationId": "11111111-1111-1111-1111-111111111111",
        }
        mock_get.return_value = ok_get
        mock_post.return_value = ok_post

        api = DelegationAPI(mock_options)
        api.list_payment_methods()
        api.create_delegation(
            CreateDelegationPayload(
                provider="visa",
                providerPaymentMethodId="vat_1abc23def45",
                spendingLimitCents=1_000,
                durationSecs=3_600,
            )
        )

        for call in [mock_get.call_args, mock_post.call_args]:
            _, kwargs = call
            assert kwargs["headers"]["Authorization"].startswith("Bearer ")


class TestX402TokenVisa:
    @patch("payments_py.x402.token.requests.post")
    def test_visa_token_request_shape(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {"accessToken": "eyJ.visa.token"}
        mock_post.return_value = mock_response

        result = X402TokenAPI(mock_options).get_x402_access_token(
            plan_id="42",
            agent_id="agent-abc",
            token_options=X402TokenOptions(
                scheme="nvm:card-delegation",
                network="visa",
                delegationConfig=DelegationConfig(
                    delegationId="11111111-1111-1111-1111-111111111111"
                ),
            ),
        )

        assert result["accessToken"] == "eyJ.visa.token"
        mock_post.assert_called_once()
        _, kwargs = mock_post.call_args
        import json

        body = json.loads(kwargs["data"])
        assert body["accepted"]["scheme"] == "nvm:card-delegation"
        assert body["accepted"]["network"] == "visa"
        assert body["accepted"]["planId"] == "42"
        assert body["accepted"]["extra"]["agentId"] == "agent-abc"
        assert body["delegationConfig"] == {
            "delegationId": "11111111-1111-1111-1111-111111111111"
        }


def _visa_payment_required() -> X402PaymentRequired:
    return X402PaymentRequired(
        x402Version=2,
        resource=X402Resource(url="/tools/echo"),
        accepts=[X402Scheme(scheme="nvm:card-delegation", network="visa", planId="42")],
        extensions={},
    )


class TestFacilitatorVisa:
    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_verify_accepts_visa_network(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "isValid": True,
            "payer": "cust_42",
            "network": "visa",
            "urlMatching": "/tools/*",
        }
        mock_post.return_value = mock_response

        result = FacilitatorAPI(mock_options).verify_permissions(
            payment_required=_visa_payment_required(),
            x402_access_token="eyJ.visa.token",
            max_amount="5",
        )

        assert result.is_valid is True
        assert result.network == "visa"

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_settle_accepts_visa_network(self, mock_post, mock_options):
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "success": True,
            "transaction": "visa-tx-7c3a",
            "network": "visa",
            "creditsRedeemed": "5",
        }
        mock_post.return_value = mock_response

        result = FacilitatorAPI(mock_options).settle_permissions(
            payment_required=_visa_payment_required(),
            x402_access_token="eyJ.visa.token",
            max_amount="5",
        )

        assert result.success is True
        assert result.network == "visa"
        assert result.credits_redeemed == "5"

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_verify_surfaces_backend_code_on_4xx(self, mock_post, mock_options):
        mock_post.return_value = _http_error_response(
            403,
            {"code": "BCK.X402.0005", "message": "Insufficient credits"},
        )

        with pytest.raises(PaymentsError) as excinfo:
            FacilitatorAPI(mock_options).verify_permissions(
                payment_required=_visa_payment_required(),
                x402_access_token="eyJ.visa.token",
            )

        assert excinfo.value.code == "BCK.X402.0005"
        assert "Insufficient credits" in str(excinfo.value)


class TestErrorEnvelopeCoverage:
    """Tests for PaymentsError.from_response edge cases via real SDK call sites.

    The helper is reached through every public SDK method that calls the
    backend, so we exercise its branches through real call sites rather
    than testing it in isolation."""

    @patch("payments_py.x402.delegation_api.requests.get")
    def test_list_payment_methods_surfaces_backend_code_on_4xx(
        self, mock_get, mock_options
    ):
        mock_get.return_value = _http_error_response(
            401,
            {"code": "BCK.AUTH.0003", "message": "API key revoked"},
        )

        with pytest.raises(PaymentsError) as excinfo:
            DelegationAPI(mock_options).list_payment_methods()

        assert excinfo.value.code == "BCK.AUTH.0003"
        assert "API key revoked" in str(excinfo.value)

    @patch("payments_py.x402.token.requests.post")
    def test_get_x402_access_token_surfaces_backend_code_on_4xx(
        self, mock_post, mock_options
    ):
        mock_post.return_value = _http_error_response(
            400,
            {
                "code": "BCK.X402.0013",
                "message": "Delegation expired",
                "hint": "Re-run the WebAuthn ceremony on /payment-methods",
            },
        )

        with pytest.raises(PaymentsError) as excinfo:
            X402TokenAPI(mock_options).get_x402_access_token(
                plan_id="42",
                token_options=X402TokenOptions(
                    scheme="nvm:card-delegation",
                    network="visa",
                    delegation_config=DelegationConfig(
                        delegation_id="11111111-1111-1111-1111-111111111111"
                    ),
                ),
            )

        assert excinfo.value.code == "BCK.X402.0013"
        assert "Delegation expired" in str(excinfo.value)
        # ``hint`` should also surface so the developer sees the corrective action
        assert "Re-run the WebAuthn ceremony" in str(excinfo.value)

    @patch("payments_py.x402.delegation_api.requests.post")
    def test_non_json_body_falls_back_to_http_status_code(
        self, mock_post, mock_options
    ):
        """A 502 from a load balancer with an HTML body should not crash —
        the helper falls back to the generic message and ``http_<status>``."""
        mock_post.return_value = _http_error_response(
            502,
            json_error=ValueError("Expecting value: line 1 column 1 (char 0)"),
        )

        with pytest.raises(PaymentsError) as excinfo:
            DelegationAPI(mock_options).create_delegation(
                CreateDelegationPayload(
                    provider="visa",
                    providerPaymentMethodId="vat_1abc23def45",
                    spendingLimitCents=1_000,
                    durationSecs=3_600,
                )
            )

        assert excinfo.value.code == "http_502"
        assert "Failed to create delegation" in str(excinfo.value)
        assert "HTTP 502" in str(excinfo.value)

    @patch("payments_py.x402.delegation_api.requests.post")
    def test_non_dict_body_falls_back_to_http_status_code(
        self, mock_post, mock_options
    ):
        """A backend that returns a JSON array (rather than a dict envelope)
        should not crash either."""
        mock_post.return_value = _http_error_response(400, body=["unexpected"])  # type: ignore[arg-type]

        with pytest.raises(PaymentsError) as excinfo:
            DelegationAPI(mock_options).create_delegation(
                CreateDelegationPayload(
                    provider="visa",
                    providerPaymentMethodId="vat_1abc23def45",
                    spendingLimitCents=1_000,
                    durationSecs=3_600,
                )
            )

        assert excinfo.value.code == "http_400"
        assert "Failed to create delegation" in str(excinfo.value)

    @patch("payments_py.x402.delegation_api.requests.post")
    def test_details_field_is_appended_to_message(self, mock_post, mock_options):
        """The NVMException ``details`` field carries the per-field
        validation breakdown (e.g. which of consumerPrompt/assuranceData
        was missing) — it should surface to the developer."""
        mock_post.return_value = _http_error_response(
            400,
            {
                "code": "BCK.VISA.0014",
                "message": "Visa delegation creation requires consumerPrompt and assuranceData",
                "details": "consumerPrompt: missing",
            },
        )

        with pytest.raises(PaymentsError) as excinfo:
            DelegationAPI(mock_options).create_delegation(
                CreateDelegationPayload(
                    provider="visa",
                    providerPaymentMethodId="vat_1abc23def45",
                    spendingLimitCents=1_000,
                    durationSecs=3_600,
                )
            )

        assert excinfo.value.code == "BCK.VISA.0014"
        assert "consumerPrompt: missing" in str(excinfo.value)

    def test_from_response_handles_none(self):
        """A future caller wiring the helper outside of the standard
        try/except shape must not crash on a None response."""
        from payments_py.common.payments_error import PaymentsError as PE

        err = PE.from_response(None, "fallback msg")
        assert isinstance(err, PE)
        assert err.code == "payments_error"
        assert "fallback msg" in str(err)
