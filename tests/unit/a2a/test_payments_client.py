"""Unit tests for PaymentsClient."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from payments_py.a2a.payments_client import PaymentsClient
from payments_py.x402.types import DelegationConfig


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
            delegation_config=DelegationConfig(delegation_id="test-delegation"),
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


# ---------------------------------------------------------------------------
# v3 access tokens (single-use) — nvm-monorepo#2646
# ---------------------------------------------------------------------------


def _encode_token(**authorization) -> str:
    from payments_py.x402.token import encode_access_token

    return encode_access_token(
        {"payload": {"authorization": authorization, "signature": "0xsig"}}
    )


V2_TOKEN = _encode_token(**{"from": "0xabc", "planId": "1"})


def _v3_token(nonce: str) -> str:
    return _encode_token(
        **{
            "from": "0xabc",
            "planId": "1",
            "agentId": "agent1",
            "resourceUrl": "https://agent.example/",
            "httpVerb": "POST",
            "nonce": nonce,
        }
    )


def _client_with_tokens(tokens, token_version=None, **binding):
    """A PaymentsClient whose mint returns ``tokens`` in order."""

    class StubClient:  # noqa: D101
        def __init__(self):
            self.send_message = AsyncMock(return_value={"ok": True})

    get_token_mock = AsyncMock(side_effect=[{"accessToken": token} for token in tokens])
    dummy_payments = SimpleNamespace(
        x402=SimpleNamespace(get_x402_access_token=get_token_mock),
        agents=SimpleNamespace(),
        requests=SimpleNamespace(),
    )
    client = PaymentsClient(
        agent_base_url="https://agent.example",
        payments=dummy_payments,  # type: ignore[arg-type]
        agent_id="agent1",
        plan_id="1",
        delegation_config=DelegationConfig(delegation_id="test-delegation"),
        token_version=token_version,
        **binding,
    )
    client._client = StubClient()  # type: ignore[attr-defined]
    return client, get_token_mock


def _sent_tokens(client):
    return [
        call.kwargs["http_kwargs"]["headers"]["payment-signature"]
        for call in client._client.send_message.call_args_list  # type: ignore[attr-defined]
    ]


@pytest.mark.asyncio()
async def test_v3_token_is_minted_per_paid_request():
    """A v3 token is consumed by the seller's first settle, so the
    client-lifetime cache must never serve one twice — the second call would
    settle against a spent nonce (BCK.X402.0059)."""
    client, get_token_mock = _client_with_tokens([_v3_token("n1"), _v3_token("n2")])

    await client.send_message({})  # type: ignore[arg-type]
    await client.send_message({})  # type: ignore[arg-type]

    assert get_token_mock.await_count == 2
    first, second = _sent_tokens(client)
    assert first != second
    # Nothing was cached, so clear_token() has nothing to clear.
    assert client._access_token is None  # type: ignore[attr-defined]


@pytest.mark.asyncio()
async def test_v2_token_is_still_cached():
    """Existing v2 behaviour is unchanged: one mint for the client's lifetime."""
    client, get_token_mock = _client_with_tokens([V2_TOKEN])

    await client.send_message({})  # type: ignore[arg-type]
    await client.send_message({})  # type: ignore[arg-type]

    assert get_token_mock.await_count == 1
    assert _sent_tokens(client) == [V2_TOKEN, V2_TOKEN]
    assert client._access_token == V2_TOKEN  # type: ignore[attr-defined]


@pytest.mark.asyncio()
async def test_caching_follows_the_returned_token_not_the_request():
    """token_version=3 against a backend that predates #2646 is stripped
    silently and yields a v2 token — which must then be cached as usual, not
    re-minted on every call because of what was asked for."""
    client, get_token_mock = _client_with_tokens([V2_TOKEN], token_version=3)

    await client.send_message({})  # type: ignore[arg-type]
    await client.send_message({})  # type: ignore[arg-type]

    assert get_token_mock.await_count == 1
    assert get_token_mock.await_args.kwargs["token_options"].token_version == 3


@pytest.mark.asyncio()
async def test_v3_request_binds_the_token_to_the_agent_endpoint():
    """A v3 token is only worth minting BOUND — an unbound one is merely
    single-use, half of what the docs promise. Every A2A call is a JSON-RPC
    POST to the one service endpoint, so the binding is known from the
    constructor and nothing can fail to resolve."""
    client, get_token_mock = _client_with_tokens([_v3_token("n1")], token_version=3)

    await client.send_message({})  # type: ignore[arg-type]

    options = get_token_mock.await_args.kwargs["token_options"]
    assert options.token_version == 3
    assert options.resource == "https://agent.example/"
    assert options.http_verb == "POST"


@pytest.mark.asyncio()
async def test_explicit_binding_overrides_the_default():
    """The default binds the agent base URL, which assumes the seller is this
    SDK's A2A server (it advertises `str(request.url)`). A seller advertising
    a relative path — what this SDK's FastAPI middleware does — would never
    match, so such a caller must be able to say what to bind."""
    client, get_token_mock = _client_with_tokens(
        [_v3_token("n1")],
        token_version=3,
        resource="/a2a/",
        http_verb="post",
    )

    await client.send_message({})  # type: ignore[arg-type]

    options = get_token_mock.await_args.kwargs["token_options"]
    assert options.resource == "/a2a/"
    # Normalisation still happens in the request builder, not here.
    assert options.http_verb == "post"


@pytest.mark.asyncio()
async def test_binding_override_is_ignored_without_v3():
    """An override is still part of the v3 binding: on v2 it would bind nothing
    and arm the endpoint allowlist, which the request builder refuses."""
    client, get_token_mock = _client_with_tokens(
        [V2_TOKEN], resource="/a2a/", http_verb="POST"
    )

    await client.send_message({})  # type: ignore[arg-type]

    options = get_token_mock.await_args.kwargs["token_options"]
    assert options.resource is None
    assert options.http_verb is None


@pytest.mark.asyncio()
async def test_v2_request_sends_no_binding():
    """On v2 the binding is not signed: it would bind nothing and merely arm
    the backend's endpoint allowlist, and the request builder refuses the
    combination outright."""
    client, get_token_mock = _client_with_tokens([V2_TOKEN])

    await client.send_message({})  # type: ignore[arg-type]

    options = get_token_mock.await_args.kwargs["token_options"]
    assert options.resource is None
    assert options.http_verb is None


@pytest.mark.asyncio()
async def test_default_client_requests_no_explicit_token_version():
    """Opt-in: without token_version the SDK asks for nothing and the backend
    default (today v2) applies."""
    client, get_token_mock = _client_with_tokens([V2_TOKEN])

    await client.send_message({})  # type: ignore[arg-type]

    assert get_token_mock.await_args.kwargs["token_options"].token_version is None
