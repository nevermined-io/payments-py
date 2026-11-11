"""Unit tests for the facilitator settle contract: ``batch`` / ``margin_percent``
request-body binding and the ``success != true`` warn-but-return guard.

Mirrors the TS ``settlePermissions`` (``src/x402/facilitator-api.ts``):
``SettlePermissionsParams.{batch, marginPercent}`` and the 200-with-``success:
false`` warning. The spent-token (``BCK.X402.0059``) guard is covered by
``test_token_v3.py``.
"""

import json
import logging
from unittest.mock import MagicMock, patch

import pytest

from payments_py.x402.facilitator_api import FacilitatorAPI
from payments_py.x402.helpers import build_payment_required
from tests.x402_responses import make_settle_response


@pytest.fixture
def mock_options():
    mock = MagicMock()
    mock.nvm_api_key = (
        "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
        "eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
    )
    mock.environment = "sandbox"
    mock.return_url = ""
    mock.app_id = None
    mock.version = None
    return mock


def _ok_response(**settle_overrides):
    """A 200 response whose ``.json()`` is the real SettleResponse wire shape."""
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = make_settle_response(**settle_overrides).model_dump(
        by_alias=True
    )
    return resp


def _sent_body(mock_post) -> dict:
    """The JSON body that reached ``requests.post`` (serialized into ``data``)."""
    return json.loads(mock_post.call_args.kwargs["data"])


PAYMENT_REQUIRED = build_payment_required(
    plan_id="plan-1", agent_id="agent-1", network="eip155:84532"
)


class TestBatchAndMarginBinding:
    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_omitted_when_not_passed(self, mock_post, mock_options):
        mock_post.return_value = _ok_response()
        FacilitatorAPI(mock_options).settle_permissions(
            payment_required=PAYMENT_REQUIRED, x402_access_token="tok"
        )
        body = _sent_body(mock_post)
        assert "batch" not in body
        assert "marginPercent" not in body

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_batch_and_margin_bound_into_body(self, mock_post, mock_options):
        mock_post.return_value = _ok_response()
        FacilitatorAPI(mock_options).settle_permissions(
            payment_required=PAYMENT_REQUIRED,
            x402_access_token="tok",
            batch=True,
            margin_percent=5,
        )
        body = _sent_body(mock_post)
        assert body["batch"] is True
        assert body["marginPercent"] == 5

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_batch_false_is_sent_not_dropped(self, mock_post, mock_options):
        # ``is not None`` guard: an explicit False is a real request value.
        mock_post.return_value = _ok_response()
        FacilitatorAPI(mock_options).settle_permissions(
            payment_required=PAYMENT_REQUIRED, x402_access_token="tok", batch=False
        )
        assert _sent_body(mock_post)["batch"] is False

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_margin_zero_is_sent_not_dropped(self, mock_post, mock_options):
        mock_post.return_value = _ok_response()
        FacilitatorAPI(mock_options).settle_permissions(
            payment_required=PAYMENT_REQUIRED,
            x402_access_token="tok",
            margin_percent=0,
        )
        assert _sent_body(mock_post)["marginPercent"] == 0


class TestSuccessNotTrueWarns:
    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_warns_and_returns_verbatim_on_success_false(
        self, mock_post, mock_options, caplog
    ):
        mock_post.return_value = _ok_response(
            success=False,
            error_reason="Cannot order plan",
            credits_redeemed="0",
        )
        with caplog.at_level(
            logging.WARNING, logger="payments_py.x402.facilitator_api"
        ):
            result = FacilitatorAPI(mock_options).settle_permissions(
                payment_required=PAYMENT_REQUIRED, x402_access_token="tok"
            )
        # Returned verbatim — the caller needs the reason/billing/credit fields.
        assert result.success is False
        assert result.error_reason == "Cannot order plan"
        msg = caplog.text
        assert "did not settle" in msg
        assert "Cannot order plan" in msg
        assert "Do not treat the request as paid" in msg

    @patch("payments_py.x402.facilitator_api.requests.post")
    def test_no_warn_on_success(self, mock_post, mock_options, caplog):
        mock_post.return_value = _ok_response(success=True)
        with caplog.at_level(
            logging.WARNING, logger="payments_py.x402.facilitator_api"
        ):
            result = FacilitatorAPI(mock_options).settle_permissions(
                payment_required=PAYMENT_REQUIRED, x402_access_token="tok"
            )
        assert result.success is True
        assert "did not settle" not in caplog.text
