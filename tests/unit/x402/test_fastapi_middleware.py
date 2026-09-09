"""
Unit tests for FastAPI x402 payment middleware.
"""

import base64
import json
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from pydantic import BaseModel

from payments_py.x402.fastapi import (
    PaymentMiddleware,
    X402_HEADERS,
    RouteConfig,
    PaymentContext,
    PaymentMiddlewareOptions,
    payment_middleware,
)
from payments_py.x402.types import VerifyResponse, SettleResponse


class QueryRequest(BaseModel):
    """Request model for test endpoints."""

    query: str


@pytest.fixture
def mock_payments():
    """Create a mock Payments instance."""
    mock = MagicMock()

    # Mock verify_permissions
    verify_response = VerifyResponse(
        is_valid=True,
        invalid_reason=None,
        payer="0x1234567890abcdef",
        agent_request_id="test-request-id-123",
    )
    mock.facilitator.verify_permissions.return_value = verify_response

    # Mock settle_permissions
    settle_response = SettleResponse(
        success=True,
        error_reason=None,
        payer="0x1234567890abcdef",
        transaction="0xabc123",
        network="eip155:84532",
        credits_redeemed="1",
        remaining_balance="99",
    )
    mock.facilitator.settle_permissions.return_value = settle_response

    return mock


@pytest.fixture
def test_app(mock_payments):
    """Create a test FastAPI app with payment middleware."""
    app = FastAPI()

    app.add_middleware(
        PaymentMiddleware,
        payments=mock_payments,
        routes={
            "POST /ask": {"plan_id": "test-plan-123", "credits": 1},
            "GET /protected/:id": {"plan_id": "test-plan-123", "credits": 2},
        },
    )

    @app.post("/ask")
    async def ask(request: Request, body: QueryRequest):
        return JSONResponse({"response": f"Answer to: {body.query}"})

    @app.get("/protected/{item_id}")
    async def get_protected(item_id: str):
        return JSONResponse({"item_id": item_id})

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    return app


@pytest.fixture
def client(test_app):
    """Create a test client."""
    return TestClient(test_app)


@pytest.fixture
def valid_token():
    """Create a valid base64-encoded token."""
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
    """Tests for PaymentMiddleware class."""

    def test_unprotected_route_passes_through(self, client):
        """Test that unprotected routes are not affected by middleware."""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_protected_route_returns_402_without_token(self, client):
        """Test that protected routes return 402 when no token is provided."""
        response = client.post(
            "/ask",
            json={"query": "What is 2+2?"},
        )

        assert response.status_code == 402
        assert "Payment Required" in response.json()["error"]

        # Check payment-required header
        assert X402_HEADERS["PAYMENT_REQUIRED"] in response.headers
        payment_required_b64 = response.headers[X402_HEADERS["PAYMENT_REQUIRED"]]
        payment_required = json.loads(base64.b64decode(payment_required_b64))
        assert payment_required["x402Version"] == 2
        assert payment_required["accepts"][0]["planId"] == "test-plan-123"

    def test_protected_route_returns_200_with_valid_token(
        self, client, valid_token, mock_payments
    ):
        """Test that protected routes return 200 with valid token."""
        response = client.post(
            "/ask",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
            json={"query": "What is 2+2?"},
        )

        assert response.status_code == 200
        assert "Answer to: What is 2+2?" in response.json()["response"]

        # Verify that verify_permissions was called
        mock_payments.facilitator.verify_permissions.assert_called_once()

        # Verify that settle_permissions was called
        mock_payments.facilitator.settle_permissions.assert_called_once()

        # Check payment-response header
        assert X402_HEADERS["PAYMENT_RESPONSE"] in response.headers
        payment_response_b64 = response.headers[X402_HEADERS["PAYMENT_RESPONSE"]]
        payment_response = json.loads(base64.b64decode(payment_response_b64))
        assert payment_response["success"] is True

    def test_protected_route_returns_402_with_invalid_token(
        self, client, valid_token, mock_payments
    ):
        """Test that protected routes return 402 when verification fails."""
        # Make verify_permissions return invalid
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

    def test_path_parameter_matching(self, client, valid_token, mock_payments):
        """Test that routes with path parameters are matched correctly."""
        response = client.get(
            "/protected/item-456",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200
        assert response.json()["item_id"] == "item-456"

    def test_agent_failure_propagates_as_5xx(self, mock_payments, valid_token):
        """Regression: handler raises -> response is 5xx, NOT 402.

        Buyers are not charged for failed runs. Verify already happened
        (so the buyer's balance lock was set in the facilitator) but
        settle_permissions MUST NOT fire on a non-2xx response.

        Before the Sprint 3 backport, the outer try/except in dispatch
        wrapped ``await call_next(request)`` and silently converted any
        handler exception into a 402 - so a buyer hitting a broken
        endpoint would see 'Payment Required' and assume their token was
        bad. The fix splits the try/except so call_next is outside the
        verify-error catch.
        """
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /explode": {"plan_id": "test-plan-123", "credits": 1}},
        )

        @app.post("/explode")
        async def explode():
            raise RuntimeError("agent blew up")

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/explode",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 500
        mock_payments.facilitator.verify_permissions.assert_called_once()
        mock_payments.facilitator.settle_permissions.assert_not_called()


