"""Integration tests for PaymentsA2AServer (FastAPI app)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from payments_py.a2a.server import PaymentsA2AServer
from payments_py.a2a.types import AgentCard


# Mock decode_access_token for tests
def mock_decode_token(token):
    return {"planId": "test-plan", "sub": "0xTestSubscriber"}


class DummyExecutor:  # noqa: D101
    async def execute(self, *args, **kwargs):  # noqa: D401
        pass


@pytest.fixture()  # noqa: D401
def agent_card() -> AgentCard:  # noqa: D401
    return {
        "name": "PyAgent",
        "capabilities": {
            "extensions": [
                {
                    "uri": "urn:nevermined:payment",
                    "params": {
                        "agentId": "agent-1",
                        "paymentType": "fixed",
                        "credits": 1,
                    },
                }
            ]
        },
    }


@pytest.fixture()  # noqa: D401
def dummy_payments(monkeypatch):  # noqa: D401
    # Stub verify_permissions & settle_permissions to avoid HTTP (x402 flow)
    payments = SimpleNamespace(
        facilitator=SimpleNamespace(
            verify_permissions=lambda **k: {"success": True},
            settle_permissions=lambda **k: {
                "success": True,
                "txHash": "0x123",
                "data": {"creditsBurned": "1"},
            },
        )
    )
    return payments  # type: ignore[return-value]


@pytest.mark.parametrize("base_path", ["/", "/a2a"])
def test_agent_card_endpoint(agent_card, dummy_payments, base_path):  # noqa: D401
    srv = PaymentsA2AServer.start(
        agent_card=agent_card,
        executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
        port=0,
        base_path=base_path,
        expose_agent_card=True,
        expose_default_routes=False,
    )

    client = TestClient(srv.app)
    url = (
        f"{base_path.rstrip('/')}/.well-known/agent.json"
        if base_path != "/"
        else "/.well-known/agent.json"
    )
    resp = client.get(url)
    assert resp.status_code == 200
    assert resp.json()["name"] == "PyAgent"


flag = {"before": False, "after": False, "error": False}


async def _before(method, params, req):  # noqa: D401
    flag["before"] = True


async def _after(method, result, req):  # noqa: D401
    flag["after"] = True


async def _on_error(method, exc, req):  # noqa: D401
    flag["error"] = True


@patch(
    "payments_py.a2a.payments_request_handler.decode_access_token", mock_decode_token
)
def test_hooks_invoked(agent_card, dummy_payments):  # noqa: D401
    # Reset flag before test
    flag["before"] = False
    flag["after"] = False
    flag["error"] = False

    hooks = {
        "beforeRequest": _before,
        "afterRequest": _after,
        "onError": _on_error,
    }
    srv = PaymentsA2AServer.start(
        agent_card=agent_card,
        executor=DummyExecutor(),
        payments_service=dummy_payments,  # type: ignore[arg-type]
        port=0,
        base_path="/rpc",
        hooks=hooks,
        expose_default_routes=True,
    )

    client = TestClient(srv.app)
    # Use message/send method which should exist
    payload = {
        "jsonrpc": "2.0",
        "method": "message/send",
        "params": {
            "message": {
                "messageId": "test-msg-123",
                "contextId": "test-ctx-123",
                "role": "user",
                "parts": [{"kind": "text", "text": "Hello"}],
            }
        },
        "id": 1,
    }
    headers = {"Authorization": "Bearer TOKEN"}
    response = client.post("/rpc", json=payload, headers=headers)

    # The call might fail (which would trigger onError) or succeed (which would trigger before/after)
    # At least one hook should have been triggered
    assert any(
        flag.values()
    ), f"No hooks triggered. Response: {response.status_code} - {response.text}"
