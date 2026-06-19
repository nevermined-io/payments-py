"""Unit tests for deriving the SDK environment from the API-key prefix.

The ``environment`` init option is deprecated: keys are ``<prefix>:<jwt>`` and
the prefix (the inverse of the backend's ``addPrefixToToken``) now drives the
environment. The option is still accepted as a fallback for unrecognized
(local/custom) prefixes, and using it emits a ``FutureWarning``. These tests
pin the precedence (key wins), the fallback, and the deprecation warning.
"""

import logging
import warnings
from contextlib import contextmanager

import pytest

import payments_py.api.base_payments as base_payments
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.environments import environment_from_api_key


@contextmanager
def _no_warning():
    """Assert that the wrapped block emits no warning."""
    with warnings.catch_warnings(record=True) as records:
        warnings.simplefilter("always")
        yield
    assert not records, f"expected no warnings, got {[str(r.message) for r in records]}"


# Unsigned JWT body (``sub`` + ``o11y`` claims) — the prefix before ``:`` is
# what these tests vary.
_JWT = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIweDEyMyIsIm8xMXkiOiJoZWxpY29uZS1rZXkifQ.fake"


def _key(prefix: str) -> str:
    return f"{prefix}:{_JWT}"


@pytest.fixture(autouse=True)
def _reset_once_flag():
    """The once-per-process logging guard is module-level; reset it so each
    test exercising the logging channel sees a clean slate."""
    base_payments._environment_deprecation_logged = False
    yield
    base_payments._environment_deprecation_logged = False


class TestEnvironmentFromApiKey:
    @pytest.mark.parametrize(
        "prefix,expected",
        [
            ("sandbox-staging", "staging_sandbox"),
            ("live-staging", "staging_live"),
            ("sandbox", "sandbox"),
            ("live", "live"),
        ],
    )
    def test_recognized_prefixes_map(self, prefix, expected):
        assert environment_from_api_key(_key(prefix)) == expected

    def test_prefix_is_case_insensitive(self):
        assert environment_from_api_key(_key("SANDBOX-STAGING")) == "staging_sandbox"

    @pytest.mark.parametrize(
        "key",
        [
            None,
            "",
            "no-colon-here",
            _key("nvm"),
            _key("local"),
            _key("unknown-prefix"),
        ],
    )
    def test_unrecognized_or_missing_returns_none(self, key):
        assert environment_from_api_key(key) is None


class TestResolveEnvironment:
    def test_recognized_prefix_wins_no_option(self):
        with _no_warning():
            resolved = BasePaymentsAPI._resolve_environment(
                _key("sandbox-staging"), None
            )
        assert resolved == "staging_sandbox"

    def test_recognized_prefix_wins_over_conflicting_option(self):
        with pytest.warns(FutureWarning, match="ignoring the passed 'live'"):
            resolved = BasePaymentsAPI._resolve_environment(
                _key("sandbox-staging"), "live"
            )
        assert resolved == "staging_sandbox"

    def test_recognized_prefix_with_matching_option_still_warns(self):
        with pytest.warns(FutureWarning, match="matched and was redundant"):
            resolved = BasePaymentsAPI._resolve_environment(_key("sandbox"), "sandbox")
        assert resolved == "sandbox"

    def test_unrecognized_prefix_falls_back_to_option_with_warning(self):
        with pytest.warns(FutureWarning, match="was not.*recognized"):
            resolved = BasePaymentsAPI._resolve_environment(_key("nvm"), "sandbox")
        assert resolved == "sandbox"

    def test_no_prefix_no_option_defaults_to_custom(self):
        with _no_warning():
            resolved = BasePaymentsAPI._resolve_environment(_key("nvm"), None)
        assert resolved == "custom"

    def test_missing_key_no_option_defaults_to_custom(self):
        with _no_warning():
            resolved = BasePaymentsAPI._resolve_environment(None, None)
        assert resolved == "custom"

    def test_deprecation_logs_once_per_process(self, caplog):
        with caplog.at_level(logging.WARNING, logger="payments_py.api.base_payments"):
            with pytest.warns(FutureWarning):
                BasePaymentsAPI._resolve_environment(_key("nvm"), "sandbox")
            with pytest.warns(FutureWarning):
                BasePaymentsAPI._resolve_environment(_key("nvm"), "sandbox")
        deprecation_logs = [
            r
            for r in caplog.records
            if "'environment' option is deprecated" in r.message
        ]
        assert len(deprecation_logs) == 1