class TestRouteConfig:
    """Tests for RouteConfig dataclass."""

    def test_default_values(self):
        """Test RouteConfig default values."""
        config = RouteConfig(plan_id="test-plan")
        assert config.plan_id == "test-plan"
        assert config.credits == 1
        assert config.agent_id is None
        assert config.network is None
        assert config.scheme is None

    def test_custom_values(self):
        """Test RouteConfig with custom values."""
        config = RouteConfig(
            plan_id="custom-plan",
            credits=5,
            agent_id="agent-123",
            network="eip155:1",
        )
        assert config.plan_id == "custom-plan"
        assert config.credits == 5
        assert config.agent_id == "agent-123"
        assert config.network == "eip155:1"


class TestPaymentContext:
    """Tests for PaymentContext dataclass."""

    def test_payment_context_creation(self):
        """Test PaymentContext creation."""
        from payments_py.x402.types import X402PaymentRequired, X402Scheme, X402Resource

        payment_required = X402PaymentRequired(
            x402_version=2,
            resource=X402Resource(url="/ask"),
            accepts=[
                X402Scheme(
                    scheme="nvm:erc4337",
                    network="eip155:84532",
                    plan_id="test-plan",
                )
            ],
            extensions={},
        )

        context = PaymentContext(
            token="test-token",
            payment_required=payment_required,
            credits_to_settle=1,
            verified=True,
            agent_request_id="req-123",
        )

        assert context.token == "test-token"
        assert context.credits_to_settle == 1
        assert context.verified is True
        assert context.agent_request_id == "req-123"


class TestX402Headers:
    """Tests for X402_HEADERS constant."""

    def test_header_values(self):
        """Test X402_HEADERS has correct values."""
        assert X402_HEADERS["PAYMENT_SIGNATURE"] == "payment-signature"
        assert X402_HEADERS["PAYMENT_REQUIRED"] == "payment-required"
        assert X402_HEADERS["PAYMENT_RESPONSE"] == "payment-response"


class TestPaymentMiddlewareOptions:
    """Tests for PaymentMiddlewareOptions."""

    def test_default_options(self):
        """Test PaymentMiddlewareOptions default values."""
        options = PaymentMiddlewareOptions()
        assert options.token_header == [X402_HEADERS["PAYMENT_SIGNATURE"]]
        assert options.on_before_verify is None
        assert options.on_after_verify is None
        assert options.on_after_settle is None
        assert options.on_payment_error is None

    def test_custom_options(self):
        """Test PaymentMiddlewareOptions with custom values."""

        async def before_hook(req, pr):
            pass

        async def after_hook(req, ver):
            pass

        options = PaymentMiddlewareOptions(
            token_header="custom-header",
            on_before_verify=before_hook,
            on_after_verify=after_hook,
        )

        assert options.token_header == "custom-header"
        assert options.on_before_verify is before_hook
        assert options.on_after_verify is after_hook


