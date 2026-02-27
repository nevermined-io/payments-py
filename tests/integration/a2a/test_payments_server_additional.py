"""Additional integration tests focusing on middleware responses."""

import base64
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from payments_py.a2a.server import PaymentsA2AServer
from payments_py.a2a.types import AgentCard


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


@pytest.fixture()
def agent_card() -> AgentCard:  # noqa: D401
    return {
        "name": "PyAgent",
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "agent-1",
                        "planId": "plan-1",
                        "paymentType": "fixed",
                        "credits": 1,
                    },
                }
            ]
        },
    }


@pytest.fixture()
def base_server(agent_card):  # noqa: D401
    def _factory(start_processing=lambda *a, **k: {"agentRequestId": "REQ"}):
        payments_stub = SimpleNamespace(
            requests=SimpleNamespace(
                start_processing_request=start_processing,
                redeem_credits_from_request=lambda *a, **k: {},
            )
        )
        srv = PaymentsA2AServer.start(
            agent_card=agent_card,
            executor=DummyExecutor(),
            payments_service=payments_stub,  # type: ignore[arg-type]
            port=0,
            base_path="/rpc",
            expose_default_routes=True,
        )
        return TestClient(srv.app)

    return _factory


def test_missing_bearer_token_returns_402(base_server):  # noqa: D401
    client = base_server()
    payload = {"jsonrpc": "2.0", "method": "ping", "id": 1}
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 402
    assert "payment-required" in resp.headers
    # Decode and verify the payment-required header content
    pr_data = json.loads(base64.b64decode(resp.headers["payment-required"]))
    assert pr_data["accepts"][0]["planId"] is not None
    assert pr_data["accepts"][0]["extra"]["agentId"] == "agent-1"


def test_missing_bearer_token_multi_plan_returns_402():  # noqa: D401
    """Agent card with planIds returns 402 with multiple entries in accepts[]."""
    multi_plan_card = {
        "name": "MultiPlanAgent",
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "agent-1",
                        "planIds": ["plan-1", "plan-2"],
                        "paymentType": "fixed",
                        "credits": 1,
                    },
                }
            ]
        },
    }
    payments_stub = SimpleNamespace(
        requests=SimpleNamespace(
            start_processing_request=lambda *a, **k: {"agentRequestId": "REQ"},
            redeem_credits_from_request=lambda *a, **k: {},
        )
    )
    srv = PaymentsA2AServer.start(
        agent_card=multi_plan_card,
        executor=DummyExecutor(),
        payments_service=payments_stub,
        port=0,
        base_path="/rpc",
        expose_default_routes=True,
    )
    client = TestClient(srv.app)

    payload = {"jsonrpc": "2.0", "method": "ping", "id": 1}
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 402
    assert "payment-required" in resp.headers
    pr_data = json.loads(base64.b64decode(resp.headers["payment-required"]))
    assert len(pr_data["accepts"]) == 2
    assert pr_data["accepts"][0]["planId"] == "plan-1"
    assert pr_data["accepts"][1]["planId"] == "plan-2"
    assert pr_data["accepts"][0]["extra"]["agentId"] == "agent-1"
    assert pr_data["accepts"][1]["extra"]["agentId"] == "agent-1"


def test_validation_failure_returns_402(base_server):  # noqa: D401
    def _fail(*_a, **_k):  # noqa: D401
        raise RuntimeError("validation failed")

    client = base_server(start_processing=_fail)
    payload = {"jsonrpc": "2.0", "method": "ping", "id": 1}
    headers = {"payment-signature": "TOK"}
    resp = client.post("/rpc", json=payload, headers=headers)
    assert resp.status_code == 402
    assert "payment-required" in resp.headers
    assert resp.json()["error"]["message"].startswith("Validation error")
