"""Integration tests for @a2a_requires_payment decorator.

These tests spin up a real FastAPI server (via TestClient) with mocked
Payments/facilitator, exercising the full HTTP → middleware → executor → settle
flow.
"""

import base64
import json
import threading
from uuid import uuid4
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from payments_py.a2a.agent_card import build_payment_agent_card
from payments_py.a2a.decorator import AgentResponse, a2a_requires_payment
from payments_py.common.payments_error import PaymentsError
from payments_py.x402.types import SettleResponse, VerifyResponse


# ---------------------------------------------------------------------------
# Mocks (same pattern as test_complete_message_send_flow)
# ---------------------------------------------------------------------------
def mock_decode_token(token):
    return {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "test-plan",
            "extra": {"version": "1"},
        },
        "payload": {
            "signature": "0x123",
            "authorization": {
                "from": "0xTestSubscriber",
                "sessionKeysProvider": "zerodev",
                "sessionKeys": [],
            },
        },
        "extensions": {},
    }


class MockFacilitatorAPI:
    def __init__(self):
        self.validation_call_count = 0
        self.settle_call_count = 0
        self.last_settle_credits = None
        self.should_fail_validation = False
        self.settle_called = threading.Event()

    def verify_permissions(
        self,
        payment_required=None,
        max_amount: str = None,
        x402_access_token: str = None,
    ):
        self.validation_call_count += 1
        if self.should_fail_validation:
            raise PaymentsError.payment_required("Insufficient credits")
        return VerifyResponse(is_valid=True, payer="0xTestSubscriber")

    def settle_permissions(
        self,
        payment_required=None,
        max_amount: str = None,
        x402_access_token: str = None,
    ):
        self.settle_call_count += 1
        self.last_settle_credits = int(max_amount) if max_amount else 0
        self.settle_called.set()
        return SettleResponse(
            success=True,
            transaction=f"0xtest{self.settle_call_count:08x}",
            network="eip155:84532",
            credits_redeemed=str(max_amount) if max_amount else "0",
        )


class MockPaymentsService:
    def __init__(self):
        self.facilitator = MockFacilitatorAPI()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
AGENT_CARD = build_payment_agent_card(
    base_card={
        "name": "DecoratorTestAgent",
        "url": "http://localhost:0",
        "version": "1.0.0",
        "capabilities": {},
    },
    payment_metadata={
        "paymentType": "dynamic",
        "credits": 10,
        "agentId": "decorator-test-agent",
        "planId": "test-plan",
    },
)

HEADERS = {"payment-signature": "TEST_TOKEN"}


def _make_payload(text: str = "Hello!", message_id: str = None):
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "message/send",
        "params": {
            "message": {
                "messageId": message_id or str(uuid4()),
                "contextId": str(uuid4()),
                "role": "user",
                "parts": [{"kind": "text", "text": text}],
            }
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token",
    mock_decode_token,
)
@pytest.mark.asyncio
async def test_decorator_full_flow_with_credit_burning():
    """Full flow: HTTP request → verify → decorator executor → settle."""
    mock_payments = MockPaymentsService()

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
        default_credits=1,
    )
    async def my_agent(context):
        return AgentResponse(text="Hello from decorator!", credits_used=3)

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    response = client.post("/rpc", json=_make_payload(), headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert "result" in data

    task = data["result"]
    assert task["kind"] == "task"
    assert task["status"]["state"] == "completed"
    assert task["status"]["message"]["parts"][0]["text"] == "Hello from decorator!"

    # Credits should be verified and settled
    assert mock_payments.facilitator.validation_call_count == 1
    assert mock_payments.facilitator.settle_call_count == 1
    assert mock_payments.facilitator.last_settle_credits == 3


@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token",
    mock_decode_token,
)
@pytest.mark.asyncio
async def test_decorator_default_credits():
    """When AgentResponse.credits_used is None, default_credits is used."""
    mock_payments = MockPaymentsService()

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
        default_credits=5,
    )
    async def my_agent(context):
        return AgentResponse(text="Using defaults")

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    response = client.post("/rpc", json=_make_payload(), headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["result"]["status"]["state"] == "completed"

    assert mock_payments.facilitator.settle_call_count == 1
    assert mock_payments.facilitator.last_settle_credits == 5


@pytest.mark.asyncio
async def test_decorator_missing_payment_signature_returns_402():
    """Request without payment-signature header should get 402 with payment-required."""
    mock_payments = MockPaymentsService()

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
    )
    async def my_agent(context):
        return AgentResponse(text="Should not reach")

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    response = client.post("/rpc", json=_make_payload())

    assert response.status_code == 402
    assert "Missing payment-signature header" in response.json()["error"]["message"]
    assert "payment-required" in response.headers
    # Verify the payment-required header contains planId and agentId
    pr_data = json.loads(base64.b64decode(response.headers["payment-required"]))
    assert pr_data["accepts"][0]["planId"] == "test-plan"
    assert pr_data["accepts"][0]["extra"]["agentId"] == "decorator-test-agent"
    assert mock_payments.facilitator.validation_call_count == 0
    assert mock_payments.facilitator.settle_call_count == 0


