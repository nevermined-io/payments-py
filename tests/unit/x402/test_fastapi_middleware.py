"""
Unit tests for FastAPI x402 payment middleware.
"""

import base64
import json
import re
from unittest.mock import MagicMock, AsyncMock, patch

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
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
from tests.asgi_raw import required_plan, send_raw
from tests.asgi_stream import STREAMED, StreamProbe
from tests.x402_responses import make_settle_response


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
        # The body, not just the status. This is the happy-path x402 test that
        # configures on_after_settle (the others force a hook or receipt
        # failure), so it is the one placed to notice a settled response losing
        # its payload while every hook still fires — e.g. draining the body to
        # attach the receipt and then returning the drained original. An empty
        # 200 with all three flags set used to pass here.
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


class TestSettledResponseIsPassedThrough:
    """payments-py#339: the receipt header used to be attached by reading the
    whole body into memory and rebuilding the response, so a large file stalled
    and a streamed response reached the client only once the handler finished."""

    @pytest.mark.asyncio
    async def test_a_streamed_body_reaches_the_client_while_the_handler_runs(
        self, mock_payments, valid_token
    ):
        probe = StreamProbe()
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"GET /stream": {"plan_id": "test-plan-123", "credits": 1}},
        )

        @app.get("/stream")
        async def stream():
            return StreamingResponse(probe.body(), media_type="text/event-stream")

        headers, body = await probe.request(
            app, "GET", "/stream", {X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token}
        )

        assert body == STREAMED
        assert X402_HEADERS["PAYMENT_RESPONSE"] in headers
        mock_payments.facilitator.settle_permissions.assert_called_once()

    def test_a_repeated_response_header_keeps_every_value(
        self, mock_payments, valid_token
    ):
        """Rebuilding from ``dict(response.headers)`` kept only the first value
        of a repeated header, so a handler setting two cookies lost one."""
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /ask": {"plan_id": "test-plan-123", "credits": 1}},
        )

        @app.post("/ask")
        async def ask():
            response = JSONResponse({"ok": True})
            response.set_cookie("first", "1")
            response.set_cookie("second", "2")
            return response

        response = TestClient(app).post(
            "/ask", headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token}
        )

        assert response.status_code == 200
        assert len(response.headers.get_list("set-cookie")) == 2
        assert X402_HEADERS["PAYMENT_RESPONSE"] in response.headers

    def test_a_reused_response_does_not_carry_a_previous_buyers_receipt(
        self, mock_payments, valid_token
    ):
        """``call_next`` hands back the handler's own header list. Writing the
        receipt into it put one buyer's settlement on a Response the handler
        returns again, so the next buyer, whose settle failed, got it too."""
        shared = JSONResponse({"ok": True})
        mock_payments.facilitator.settle_permissions.side_effect = [
            make_settle_response(transaction="0xalice"),
            RuntimeError("backend down"),
        ]
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /ask": {"plan_id": "test-plan-123", "credits": 1}},
        )

        @app.post("/ask")
        async def ask():
            return shared

        client = TestClient(app)
        headers = {X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token}
        alice = client.post("/ask", headers=headers)
        bob = client.post("/ask", headers=headers)

        assert X402_HEADERS["PAYMENT_RESPONSE"] in alice.headers
        assert bob.status_code == 200
        assert X402_HEADERS["PAYMENT_RESPONSE"] not in bob.headers

    def test_a_receipt_that_cannot_be_attached_still_runs_on_after_settle(
        self, mock_payments, valid_token
    ):
        """The burn committed, so the seller's post-settle record must fire
        even when the receipt header could not be built."""
        settled = []

        async def on_after_settle(request, credits, result):
            settled.append(credits)

        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"POST /ask": {"plan_id": "test-plan-123", "credits": 1}},
            options=PaymentMiddlewareOptions(on_after_settle=on_after_settle),
        )

        @app.post("/ask")
        async def ask():
            return JSONResponse({"ok": True})

        with patch.object(
            SettleResponse, "model_dump_json", side_effect=RuntimeError("boom")
        ):
            response = TestClient(app).post(
                "/ask", headers={X402_HEADERS["PAYMENT_SIGNATURE"]: valid_token}
            )

        assert response.status_code == 200
        assert response.json() == {"ok": True}
        assert X402_HEADERS["PAYMENT_RESPONSE"] not in response.headers
        assert settled == [1]


def _gated_app(mock_payments, key, method, route):
    """One route, gated by one key, with a flag recording whether it ran."""
    app = FastAPI()
    app.state.handler_ran = False
    app.add_middleware(
        PaymentMiddleware,
        payments=mock_payments,
        routes={key: {"plan_id": "test-plan-123", "credits": 1}},
    )

    async def handler(request: Request):
        request.app.state.handler_ran = True
        return JSONResponse({"ok": True})

    app.add_api_route(route, handler, methods=[method])
    return app


