"""Unit tests for PaymentsClient."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from payments_py.a2a.payments_client import PaymentsClient


class DummyPayments:  # noqa: D101
    def __init__(self) -> None:
        self._get_token_mock = AsyncMock(return_value={"accessToken": "XYZ"})
        self.x402 = SimpleNamespace(get_x402_access_token=self._get_token_mock)
        self.agents = SimpleNamespace()
        self.requests = SimpleNamespace()


@pytest_asyncio.fixture()  # noqa: D401
async def payments_client(monkeypatch):  # noqa: D401
    dummy_payments = DummyPayments()

    # Patch ClientFactory.get_jsonrpc_client to return a stub client
    class StubClient:  # noqa: D101
        def __init__(self):
            self.send_message = AsyncMock(return_value={"ok": True})

    with patch("payments_py.a2a.payments_client.ClientFactory") as mock_factory:
        mock_factory.return_value.get_jsonrpc_client.return_value = StubClient()
        client = PaymentsClient(
            agent_base_url="https://agent.example",
            payments=dummy_payments,  # type: ignore[arg-type]
            agent_id="agent1",
            plan_id="1",
        )
        # Monkeypatch internal _get_client to avoid ClientFactory path
        client._client = StubClient()  # type: ignore[attr-defined]
        yield client


@pytest.mark.asyncio()  # noqa: D401
async def test_access_token_cached(payments_client):  # noqa: D401
    # First call should fetch token and cache it
    await payments_client.send_message({})  # type: ignore[arg-type]
    # Token fetching occurs once; call again and ensure get_agent_access_token
    # not called again
    await payments_client.send_message({})  # type: ignore[arg-type]

    # The mocked get_agent_access_token should have been awaited exactly once
    # type: ignore[attr-defined]
    get_token_mock = payments_client._payments._get_token_mock
    assert get_token_mock.await_count == 1


@pytest.mark.asyncio()  # noqa: D401
async def test_payment_signature_header_injected(payments_client):  # noqa: D401
    await payments_client.send_message({})  # type: ignore[arg-type]
    stub_client = payments_client._client  # type: ignore[attr-defined]
    stub_client.send_message.assert_called()  # type: ignore[attr-defined]
    _, kwargs = stub_client.send_message.call_args  # type: ignore[attr-defined]
    headers = kwargs["http_kwargs"]["headers"]
    assert "payment-signature" in headers
    assert headers["payment-signature"] == "XYZ"