class TestMiddlewareHooks:
    """Tests for middleware hooks."""

    def test_hooks_are_called(self, mock_payments, valid_token):
        """Test that hooks are called during request processing."""
        # Track hook calls
        hook_calls = {
            "before_verify": False,
            "after_verify": False,
            "after_settle": False,
        }

        async def on_before_verify(request, payment_required):
            hook_calls["before_verify"] = True

        async def on_after_verify(request, verification):
            hook_calls["after_verify"] = True
            assert verification.is_valid is True

        async def on_after_settle(request, credits_used, result):
            hook_calls["after_settle"] = True
            assert credits_used == 1

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /test": {"plan_id": "test-plan", "credits": 1}},
            options=PaymentMiddlewareOptions(
                on_before_verify=on_before_verify,
                on_after_verify=on_after_verify,
                on_after_settle=on_after_settle,
            ),
        )

        @app.post("/test")
        async def test_endpoint():
            return JSONResponse({"result": "ok"})

        client = TestClient(app)
        response = client.post(
            "/test",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200
        # The body, not just the status. This is the only x402 test that
        # configures on_after_settle, so it is the one placed to notice a
        # settled response losing its payload while every hook still fires —
        # e.g. returning the already-drained original instead of the rebuilt
        # one. An empty 200 with all three flags set used to pass here.
        assert response.json()["result"] == "ok"
        assert hook_calls["before_verify"] is True
        assert hook_calls["after_verify"] is True
        assert hook_calls["after_settle"] is True


class TestPaymentMiddlewareFactory:
    """Tests for payment_middleware factory function."""

    def test_factory_creates_middleware(self, mock_payments):
        """Test that payment_middleware factory creates working middleware."""
        middleware_class = payment_middleware(
            mock_payments,
            {"POST /test": {"plan_id": "test-plan", "credits": 1}},
        )

        app = FastAPI()
        app.add_middleware(middleware_class)

        @app.post("/test")
        async def test_endpoint():
            return JSONResponse({"result": "ok"})

        client = TestClient(app)

        # Test without token
        response = client.post("/test")
        assert response.status_code == 402


class TestDynamicCredits:
    """Tests for dynamic credits calculation."""

    def test_sync_callable_credits(self, mock_payments, valid_token):
        """Test that sync callable credits function works."""

        def calculate_credits(request: Request) -> int:
            # Simple sync function that returns 3 credits
            return 3

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "POST /generate": {"plan_id": "test-plan", "credits": calculate_credits}
            },
        )

        @app.post("/generate")
        async def generate():
            return JSONResponse({"result": "generated"})

        client = TestClient(app)
        response = client.post(
            "/generate",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200

        # Verify that verify_permissions was called with max_amount="3"
        call_args = mock_payments.facilitator.verify_permissions.call_args
        assert call_args.kwargs["max_amount"] == "3"

        # Verify that settle_permissions was called with max_amount="3"
        call_args = mock_payments.facilitator.settle_permissions.call_args
        assert call_args.kwargs["max_amount"] == "3"

    def test_async_callable_credits(self, mock_payments, valid_token):
        """Test that async callable credits function works."""

        async def calculate_credits(request: Request) -> int:
            # Async function that returns 5 credits
            return 5

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "POST /analyze": {"plan_id": "test-plan", "credits": calculate_credits}
            },
        )

        @app.post("/analyze")
        async def analyze():
            return JSONResponse({"result": "analyzed"})

        client = TestClient(app)
        response = client.post(
            "/analyze",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200

        # Verify that verify_permissions was called with max_amount="5"
        call_args = mock_payments.facilitator.verify_permissions.call_args
        assert call_args.kwargs["max_amount"] == "5"

        # Verify that settle_permissions was called with max_amount="5"
        call_args = mock_payments.facilitator.settle_permissions.call_args
        assert call_args.kwargs["max_amount"] == "5"

    def test_credits_based_on_request_body(self, mock_payments, valid_token):
        """Test calculating credits based on request body content."""

        credits_calculated = {"value": None}

        async def calculate_credits(request: Request) -> int:
            # Calculate credits based on request body
            body = await request.json()
            tokens = body.get("max_tokens", 100)
            credits = max(1, tokens // 100)
            credits_calculated["value"] = credits
            return credits

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "POST /chat": {"plan_id": "test-plan", "credits": calculate_credits}
            },
        )

        @app.post("/chat")
        async def chat(request: Request):
            body = await request.json()
            return JSONResponse(
                {"result": "response", "tokens": body.get("max_tokens")}
            )

        client = TestClient(app)

        # Request with 500 tokens should result in 5 credits
        response = client.post(
            "/chat",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
            json={"message": "Hello", "max_tokens": 500},
        )

        assert response.status_code == 200
        assert credits_calculated["value"] == 5

        # Verify settle was called with correct credits
        call_args = mock_payments.facilitator.settle_permissions.call_args
        assert call_args.kwargs["max_amount"] == "5"

    def test_payment_context_has_calculated_credits(self, mock_payments, valid_token):
        """Test that PaymentContext has the calculated credits value."""

        captured_context = {"credits": None}

        async def calculate_credits(request: Request) -> int:
            return 7

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "POST /test": {"plan_id": "test-plan", "credits": calculate_credits}
            },
        )

        @app.post("/test")
        async def test_endpoint(request: Request):
            context = request.state.payment_context
            captured_context["credits"] = context.credits_to_settle
            return JSONResponse({"result": "ok"})

        client = TestClient(app)
        response = client.post(
            "/test",
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token},
        )

        assert response.status_code == 200
        assert captured_context["credits"] == 7

    def test_route_config_with_callable_credits(self):
        """Test RouteConfig accepts callable credits."""

        def calc(req: Request) -> int:
            return 10

        config = RouteConfig(plan_id="test-plan", credits=calc)
        assert config.plan_id == "test-plan"
        assert callable(config.credits)
        # We can't easily test the callable without a request, but we verify it's stored