class TestRouteKeysMatchTheRouter:
    """A key that names a route must gate every request the router sends to it
    (#341). A request without a token must get a 402 and never reach the
    handler."""

    @pytest.mark.parametrize(
        "key, method, route, url",
        [
            # Express-style parameter, the syntax that already worked.
            ("GET /users/:user_id", "GET", "/users/{user_id}", "/users/42"),
            # FastAPI's own parameter syntax, copied from the decorator.
            ("GET /users/{user_id}", "GET", "/users/{user_id}", "/users/42"),
            # A path converter spans several segments.
            (
                "GET /files/{file_path:path}",
                "GET",
                "/files/{file_path:path}",
                "/files/a/b.csv",
            ),
            ("GET /items/{item_id:int}", "GET", "/items/{item_id:int}", "/items/7"),
            # A lower-case method in the key.
            ("post /ask", "POST", "/ask", "/ask"),
            # Padding around the key.
            ("POST /ask ", "POST", "/ask", "/ask"),
            (" POST /ask", "POST", "/ask", "/ask"),
            # A literal colon inside a segment is not a parameter.
            ("POST /v1/items:batch", "POST", "/v1/items:batch", "/v1/items:batch"),
        ],
    )
    def test_request_without_token_is_refused(
        self, mock_payments, key, method, route, url
    ):
        app = _gated_app(mock_payments, key, method, route)

        response = TestClient(app).request(method, url)

        assert response.status_code == 402
        assert app.state.handler_ran is False

    @pytest.mark.parametrize("key", ["POST /ask", "POST /api/ask"])
    def test_root_path_does_not_hide_the_route(self, mock_payments, key):
        """Behind a proxy (`uvicorn --root-path /api`) the server puts the
        root path in front of the request path, and the router strips it
        again. The key may name either form."""
        app = _gated_app(mock_payments, key, "POST", "/ask")

        # TestClient sends `root_path` and the full path, as uvicorn does.
        response = TestClient(app, root_path="/api").post("/api/ask")

        assert response.status_code == 402
        assert app.state.handler_ran is False

    def test_literal_key_wins_behind_a_root_path(self, mock_payments):
        """Precedence comes from the keys, not from which form of the path
        matched first: the literal full-path key keeps its request."""
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "POST /{agent}": {"plan_id": "cheap-plan"},
                "POST /api/ask": {"plan_id": "premium-plan"},
            },
        )

        response = TestClient(app, root_path="/api").post("/api/ask")

        assert response.status_code == 402
        payment_required = json.loads(
            base64.b64decode(response.headers[X402_HEADERS["PAYMENT_REQUIRED"]])
        )
        assert payment_required["accepts"][0]["planId"] == "premium-plan"

    @pytest.mark.parametrize(
        "path, raw_path",
        [
            ("/users/me?x", b"/users/me%3Fx"),
            ("/users/me#x", b"/users/me%23x"),
        ],
    )
    def test_a_decoded_query_mark_does_not_pick_a_cheaper_key(
        self, mock_payments, path, raw_path
    ):
        """uvicorn decodes `%3F` into the path; the router serves
        `/users/{user_id}` with `user_id="me?x"`, so that key sets the price,
        not `/users/me`."""
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "GET /users/{user_id}": {"plan_id": "premium-plan"},
                "GET /users/me": {"plan_id": "cheap-plan"},
            },
        )

        status, headers = send_raw(app, "GET", path, raw_path)

        assert status == 402
        assert required_plan(headers) == "premium-plan"

    def test_an_explicit_head_key_wins_over_the_get_fallback(self, mock_payments):
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "GET /x": {"plan_id": "get-plan"},
                "HEAD /x": {"plan_id": "head-plan"},
            },
        )

        response = TestClient(app).head("/x")

        assert response.status_code == 402
        assert required_plan(response.headers) == "head-plan"

    def test_head_reaches_a_starlette_get_route(self, mock_payments):
        """Starlette's `Route` serves HEAD with the GET handler, so a GET key
        must gate HEAD too. (FastAPI's `@app.get` answers HEAD with 405.)"""
        app = FastAPI()
        app.state.handler_ran = False
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"GET /doc": {"plan_id": "test-plan-123"}},
        )

        async def doc(request: Request):
            request.app.state.handler_ran = True
            return JSONResponse({"ok": True})

        app.router.add_route("/doc", doc, methods=["GET"])

        response = TestClient(app).head("/doc")

        assert response.status_code == 402
        assert app.state.handler_ran is False

    @pytest.mark.parametrize(
        "key, method, url",
        [
            # Another method on a keyed path, CORS preflights included.
            ("POST /ask", "GET", "/ask"),
            ("POST /ask", "OPTIONS", "/ask"),
            # Only HEAD falls back to GET keys, and only to GET keys.
            ("POST /ask", "HEAD", "/ask"),
            ("GET /ask", "OPTIONS", "/ask"),
            # `:name` spans one segment, so a longer path is another route.
            ("GET /users/:user_id", "GET", "/users/42/posts"),
        ],
    )
    def test_requests_the_key_does_not_name_pass_through(
        self, mock_payments, key, method, url
    ):
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={key: {"plan_id": "test-plan-123"}},
        )

        async def free(request: Request):
            return JSONResponse({"free": True})

        app.router.add_route("/ask", free, methods=["GET", "OPTIONS"])
        app.add_api_route("/users/{user_id}/posts", free, methods=["GET"])

        response = TestClient(app).request(method, url)

        assert response.status_code == 200

    def test_literal_key_wins_over_a_parameter_key(self, mock_payments):
        """`/users/me` matches both keys; the literal one is the specific one,
        whatever order the keys are declared in."""
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={
                "GET /users/{user_id}": {"plan_id": "param-plan"},
                "GET /users/me": {"plan_id": "me-plan"},
            },
        )

        response = TestClient(app).get("/users/me")

        assert response.status_code == 402
        payment_required = json.loads(
            base64.b64decode(response.headers[X402_HEADERS["PAYMENT_REQUIRED"]])
        )
        assert payment_required["accepts"][0]["planId"] == "me-plan"


