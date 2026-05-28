"""Unit tests for BasePaymentsAPI's HTTP-body preprocessing.

The Nevermined backend (Node.js) validates uint256 fields with
``@IsUint256()`` which rejects JSON numbers above
``Number.MAX_SAFE_INTEGER`` (``2**53 - 1``) because they lose precision
when parsed back as JS ``number``. The Python SDK has no ``bigint`` type
to disambiguate, so it stringifies any int outside the safe range just
before JSON serialization. These tests pin that behavior down.
"""

import json
from unittest.mock import MagicMock

from payments_py.api.base_payments import (
    ALLOWED_EXTRA_HEADERS,
    BasePaymentsAPI,
    CURRENT_ORG_ID_HEADER,
    _JS_MAX_SAFE_INTEGER,
    _stringify_unsafe_ints,
)


class TestStringifyUnsafeInts:
    def test_safe_ints_pass_through(self):
        assert _stringify_unsafe_ints(0) == 0
        assert _stringify_unsafe_ints(1) == 1
        assert _stringify_unsafe_ints(_JS_MAX_SAFE_INTEGER) == _JS_MAX_SAFE_INTEGER
        assert _stringify_unsafe_ints(-_JS_MAX_SAFE_INTEGER) == -_JS_MAX_SAFE_INTEGER

    def test_unsafe_ints_are_stringified(self):
        unsafe = _JS_MAX_SAFE_INTEGER + 1
        assert _stringify_unsafe_ints(unsafe) == str(unsafe)
        big = (1 << 200) + 1234
        assert _stringify_unsafe_ints(big) == str(big)

    def test_negative_unsafe_ints_are_stringified(self):
        unsafe = -(_JS_MAX_SAFE_INTEGER + 1)
        assert _stringify_unsafe_ints(unsafe) == str(unsafe)

    def test_booleans_are_preserved_not_stringified(self):
        # bool subclasses int, but JSON ``true``/``false`` shouldn't
        # become the strings ``"True"``/``"False"``.
        assert _stringify_unsafe_ints(True) is True
        assert _stringify_unsafe_ints(False) is False

    def test_walks_nested_dicts_and_lists(self):
        big = (1 << 128) + 5
        body = {
            "nonce": big,
            "creditsConfig": {"durationSecs": big, "amount": 10},
            "amounts": [big, 1, big],
            "nested": {"deep": {"value": big}},
        }
        result = _stringify_unsafe_ints(body)
        assert result["nonce"] == str(big)
        assert result["creditsConfig"]["durationSecs"] == str(big)
        assert result["creditsConfig"]["amount"] == 10
        assert result["amounts"] == [str(big), 1, str(big)]
        assert result["nested"]["deep"]["value"] == str(big)

    def test_passes_through_strings_floats_none(self):
        body = {
            "id": "vat_abc",
            "rate": 1.5,
            "missing": None,
        }
        assert _stringify_unsafe_ints(body) == body


def _bp_with_safe_jwt() -> BasePaymentsAPI:
    """Build a BasePaymentsAPI without doing the real JWT parsing."""
    options = MagicMock()
    options.nvm_api_key = "nvm:eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"
    options.environment = "sandbox"
    options.return_url = ""
    options.app_id = None
    options.version = None
    return BasePaymentsAPI(options)


class TestGetBackendHTTPOptions:
    def test_serialized_body_stringifies_large_ints(self):
        bp = _bp_with_safe_jwt()
        big = (1 << 128) + 1
        opts = bp.get_backend_http_options(
            "POST",
            {"nonce": big, "creditsConfig": {"duration_secs": big, "amount": 10}},
        )
        body = json.loads(opts["data"])
        # Big ints become JSON strings on the wire — uint256 backend validator
        # accepts the string form, would reject the number form.
        assert body["nonce"] == str(big)
        assert body["creditsConfig"]["durationSecs"] == str(big)
        # Small int stays an int (still a JSON number on the wire).
        assert body["creditsConfig"]["amount"] == 10
        # Authorization header still wired correctly.
        assert opts["headers"]["Authorization"].startswith("Bearer ")

    def test_public_options_stringify_large_ints(self):
        bp = _bp_with_safe_jwt()
        big = (1 << 64) + 7
        opts = bp.get_public_http_options("POST", {"amount": big})
        body = json.loads(opts["data"])
        assert body["amount"] == str(big)
        # Public path doesn't carry Authorization
        assert "Authorization" not in opts["headers"]


class TestExtraHeadersAllowlist:
    """The ``extra_headers`` argument on :meth:`get_backend_http_options` is
    used by the per-call workspace-targeting path (``X-Current-Org-Id``).
    Without an allowlist a caller could inject ``Authorization`` or
    ``Content-Type`` through it and override the SDK's own auth — these
    tests pin the allowlist (mirror of TS ``ALLOWED_EXTRA_HEADERS``).
    """

    def test_allowlist_includes_only_current_org_id_header(self):
        # Hard-coded membership check — drift here implies the security
        # surface widened. Any addition must be a deliberate review item.
        assert ALLOWED_EXTRA_HEADERS == {CURRENT_ORG_ID_HEADER}

    def test_current_org_id_header_passes_through(self):
        bp = _bp_with_safe_jwt()
        opts = bp.get_backend_http_options(
            "GET",
            extra_headers={CURRENT_ORG_ID_HEADER: "org-target-123"},
        )
        assert opts["headers"][CURRENT_ORG_ID_HEADER] == "org-target-123"

    def test_unknown_headers_are_dropped(self):
        bp = _bp_with_safe_jwt()
        opts = bp.get_backend_http_options(
            "GET",
            extra_headers={"X-Custom-Trace-Id": "abc-123"},
        )
        assert "X-Custom-Trace-Id" not in opts["headers"]

    def test_authorization_header_cannot_be_overridden(self):
        # The SDK sets Authorization itself from the NVM API key. A caller
        # passing Authorization through extra_headers must not silently
        # replace it — that would let a per-call override hijack the auth.
        bp = _bp_with_safe_jwt()
        original_auth = bp.get_backend_http_options("GET")["headers"]["Authorization"]
        opts = bp.get_backend_http_options(
            "GET",
            extra_headers={"Authorization": "Bearer evil-token"},
        )
        assert opts["headers"]["Authorization"] == original_auth

    def test_content_type_header_cannot_be_overridden(self):
        bp = _bp_with_safe_jwt()
        opts = bp.get_backend_http_options(
            "POST",
            {"foo": "bar"},
            extra_headers={"Content-Type": "text/plain"},
        )
        assert opts["headers"]["Content-Type"] == "application/json"

    def test_mixed_allowed_and_disallowed_headers(self):
        # Allowed key still goes through; disallowed keys silently dropped.
        bp = _bp_with_safe_jwt()
        opts = bp.get_backend_http_options(
            "GET",
            extra_headers={
                CURRENT_ORG_ID_HEADER: "org-keep",
                "X-Forwarded-For": "192.0.2.1",
                "Cookie": "session=evil",
            },
        )
        assert opts["headers"][CURRENT_ORG_ID_HEADER] == "org-keep"
        assert "X-Forwarded-For" not in opts["headers"]
        assert "Cookie" not in opts["headers"]
