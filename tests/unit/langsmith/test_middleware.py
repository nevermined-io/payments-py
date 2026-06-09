"""Unit tests for the LangSmith Deployment payment middleware.

Mirrors the structure of tests/unit/x402/test_fastapi_middleware.py and adds
coverage for the LangSmith-specific surface: the build_payment_app factory,
env-var fallback for single-plan deployments, FastAPI-style {param} path
matching, and the settle-failure-still-returns-200 contract.
"""

import base64
import json
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from payments_py.langsmith import (
    PaymentMiddleware,
    RouteConfig,
    X402_HEADERS,
    build_payment_app,
)
from payments_py.langsmith import middleware as ls_middleware
from payments_py.x402.types import SettleResponse, VerifyResponse


class QueryRequest(BaseModel):
    query: str


@pytest.fixture
def mock_payments():
    mock = MagicMock()
    mock.facilitator.verify_permissions.return_value = VerifyResponse(
        is_valid=True,
        invalid_reason=None,
        payer="0x1234567890abcdef",
        agent_request_id="test-request-id-123",
    )
    mock.facilitator.settle_permissions.return_value = SettleResponse(
        success=True,
        error_reason=None,
        payer="0x1234567890abcdef",
        transaction="0xabc123",
        network="eip155:84532",
        credits_redeemed="1",
        remaining_balance="99",
    )
    return mock


def _build_test_app(mock_payments, routes=None):
    """Build a FastAPI app with the LangSmith PaymentMiddleware and a few routes."""
    app = FastAPI()
    app.add_middleware(
        PaymentMiddleware,
        payments=mock_payments,
        routes=(
            routes
            if routes is not None
            else {
                "POST /ask": {"plan_id": "test-plan-123", "credits": 1},
                "POST /threads/{thread_id}/runs/wait": {
                    "plan_id": "test-plan-123",
                    "credits": 5,
                },
                "GET /legacy/:id": {"plan_id": "test-plan-123", "credits": 2},
            }
        ),
    )

    @app.post("/ask")
    async def ask(_request: Request, body: QueryRequest):
        return JSONResponse({"response": f"Answer to: {body.query}"})

    @app.post("/threads/{thread_id}/runs/wait")
    async def runs_wait(thread_id: str):
        return JSONResponse({"thread_id": thread_id, "output": "ran"})

    @app.get("/legacy/{item_id}")
    async def legacy(item_id: str):
        return JSONResponse({"item_id": item_id})

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @app.post("/explode")
    async def explode():
        raise RuntimeError("agent blew up")

    return app


@pytest.fixture
def test_app(mock_payments):
    return _build_test_app(mock_payments)


@pytest.fixture
def client(test_app):
    return TestClient(test_app, raise_server_exceptions=False)


@pytest.fixture
def valid_token():
    token_data = {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "test-plan-123",
        },
        "payload": {
            "signature": "0xtest",
            "authorization": {"from": "0xsubscriber"},
        },
    }
    return base64.b64encode(json.dumps(token_data).encode()).decode()


