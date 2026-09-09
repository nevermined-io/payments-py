"""The registry's ``token_version`` wiring (nvm-monorepo#2646).

Deliberately a separate module from ``test_client_registry.py``: that file
patches ``PaymentsClient`` with an autouse fixture, so a client built there
carries no real attributes. These tests construct the real client — cheap, the
transport is created lazily — so they assert on the value that actually reached
it rather than on a call record.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from payments_py.a2a.client_registry import ClientRegistry


class DummyPayments:  # noqa: D101
    def __init__(self) -> None:
        self.x402 = SimpleNamespace(get_x402_access_token=AsyncMock())


_OPTS = {
    "agent_base_url": "https://agent.example",
    "agent_id": "agent1",
    "plan_id": "1",
}


def test_token_version_reaches_the_client():  # noqa: D401
    """Nothing else proves the parameter is wired: deleting it from the client
    construction leaves the rest of the suite green, so the v3 path could be
    silently inert for every A2A caller."""
    registry = ClientRegistry(DummyPayments())  # type: ignore[arg-type]

    client = registry.get_client(**_OPTS, token_version=3)  # type: ignore[arg-type]

    assert client._token_version == 3


def test_default_client_requests_no_token_version():  # noqa: D401
    """Opt-in: without it the backend default (today v2) applies."""
    registry = ClientRegistry(DummyPayments())  # type: ignore[arg-type]

    client = registry.get_client(**_OPTS)  # type: ignore[arg-type]

    assert client._token_version is None


def test_v2_then_v3_does_not_hand_back_the_cached_v2_client():  # noqa: D401
    """The cache key must cover ``token_version``.

    Clients are only constructed on a MISS, so a key blind to the version lets
    the first caller for a triple win for the registry's lifetime: the second
    caller explicitly asks for replay protection and is silently handed a
    client that mints reusable v2 tokens, caches them, and replays them on
    every paid call — no error, no warning, nothing on the returned object to
    inspect.
    """
    registry = ClientRegistry(DummyPayments())  # type: ignore[arg-type]

    v2_client = registry.get_client(**_OPTS)  # type: ignore[arg-type]
    v3_client = registry.get_client(**_OPTS, token_version=3)  # type: ignore[arg-type]

    assert v3_client is not v2_client
    assert v2_client._token_version is None
    assert v3_client._token_version == 3
    # Each version still caches on its own key.
    assert registry.get_client(**_OPTS, token_version=3) is v3_client  # type: ignore[arg-type]
    assert registry.get_client(**_OPTS) is v2_client  # type: ignore[arg-type]


def test_binding_overrides_reach_the_client_and_key_the_cache():  # noqa: D401
    """Same argument as the version: a second caller asking for a different
    binding must not be handed the first caller's client."""
    registry = ClientRegistry(DummyPayments())  # type: ignore[arg-type]

    default = registry.get_client(**_OPTS, token_version=3)  # type: ignore[arg-type]
    overridden = registry.get_client(  # type: ignore[arg-type]
        **_OPTS, token_version=3, resource="/a2a/", http_verb="POST"
    )

    assert overridden is not default
    assert default._resource is None
    assert overridden._resource == "/a2a/"
    assert overridden._http_verb == "POST"
    assert (
        registry.get_client(  # type: ignore[arg-type]
            **_OPTS, token_version=3, resource="/a2a/", http_verb="POST"
        )
        is overridden
    )