class TestV3TokenRelay:
    """The seller relays the access token unchanged — no protocol change for v3.

    A v3 token (nvm-monorepo#2646) is signed over ``agentId`` / ``resourceUrl``
    / ``httpVerb`` / ``nonce``, so ANY mutation on the way to verify or settle
    — re-encoding, trimming, normalising — turns it into a forgery
    (``BCK.X402.0005``). The middleware must hand the facilitator the exact
    bytes it received.
    """

    @pytest.fixture
    def v3_token(self):
        token_data = {
            "x402Version": 2,
            "accepted": {
                "scheme": "nvm:erc4337",
                "network": "eip155:84532",
                "planId": "test-plan-123",
            },
            "payload": {
                "signature": "0xtest",
                "authorization": {
                    "from": "0xsubscriber",
                    "agentId": "agent-1",
                    "resourceUrl": "http://testserver/ask",
                    "httpVerb": "POST",
                    "nonce": "0x0123456789abcdef",
                },
            },
        }
        return base64.b64encode(json.dumps(token_data).encode()).decode()

    def test_v3_token_reaches_verify_and_settle_byte_for_byte(
        self, client, mock_payments, v3_token
    ):
        response = client.post(
            "/ask",
            json={"query": "test"},
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: v3_token},
        )

        assert response.status_code == 200

        verify_token = mock_payments.facilitator.verify_permissions.call_args.kwargs[
            "x402_access_token"
        ]
        settle_token = mock_payments.facilitator.settle_permissions.call_args.kwargs[
            "x402_access_token"
        ]
        assert verify_token == v3_token
        assert settle_token == v3_token
        # And the relayed bytes still decode to the same signed authorization.
        assert (
            json.loads(base64.b64decode(settle_token))["payload"]["authorization"][
                "nonce"
            ]
            == "0x0123456789abcdef"
        )

    def test_settle_is_called_once_per_request(self, client, mock_payments, v3_token):
        """A v3 token is consumed by its FIRST settle, so the seller must not
        settle the same token twice within one request."""
        client.post(
            "/ask",
            json={"query": "test"},
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: v3_token},
        )

        assert mock_payments.facilitator.settle_permissions.call_count == 1


