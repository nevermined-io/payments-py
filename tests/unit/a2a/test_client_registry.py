"""Unit tests for ClientRegistry."""

from types import SimpleNamespace
from unittest.mock import patch, AsyncMock

import pytest

from payments_py.a2a.client_registry import ClientRegistry


class DummyPayments:  # noqa: D101
    def __init__(self) -> None:
        self.agents = SimpleNamespace(get_agent_access_token=AsyncMock())


def _create_registry():  # noqa: D401
    return ClientRegistry(DummyPayments())


@pytest.fixture(autouse=True)  # noqa: D401
def patch_client_factory(monkeypatch):  # noqa: D401
    from unittest.mock import MagicMock

    def _factory_side_effect(*args, **kwargs):  # noqa: D401
        return MagicMock()

    mock_factory = patch(
        "payments_py.a2a.client_registry.PaymentsClient",
        side_effect=_factory_side_effect,
        autospec=True,
    )
    with mock_factory:
        yield


def test_same_instance_for_same_key():  # noqa: D401
    registry = _create_registry()
    opts = {
        "agent_base_url": "https://agent.example",
        "agent_id": "agent1",
        "plan_id": "1",
    }
    client1 = registry.get_client(**opts)  # type: ignore[arg-type]
    client2 = registry.get_client(**opts)  # type: ignore[arg-type]
    assert client1 is client2


def test_different_instance_for_different_keys():  # noqa: D401
    registry = _create_registry()
    opts1 = {
        "agent_base_url": "https://agent.example",
        "agent_id": "agent1",
        "plan_id": "1",
    }
    opts2 = {
        "agent_base_url": "https://agent.example",
        "agent_id": "agent1",
        "plan_id": "2",
    }
    client1 = registry.get_client(**opts1)  # type: ignore[arg-type]
    client2 = registry.get_client(**opts2)  # type: ignore[arg-type]
    assert client1 is not client2


def test_missing_parameter_raises():  # noqa: D401
    registry = _create_registry()
    with pytest.raises(ValueError):
        registry.get_client(agent_base_url="https://agent.example", agent_id="agent1", plan_id="")  # type: ignore[arg-type]