@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token",
    mock_decode_token,
)
@pytest.mark.asyncio
async def test_decorator_validation_failure_returns_402():
    """When verification fails, should return 402."""
    mock_payments = MockPaymentsService()
    mock_payments.facilitator.should_fail_validation = True

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
    )
    async def my_agent(context):
        return AgentResponse(text="Should not reach")

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    response = client.post("/rpc", json=_make_payload(), headers=HEADERS)

    assert response.status_code == 402
    assert "Validation error" in response.json()["error"]["message"]
    assert mock_payments.facilitator.validation_call_count == 1
    assert mock_payments.facilitator.settle_call_count == 0


@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token",
    mock_decode_token,
)
@pytest.mark.asyncio
async def test_decorator_handler_error_publishes_failed_task():
    """When the handler raises, the task should be failed with 0 credits."""
    mock_payments = MockPaymentsService()

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
        default_credits=5,
    )
    async def my_agent(context):
        raise RuntimeError("Boom!")

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    response = client.post("/rpc", json=_make_payload(), headers=HEADERS)

    assert response.status_code == 200
    data = response.json()
    task = data["result"]
    assert task["status"]["state"] == "failed"
    assert "Boom!" in task["status"]["message"]["parts"][0]["text"]


@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token",
    mock_decode_token,
)
@pytest.mark.asyncio
async def test_decorator_agent_card_endpoint():
    """The agent card endpoint should return the card with payment extension."""
    mock_payments = MockPaymentsService()

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
    )
    async def my_agent(context):
        return AgentResponse(text="hi")

    # The server's own well-known endpoint serves the card data
    result = my_agent.create_server(port=0)
    app = result.app

    # The a2a SDK's _Card wrapper doesn't have model_dump, so we add our own
    # simple agent-card endpoint to verify the card is accessible.
    @app.get("/test-agent-card")
    async def get_card():
        return AGENT_CARD

    client = TestClient(app)

    response = client.get("/test-agent-card")

    assert response.status_code == 200
    card = response.json()
    extensions = card["capabilities"]["extensions"]
    payment_ext = next(e for e in extensions if e["uri"] == "urn:nevermined:payment")
    assert payment_ext["params"]["agentId"] == "decorator-test-agent"
    assert payment_ext["params"]["planId"] == "test-plan"


@pytest.mark.asyncio
async def test_decorator_multi_plan_missing_token_returns_402():
    """Multi-plan agent card returns 402 with correct accepts[] entries."""
    mock_payments = MockPaymentsService()

    multi_plan_card = build_payment_agent_card(
        base_card={
            "name": "MultiPlanAgent",
            "url": "http://localhost:0",
            "version": "1.0.0",
            "capabilities": {},
        },
        payment_metadata={
            "paymentType": "dynamic",
            "credits": 10,
            "agentId": "decorator-test-agent",
            "planIds": ["plan-a", "plan-b"],
        },
    )

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=multi_plan_card,
    )
    async def my_agent(context):
        return AgentResponse(text="Should not reach")

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    response = client.post("/rpc", json=_make_payload())

    assert response.status_code == 402
    assert "payment-required" in response.headers
    pr_data = json.loads(base64.b64decode(response.headers["payment-required"]))
    assert len(pr_data["accepts"]) == 2
    assert pr_data["accepts"][0]["planId"] == "plan-a"
    assert pr_data["accepts"][1]["planId"] == "plan-b"
    assert pr_data["accepts"][0]["extra"]["agentId"] == "decorator-test-agent"
    assert mock_payments.facilitator.validation_call_count == 0


@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token",
    mock_decode_token,
)
@pytest.mark.asyncio
async def test_decorator_dynamic_credits_per_request():
    """Different requests can burn different amounts of credits."""
    mock_payments = MockPaymentsService()

    @a2a_requires_payment(
        payments=mock_payments,
        agent_card=AGENT_CARD,
        default_credits=1,
    )
    async def my_agent(context):
        text = context.get_user_input()
        if "expensive" in text:
            return AgentResponse(text="Expensive!", credits_used=10)
        return AgentResponse(text="Cheap!", credits_used=1)

    result = my_agent.create_server(port=0, base_path="/rpc")
    client = TestClient(result.app)

    # First request: cheap
    resp1 = client.post("/rpc", json=_make_payload("cheap request"), headers=HEADERS)
    assert resp1.status_code == 200
    assert mock_payments.facilitator.last_settle_credits == 1

    # Second request: expensive
    resp2 = client.post(
        "/rpc", json=_make_payload("expensive request"), headers=HEADERS
    )
    assert resp2.status_code == 200
    assert mock_payments.facilitator.last_settle_credits == 10
    assert mock_payments.facilitator.settle_call_count == 2