class TestPaymentMiddleware:
    def test_unprotected_route_passes_through(self, client, mock_payments):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}
        mock_payments.facilitator.verify_permissions.assert_not_called()
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_protected_route_returns_402_without_token(self, client):
        response = client.post("/ask", json={"query": "What is 2+2?"})

        assert response.status_code == 402
        assert "Payment Required" in response.json()["error"]
        assert X402_HEADERS["PAYMENT_REQUIRED"] in response.headers
        envelope = json.loads(
            base64.b64decode(response.headers[X402_HEADERS["PAYMENT_REQUIRED"]])
        )
        assert envelope["x402Version"] == 2
        assert envelope["accepts"][0]["planId"] == "test-plan-123"

    def test_protected_route_returns_200_with_valid_token(
        self, client, valid_token, mock_payments
    ):
        response = client.post(
            "/ask",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
            json={"query": "What is 2+2?"},
        )

        assert response.status_code == 200
        assert "Answer to: What is 2+2?" in response.json()["response"]
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_called_once()

        assert X402_HEADERS["PAYMENT_RESPONSE"] in response.headers
        receipt = json.loads(
            base64.b64decode(response.headers[X402_HEADERS["PAYMENT_RESPONSE"]])
        )
        assert receipt["success"] is True
        assert receipt["payer"] == "0x1234567890abcdef"

    def test_protected_route_returns_402_with_invalid_verify(
        self, client, valid_token, mock_payments
    ):
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False,
            invalid_reason="Insufficient credits",
            payer=None,
            agent_request_id=None,
        )

        response = client.post(
            "/ask",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
            json={"query": "What is 2+2?"},
        )

        assert response.status_code == 402
        assert "Insufficient credits" in response.json()["message"]
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_fastapi_style_path_parameter_matching(
        self, client, valid_token, mock_payments
    ):
        """LangGraph routes use {param} syntax — must match."""
        response = client.post(
            "/threads/thread-abc-123/runs/wait",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200
        assert response.json()["thread_id"] == "thread-abc-123"
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_called_once()

    def test_starlette_style_path_parameter_matching(
        self, client, valid_token, mock_payments
    ):
        """:param syntax also matches — same code path as FastAPI middleware."""
        response = client.get(
            "/legacy/item-456",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200
        assert response.json()["item_id"] == "item-456"

    def test_non_2xx_response_skips_settle(self, valid_token, mock_payments):
        """Agent raises -> response is 5xx -> settle NEVER called.

        Buyers are not charged for failed runs. Verify was already paid via
        the verify_permissions call so the buyer's balance lock was set, but
        the actual settle_permissions burn must NOT fire.
        """
        app = _build_test_app(
            mock_payments,
            routes={"POST /explode": {"plan_id": "test-plan-123", "credits": 1}},
        )
        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/explode",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 500
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_settle_failure_still_returns_200(
        self, client, valid_token, mock_payments, caplog
    ):
        """Settle raising AFTER a 2xx response must not surface to the client."""
        mock_payments.facilitator.settle_permissions.side_effect = RuntimeError(
            "facilitator down"
        )

        with caplog.at_level("ERROR"):
            response = client.post(
                "/ask",
                headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
                json={"query": "hi"},
            )

        assert response.status_code == 200
        assert response.json()["response"] == "Answer to: hi"
        # Settle failures must be logged at ERROR level
        assert any(
            "x402 settlement failed" in rec.message
            and "facilitator down" in rec.message
            for rec in caplog.records
        )
        # No payment-response header because settle never produced a receipt
        assert X402_HEADERS["PAYMENT_RESPONSE"] not in response.headers

    def test_multi_chunk_body_is_buffered_correctly(self, valid_token, mock_payments):
        """A multi-chunk body_iterator must be concatenated in full.

        Regression guard against a future refactor that breaks
        ``body += chunk`` (e.g. last-chunk-only assignment, missing
        ``async for``). All other tests use single-chunk JSONResponse so
        they would not catch the partial-buffer case.
        """
        from starlette.responses import StreamingResponse

        async def multi_chunk():
            yield b'{"response":'
            yield b'"chunked answer"}'

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"GET /stream": {"plan_id": "test-plan-123", "credits": 1}},
        )

        @app.get("/stream")
        async def stream_route():
            return StreamingResponse(multi_chunk(), media_type="application/json")

        client = TestClient(app)
        response = client.get(
            "/stream",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200
        assert response.json() == {"response": "chunked answer"}
        assert X402_HEADERS["PAYMENT_RESPONSE"] in response.headers

    def test_payment_context_available_in_handler(self, valid_token, mock_payments):
        """``request.state.payment_context`` must be reachable from the
        downstream handler - that is the primary surface for LangGraph
        code that needs ``agent_request_id`` for observability or
        ``credits_to_settle`` for dynamic pricing.
        """
        captured: dict = {}

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"GET /ctx": {"plan_id": "test-plan-123", "credits": 3}},
        )

        @app.get("/ctx")
        async def ctx_route(request: Request):
            ctx = request.state.payment_context
            captured["verified"] = ctx.verified
            captured["credits_to_settle"] = ctx.credits_to_settle
            captured["agent_request_id"] = ctx.agent_request_id
            return JSONResponse({"ok": True})

        TestClient(app).get(
            "/ctx",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert captured["verified"] is True
        assert captured["credits_to_settle"] == 3
        assert captured["agent_request_id"] == "test-request-id-123"

    def test_payment_signature_stripped_before_handler(
        self, valid_token, mock_payments
    ):
        """The payment-signature bearer token must NOT reach the handler.

        Sentry/OTEL/structlog auto-capture request headers and their
        default denylists do not cover payment-signature; leaving the
        header in scope would exfiltrate the x402 token to whichever
        observability tool the deployer wires in.
        """
        seen_header: dict = {}

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"GET /seen": {"plan_id": "test-plan-123", "credits": 1}},
        )

        @app.get("/seen")
        async def seen(request: Request):
            seen_header["payment-signature"] = request.headers.get("payment-signature")
            return JSONResponse({"ok": True})

        TestClient(app).get(
            "/seen",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert seen_header["payment-signature"] is None

    def test_no_store_cache_headers_on_settle_and_402(self, client, valid_token):
        """Receipt + envelope carry per-buyer financial metadata; both
        response paths must be Cache-Control: no-store so any CDN in
        front cannot leak them across buyers.
        """
        settled = client.post(
            "/ask",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
            json={"query": "hi"},
        )
        assert settled.status_code == 200
        assert settled.headers.get("cache-control") == "no-store"

        unsigned = client.post("/ask", json={"query": "hi"})
        assert unsigned.status_code == 402
        assert unsigned.headers.get("cache-control") == "no-store"


class TestUnmatchedRoutesPassThrough:
    def test_unmatched_route_passes_through_even_with_nvm_env_vars_set(
        self, mock_payments, monkeypatch
    ):
        """Setting NVM_* env vars in the user's environment must not gate
        paths the middleware has no route config for. The middleware does
        not read env vars - it only looks at the explicit routes dict.
        """
        monkeypatch.setenv("NVM_PLAN_ID", "irrelevant-env-plan")
        monkeypatch.setenv("NVM_CREDITS_PER_INVOKE", "99")

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /gated": {"plan_id": "explicit-plan", "credits": 1}},
        )

        @app.get("/ungated")
        async def ungated():
            return JSONResponse({"hit": True})

        client = TestClient(app)
        response = client.get("/ungated")
        assert response.status_code == 200
        mock_payments.facilitator.verify_permissions.assert_not_called()