class TestSpentTokenIsNotServed:
    """A replayed v3 token must not buy the agent's output.

    The backend spends a v3 nonce at SETTLE only — `verify()` never consults
    the replay store, deliberately, because verify is a dry run a seller may
    repeat. So a replayed token passes verification, the handler runs, and the
    seller only learns the token was spent afterwards. Returning the generated
    body then would hand out the output for free, repeatable without limit.
    """

    def test_spent_token_gets_402_and_no_body(self, client, mock_payments):
        from payments_py.common.payments_error import PaymentsError

        # A PLAIN PaymentsError carrying the wire code, not the typed class:
        # `payments` is caller-supplied, so a BCK.X402.0059 rebuilt across a
        # process boundary or raised by a second copy of this package arrives
        # like this — and an isinstance check would miss it and serve the body.
        mock_payments.facilitator.settle_permissions.side_effect = PaymentsError(
            "access token already used", "BCK.X402.0059"
        )

        response = client.post(
            "/ask",
            json={"query": "test"},
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: "dGVzdA=="},
        )

        assert response.status_code == 402
        # The agent's answer must not be in the body.
        assert "Answer to:" not in response.text
        assert X402_HEADERS["PAYMENT_REQUIRED"] in response.headers
        assert "already used" in response.json()["message"]

    def test_transient_settle_failure_still_serves_the_response(
        self, client, mock_payments
    ):
        """The withholding is scoped to a spent token. A backend outage is not
        the buyer's fault and the value was already delivered, so that branch
        must keep returning the agent's output."""
        mock_payments.facilitator.settle_permissions.side_effect = RuntimeError(
            "backend down"
        )

        response = client.post(
            "/ask",
            json={"query": "test"},
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: "dGVzdA=="},
        )

        assert response.status_code == 200
        assert "Answer to: test" in response.text

    def test_spent_token_402_goes_through_on_payment_error(self, mock_payments):
        """Every other 402 in this middleware lets the hook observe and
        override. A seller who wired it for metrics or alerting must not be
        skipped on the one 402 that means "work delivered, unpaid" — the signal
        that someone is replaying tokens against them."""
        from payments_py.common.payments_error import PaymentsError

        seen = {}

        async def on_payment_error(error, request):
            seen["error"] = error
            return JSONResponse(status_code=418, content={"custom": True})

        mock_payments.facilitator.settle_permissions.side_effect = PaymentsError(
            "access token already used", "BCK.X402.0059"
        )

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /ask": {"plan_id": "test-plan-123", "credits": 1}},
            options=PaymentMiddlewareOptions(on_payment_error=on_payment_error),
        )

        @app.post("/ask")
        async def ask(body: QueryRequest):
            return JSONResponse({"response": f"Answer to: {body.query}"})

        response = TestClient(app).post(
            "/ask",
            json={"query": "test"},
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: "dGVzdA=="},
        )

        assert response.status_code == 418
        assert response.json() == {"custom": True}
        assert seen["error"].code == "BCK.X402.0059"

    def test_a_failure_after_a_successful_settle_still_serves_the_body(
        self, mock_payments
    ):
        """The withholding branch must be unreachable once the burn committed.

        `on_after_settle` raising this error is plausible for an agent that pays
        a downstream service from that hook — and withholding there would charge
        the buyer and give them nothing, while logging that the response was
        withheld to avoid serving a replay. Narrowing the settle `try` is what
        makes the branch mean what its comment says."""
        from payments_py.common.payments_error import PaymentsError

        async def on_after_settle(request, credits, result):
            raise PaymentsError("access token already used", "BCK.X402.0059")

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /ask": {"plan_id": "test-plan-123", "credits": 1}},
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        )

        @app.post("/ask")
        async def ask(body: QueryRequest):
            return JSONResponse({"response": f"Answer to: {body.query}"})

        response = TestClient(app).post(
            "/ask",
            json={"query": "test"},
            headers={X402_HEADERS["PAYMENT_SIGNATURE"]: "dGVzdA=="},
        )

        # Paid, so served.
        assert response.status_code == 200
        assert "Answer to: test" in response.text
