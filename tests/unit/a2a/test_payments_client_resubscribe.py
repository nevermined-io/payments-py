"""Unit test for PaymentsClient resubscribe_task."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from payments_py.a2a.payments_client import PaymentsClient


class DummyPayments:  # noqa: D101
    def __init__(self):
        self.agents = SimpleNamespace(
            get_agent_access_token=AsyncMock(
                return_value=SimpleNamespace(access_token="TOK")
            )
        )


@pytest.mark.asyncio()  # noqa: D401
async def test_resubscribe_task():  # noqa: D401
    dummy_payments = DummyPayments()
    pc = PaymentsClient(
        agent_base_url="https://agent",
        payments=dummy_payments,  # type: ignore[arg-type]
        agent_id="aid",
        plan_id="pid",
    )

    # Patch underlying jsonrpc client
    async def fake_stream(*_args, **_kwargs):  # noqa: D401
        yield {"kind": "task"}

    with patch("payments_py.a2a.payments_client.ClientFactory.create") as gf:
        client_mock = AsyncMock()
        client_mock.resubscribe = lambda *a, **k: fake_stream()  # type: ignore[misc]
        gf.return_value = client_mock

        collected = []
        async for ev in pc.resubscribe_task({"taskId": "tid"}):  # type: ignore[arg-type]
            collected.append(ev)

    assert collected == [{"kind": "task"}]
    dummy_payments.agents.get_agent_access_token.assert_awaited()
