"""Unit tests for the async OTel logger (payments-py#308 parity with the TS
``observability.withAsyncLogger``).

The ``traceloop`` extra is NOT installed in the unit CI env, so the traceloop /
OpenTelemetry imports are either exercised as the real "extra missing" path or
mocked via ``sys.modules`` injection.
"""

import sys
from types import ModuleType, SimpleNamespace
from unittest.mock import MagicMock, patch

import jwt
import pytest

from payments_py.api.observability_api import (
    AsyncLogger,
    ObservabilityAPI,
    with_async_logger,
)
from payments_py.common.types import PaymentOptions, PlanBalance, StartAgentRequest

_FAKE_API_KEY = "nvm:" + jwt.encode(
    {"sub": "0x47dB227b96D47380DB6F356aA971189c31E4e112", "o11y": "helicone-test-key"},
    "unit-test-secret-not-a-real-credential-0123456789",
    algorithm="HS256",
)


def _agent_request() -> StartAgentRequest:
    return StartAgentRequest(
        agentRequestId="arId-123",
        agentName="E2E Agent",
        agentId="agent-abc",
        balance=PlanBalance(
            planId="plan-xyz",
            planName="Test Plan",
            planType="4",
            holderAddress="0xConsumer",
            balance=10,
            creditsContract="0xCredits",
            isSubscriber=True,
            pricePerCredit=0,
        ),
        urlMatching="",
        verbMatching="",
        batch=False,
    )


class TestAssociationProperties:
    def test_only_helicone_property_headers_become_association_props(self):
        logger = with_async_logger(
            helicone_api_key="hk-1",
            helicone_async_logging_url="https://helicone.example/jawn/v1/trace/log",
            account_address="0xAcct",
            environment_name="sandbox",
            start_agent_request=_agent_request(),
            custom_properties={"sessionid": "s-1"},
        )
        props = logger._association_properties
        # Every key is a Helicone-Property-* name; the Helicone-Auth header is excluded.
        assert all(k.startswith("Helicone-Property-") for k in props)
        assert "Helicone-Auth" not in props
        assert props["Helicone-Property-agentId"] == "agent-abc"
        assert props["Helicone-Property-accountAddress"] == "0xAcct"
        assert props["Helicone-Property-environmentName"] == "sandbox"
        # Custom property forwarded.
        assert props["Helicone-Property-sessionid"] == "s-1"


class TestInitRequiresExtra:
    def test_init_without_traceloop_raises_import_error(self):
        # The 'traceloop' extra is not installed in the unit env, so the lazy
        # import inside init() fails with a clear, actionable ImportError
        # (matching the repo convention for missing optional extras).
        logger = AsyncLogger(
            "hk", "https://h/jawn/v1/trace/log", {"Helicone-Property-x": "y"}
        )
        # Make sure a stray injected module from another test isn't present.
        with patch.dict(sys.modules, {"traceloop": None, "traceloop.sdk": None}):
            with pytest.raises(ImportError) as exc:
                logger.init()
        assert "traceloop" in str(exc.value).lower()


def _fake_traceloop_modules():
    """Build a minimal fake traceloop + OTLP exporter module tree for sys.modules."""
    traceloop_pkg = ModuleType("traceloop")
    traceloop_sdk = ModuleType("traceloop.sdk")
    traceloop_sdk.Traceloop = MagicMock(name="Traceloop")

    # The OTLP exporter lives behind several namespace packages; each prefix must
    # resolve for `from opentelemetry...trace_exporter import OTLPSpanExporter`.
    otlp_leaf = ModuleType("opentelemetry.exporter.otlp.proto.http.trace_exporter")
    otlp_leaf.OTLPSpanExporter = MagicMock(name="OTLPSpanExporter")
    prefixes = {
        "opentelemetry": ModuleType("opentelemetry"),
        "opentelemetry.exporter": ModuleType("opentelemetry.exporter"),
        "opentelemetry.exporter.otlp": ModuleType("opentelemetry.exporter.otlp"),
        "opentelemetry.exporter.otlp.proto": ModuleType(
            "opentelemetry.exporter.otlp.proto"
        ),
        "opentelemetry.exporter.otlp.proto.http": ModuleType(
            "opentelemetry.exporter.otlp.proto.http"
        ),
        "opentelemetry.exporter.otlp.proto.http.trace_exporter": otlp_leaf,
    }
    return (
        {
            "traceloop": traceloop_pkg,
            "traceloop.sdk": traceloop_sdk,
            **prefixes,
        },
        traceloop_sdk.Traceloop,
        otlp_leaf.OTLPSpanExporter,
    )


