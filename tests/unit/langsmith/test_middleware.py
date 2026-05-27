"""Unit tests for the LangSmith Deployment payment middleware.

Mirrors the structure of tests/unit/x402/test_fastapi_middleware.py and adds
coverage for the LangSmith-specific surface: the build_payment_app factory,
env-var fallback for single-plan deployments, FastAPI-style {param} path
matching, and the settle-failure-still-returns-200 contract.
"""

import base64
import json
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