class TestRouteConfig:
    def test_defaults(self):
        config = RouteConfig(plan_id="p")
        assert config.plan_id == "p"
        assert config.credits == 1
        assert config.agent_id is None
        assert config.scheme is None
        assert config.network is None

    def test_custom_values(self):
        config = RouteConfig(
            plan_id="custom",
            credits=5,
            agent_id="agent-1",
            network="eip155:1",
            scheme="nvm:erc4337",
        )
        assert config.credits == 5
        assert config.agent_id == "agent-1"
        assert config.network == "eip155:1"
        assert config.scheme == "nvm:erc4337"


class TestBuildPaymentApp:
    def test_returns_fastapi_with_middleware_applied(self, mock_payments):
        """The factory must return a FastAPI instance pre-wired with PaymentMiddleware."""
        app = build_payment_app(
            payments=mock_payments,
            routes={"POST /runs": RouteConfig(plan_id="p", credits=1)},
        )

        assert isinstance(app, FastAPI)
        # PaymentMiddleware must be present in the user_middleware stack
        middleware_classes = [m.cls for m in app.user_middleware]
        assert PaymentMiddleware in middleware_classes

    def test_factory_smoke_test_402_without_token(self, mock_payments):
        """End-to-end: the factory-produced app emits 402 on unsigned requests."""
        app = build_payment_app(
            payments=mock_payments,
            routes={"POST /runs": {"plan_id": "p", "credits": 1}},
        )

        @app.post("/runs")
        async def runs():
            return JSONResponse({"ok": True})

        client = TestClient(app)
        response = client.post("/runs")

        assert response.status_code == 402
        assert X402_HEADERS["PAYMENT_REQUIRED"] in response.headers

    def test_factory_accepts_none_routes(self, mock_payments, monkeypatch):
        """routes=None is valid; behavior matches routes={} (env-var fallback only)."""
        monkeypatch.delenv("NVM_PLAN_ID", raising=False)
        app = build_payment_app(payments=mock_payments, routes=None)

        @app.get("/x")
        async def x():
            return JSONResponse({"ok": True})

        client = TestClient(app)
        # No routes + no env vars -> pass through
        assert client.get("/x").status_code == 200


def _our_optional_warnings(recwarn):
    """Only the build_payment_app 'no longer required' UserWarnings.

    Scoped by message so unrelated UserWarnings from FastAPI/Starlette can't
    make the assertions pass or fail spuriously.
    """
    return [
        w
        for w in recwarn.list
        if issubclass(w.category, UserWarning)
        and "no longer required" in str(w.message)
    ]