class TestRouteKeysThatCannotMatchAreRejected:
    """A key the matcher cannot match used to protect nothing, silently. It
    must fail when the middleware is built, naming the key (#341)."""

    @pytest.mark.parametrize(
        "key",
        [
            "/api/tasks",  # no method
            "ALL /ask",  # not an HTTP method
            "FETCH /ask",
            "GET ask",  # not a path
            "GET /files/*",  # wildcard
            "GET /search?q=1",  # a query string is never part of the path
            "GET /f/:name.csv",  # partial-segment `:param`
            "GET /users/{user_id",  # stray brace
            "GET /users/user_id}",
            "GET /files/{file_path:nope}",  # unknown converter
            "GET /a/{x}/{x}",  # repeated parameter name
        ],
    )
    def test_unmatchable_key_raises(self, mock_payments, key):
        with pytest.raises(ValueError, match=re.escape(key)):
            PaymentMiddleware(
                app=None, payments=mock_payments, routes={key: {"plan_id": "p"}}
            )

    def test_routes_cannot_change_after_the_keys_are_compiled(self, mock_payments):
        """The gate reads the keys compiled in `__init__`, so a key added to
        `routes` later would be ignored, leaving its route unpaid."""
        middleware = PaymentMiddleware(
            app=None, payments=mock_payments, routes={"POST /ask": {"plan_id": "p"}}
        )

        with pytest.raises(TypeError):
            middleware.routes["POST /other"] = RouteConfig(plan_id="p")

    def test_the_factory_raises_when_called(self, mock_payments):
        """`payment_middleware()` runs at import time, before any server, so
        a rejected key stops the app from loading at all."""
        with pytest.raises(ValueError, match=re.escape("GET /files/*")):
            payment_middleware(mock_payments, {"GET /files/*": {"plan_id": "p"}})

    def test_add_middleware_never_serves_a_route_with_a_rejected_key(
        self, mock_payments
    ):
        """`app.add_middleware` builds the middleware on the app's first ASGI
        event, so the error comes then, and no route is served."""
        app = FastAPI()
        app.add_middleware(
            PaymentMiddleware,
            payments=mock_payments,
            routes={"GET /files/*": {"plan_id": "p"}},
        )

        @app.get("/health")
        async def health():
            return {"ok": True}

        with pytest.raises(ValueError, match=re.escape("GET /files/*")):
            TestClient(app).get("/health")

    @pytest.mark.parametrize(
        "first, second",
        [
            ("GET /users/:id", "GET /users/{user_id}"),
            ("get /ask", "GET /ask"),
            # No converter means `str`.
            ("GET /a/{x}", "GET /a/{y:str}"),
        ],
    )
    def test_keys_that_collide_raise(self, mock_payments, first, second):
        """Two keys for the same requests would leave one config dead."""
        with pytest.raises(ValueError, match=re.escape(second)):
            PaymentMiddleware(
                app=None,
                payments=mock_payments,
                routes={first: {"plan_id": "a"}, second: {"plan_id": "b"}},
            )
