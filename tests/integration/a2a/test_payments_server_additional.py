"""Additional integration tests focusing on middleware responses."""

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


def test_missing_bearer_token_returns_401(base_server):  # noqa: D401
    client = base_server()
    payload = {"jsonrpc": "2.0", "method": "ping", "id": 1}
    resp = client.post("/rpc", json=payload)
    assert resp.status_code == 401


def test_validation_failure_returns_402(base_server):  # noqa: D401
    def _fail(*_a, **_k):  # noqa: D401
        raise RuntimeError("validation failed")

    client = base_server(start_processing=_fail)
    payload = {"jsonrpc": "2.0", "method": "ping", "id": 1}
    headers = {"Authorization": "Bearer TOK"}
    resp = client.post("/rpc", json=payload, headers=headers)
    assert resp.status_code == 402
    assert resp.json()["error"]["message"].startswith("Validation error")