class TestBuildPaymentAppOptionalWarning:
    """build_payment_app warns it's optional on langgraph-api >= 0.6.15.

    The spike (nvm-monorepo#1762) bisected the OpenAPI-docstring crash fix to
    langgraph-api 0.6.15 (``get_schema`` broadened its catch to
    ``except Exception``), so a plain Starlette http.app boots without the
    FastAPI wrapper. #1763 surfaces that via a UserWarning (visible by default,
    unlike DeprecationWarning, so the nudge actually reaches deployers).
    """

    def test_warns_at_fix_version(self, mock_payments, monkeypatch):
        monkeypatch.setattr(ls_middleware, "_langgraph_api_version", lambda: (0, 6, 15))
        with pytest.warns(UserWarning, match="no longer required"):
            build_payment_app(payments=mock_payments, routes=None)

    def test_warning_points_at_plain_starlette_form(self, mock_payments, monkeypatch):
        monkeypatch.setattr(ls_middleware, "_langgraph_api_version", lambda: (0, 8, 7))
        with pytest.warns(UserWarning, match=r"Starlette\(middleware="):
            build_payment_app(payments=mock_payments, routes=None)

    @pytest.mark.parametrize(
        "detected,should_warn",
        [
            ((0, 6, 15), True),  # exactly the fix version
            ((0, 8, 7), True),  # newer 3-component
            ((0, 7), True),  # 2-component, above fix
            ((0, 6), False),  # 2-component == 0.6.0 < 0.6.15
            ((1,), True),  # 1-component major bump
            ((0,), False),  # 1-component, below
            ((0, 6, 14), False),  # the last crashing patch
        ],
    )
    def test_warning_gate_across_tuple_shapes(
        self, mock_payments, monkeypatch, recwarn, detected, should_warn
    ):
        """Pin the tuple-prefix comparison against the (0,6,15) sentinel so a
        future "harden the version compare" refactor can't silently regress the
        2-/1-component cases (e.g. break the "0.7" path)."""
        monkeypatch.setattr(ls_middleware, "_langgraph_api_version", lambda: detected)
        app = build_payment_app(payments=mock_payments, routes=None)
        assert isinstance(app, FastAPI)  # always built, warning or not
        assert bool(_our_optional_warnings(recwarn)) == should_warn

    def test_no_warning_when_version_undetected(
        self, mock_payments, monkeypatch, recwarn
    ):
        # langgraph-api absent / unparseable -> None -> silent, still returns app.
        monkeypatch.setattr(ls_middleware, "_langgraph_api_version", lambda: None)
        app = build_payment_app(payments=mock_payments, routes=None)
        assert isinstance(app, FastAPI)
        assert not _our_optional_warnings(recwarn)

    def test_warns_via_real_version_detection(self, mock_payments, monkeypatch):
        """End-to-end: patch only importlib.metadata.version and let the real
        parse -> compare -> warn seam run (the other tests stub
        _langgraph_api_version wholesale, never exercising the parser here)."""
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.8.7")
        with pytest.warns(UserWarning, match="no longer required"):
            build_payment_app(payments=mock_payments, routes=None)


class TestLanggraphApiVersionDetection:
    """_langgraph_api_version parses the installed version defensively."""

    def test_parses_three_components(self, monkeypatch):
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.6.15")
        assert ls_middleware._langgraph_api_version() == (0, 6, 15)

    def test_parses_prerelease_component(self, monkeypatch):
        # A pre-release suffix on the patch component is stripped to its int.
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.6.15rc1")
        assert ls_middleware._langgraph_api_version() == (0, 6, 15)

    def test_parses_non_digit_and_extra_components(self, monkeypatch):
        # A component with no leading digit degrades to 0 (the else-0 branch)...
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.6.rc1")
        assert ls_middleware._langgraph_api_version() == (0, 6, 0)
        # ...and a 4th component is dropped by the [:3] slice.
        monkeypatch.setattr("importlib.metadata.version", lambda name: "0.6.15.post1")
        assert ls_middleware._langgraph_api_version() == (0, 6, 15)

    def test_returns_none_when_not_installed(self, monkeypatch):
        def _raise(name):
            raise PackageNotFoundError(name)

        monkeypatch.setattr("importlib.metadata.version", _raise)
        assert ls_middleware._langgraph_api_version() is None