class TestInitWiring:
    def test_init_configures_traceloop_with_helicone_exporter(self):
        fake_modules, traceloop_mock, exporter_cls = _fake_traceloop_modules()
        url = "https://helicone.example/jawn/v1/trace/log"
        logger = AsyncLogger(
            helicone_api_key="hk-secret",
            helicone_async_logging_url=url,
            association_properties={"Helicone-Property-agentId": "agent-abc"},
            instruments={"OPENAI"},
            app_name="my-agent",
        )

        with patch.dict(sys.modules, fake_modules):
            logger.init()

        # Custom OTLP exporter points at the Helicone async URL with a bearer header.
        exporter_cls.assert_called_once()
        _, kwargs = exporter_cls.call_args
        assert kwargs["endpoint"] == url
        assert kwargs["headers"] == {"Authorization": "Bearer hk-secret"}

        # Traceloop.init gets that exporter, batching off, and the instruments set.
        traceloop_mock.init.assert_called_once()
        _, init_kwargs = traceloop_mock.init.call_args
        assert init_kwargs["exporter"] is exporter_cls.return_value
        assert init_kwargs["disable_batch"] is True
        assert init_kwargs["instruments"] == {"OPENAI"}
        assert init_kwargs["app_name"] == "my-agent"

        # Association properties are registered.
        traceloop_mock.set_association_properties.assert_called_once_with(
            {"Helicone-Property-agentId": "agent-abc"}
        )


class TestObservabilityApiWiring:
    def test_async_logging_url_and_method(self):
        payments = ObservabilityAPI.get_instance(
            PaymentOptions(nvm_api_key=_FAKE_API_KEY, environment="sandbox")
        )
        # jawn OTLP endpoint (…/v1/trace/log, not /v1/traces).
        assert payments.helicone_async_logging_url.endswith("jawn/v1/trace/log")

        logger = payments.with_async_logger(_agent_request())
        assert isinstance(logger, AsyncLogger)
        assert logger._helicone_async_logging_url == payments.helicone_async_logging_url
        # The helicone key (o11y claim) and account address (sub claim) must flow
        # through, not get swapped for each other or the environment name.
        assert logger._helicone_api_key == "helicone-test-key"
        props = logger._association_properties
        assert props["Helicone-Property-agentId"] == "agent-abc"
        assert (
            props["Helicone-Property-accountAddress"]
            == "0x47dB227b96D47380DB6F356aA971189c31E4e112"
        )
        assert props["Helicone-Property-environmentName"] == payments.environment_name

    def test_method_forwards_non_default_args(self):
        # Pin the method's positional delegation to the module function: an
        # arg-order regression (e.g. swapping instruments/app_name) would fail here.
        payments = ObservabilityAPI.get_instance(
            PaymentOptions(nvm_api_key=_FAKE_API_KEY, environment="sandbox")
        )
        logger = payments.with_async_logger(
            _agent_request(),
            custom_properties={"sessionid": "s-9"},
            instruments={"OPENAI"},
            app_name="svc-x",
        )
        assert logger._instruments == {"OPENAI"}
        assert logger._app_name == "svc-x"
        assert logger._association_properties["Helicone-Property-sessionid"] == "s-9"

    def test_per_request_loggers_do_not_share_properties(self):
        # Two concurrent requests → two loggers, each carrying only its own
        # tags. The SDK introduces no shared mutable state between them (the
        # per-request isolation at runtime is OpenTelemetry's contextvars).
        payments = ObservabilityAPI.get_instance(
            PaymentOptions(nvm_api_key=_FAKE_API_KEY, environment="sandbox")
        )
        req_a = _agent_request()
        req_b = _agent_request()
        req_b.agent_id = "agent-B"
        logger_a = payments.with_async_logger(
            req_a, custom_properties={"sessionid": "A"}
        )
        logger_b = payments.with_async_logger(
            req_b, custom_properties={"sessionid": "B"}
        )

        assert logger_a._association_properties is not logger_b._association_properties
        assert (
            logger_a._association_properties["Helicone-Property-agentId"] == "agent-abc"
        )
        assert (
            logger_b._association_properties["Helicone-Property-agentId"] == "agent-B"
        )
        assert logger_a._association_properties["Helicone-Property-sessionid"] == "A"
        assert logger_b._association_properties["Helicone-Property-sessionid"] == "B"
