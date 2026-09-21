"""``payments.mcp.start()`` must FORWARD ``oauthUrls`` to the OAuth router (payments-py#286 review).

``oauthUrls`` is the one knob a ``custom`` deployment whose backend host ``resolve_oauth_tier``
cannot classify has to state its tier. The router already read it (``options.get("oauthUrls")``)
and ``HttpRouterConfig`` already typed it — but ``McpServerManager.start`` built the router's
options dict by hand and never copied it across, so the managed entry point accepted the key
(``total=False`` TypedDict) and dropped it in silence: the document kept the bare authorize URL,
which is exactly the state the operator was setting the option to leave.

The test drives the real ``start()`` up to the router and captures what it is handed, without
binding a port: ``create_oauth_router`` is bound in the module namespace, so a spy that records
its options and raises a sentinel is enough.
"""

from unittest.mock import MagicMock

import pytest

from payments_py.mcp.core import server_manager as sm


class _StopAtRouter(Exception):
    pass


def _spy(captured):
    def create_oauth_router(options):
        captured.update(options)
        raise _StopAtRouter()

    return create_oauth_router


def _base_config(**extra):
    return {"port": 5001, "planId": "plan-123", "serverName": "srv", **extra}


def _payments(environment_name):
    # ``start()`` configures the paywall integration before it builds the router; a mock with
    # the environment name the manager falls back to is all that path needs. ``spec`` keeps the
    # double honest: a ``MagicMock()`` without it answers ANY attribute, so a manager reading a
    # misspelled one (the #293 bug read ``_environment_name``) would still get a value here.
    payments = MagicMock(spec=["environment_name", "mcp"])
    payments.environment_name = environment_name
    return payments


@pytest.mark.asyncio
async def test_start_forwards_oauth_urls_to_the_oauth_router(monkeypatch):
    captured = {}
    monkeypatch.setattr(sm, "create_oauth_router", _spy(captured))
    manager = sm.McpServerManager(_payments("custom"))
    urls = {
        "authorizationUri": "https://nevermined.app/oauth/authorize?network=sandbox"
    }

    with pytest.raises(_StopAtRouter):
        await manager.start(_base_config(oauthUrls=urls))

    assert captured["oauthUrls"] == urls
    # The rest of the hand-built dict is intact around it.
    assert captured["environment"] == "custom"
    assert captured["serverName"] == "srv"
    # start() rewinds to IDLE on any failure, so a follow-up start is not refused.
    assert manager._state == sm.ServerState.IDLE


@pytest.mark.asyncio
async def test_start_without_oauth_urls_forwards_none_not_a_default(monkeypatch):
    # Absent must stay absent (``None``): the router derives every URL itself in that case, and
    # a default here would be a second place inventing an authorize URL.
    captured = {}
    monkeypatch.setattr(sm, "create_oauth_router", _spy(captured))
    manager = sm.McpServerManager(_payments("sandbox"))

    with pytest.raises(_StopAtRouter):
        await manager.start(_base_config())

    assert "oauthUrls" in captured
    assert captured["oauthUrls"] is None


@pytest.mark.asyncio
async def test_start_takes_the_environment_from_the_payments_key_not_a_phantom_attribute(
    monkeypatch,
):
    # payments-py#293: the manager read ``_environment_name``, which the real class never sets
    # (it sets ``environment_name``), so every server that did not pass ``environment`` advertised
    # staging_sandbox documents whatever key it was built with. The double here has ONLY the real
    # attribute, so a regression to the phantom name falls through to the default and fails.
    captured = {}
    monkeypatch.setattr(sm, "create_oauth_router", _spy(captured))
    manager = sm.McpServerManager(_payments("sandbox"))

    with pytest.raises(_StopAtRouter):
        await manager.start(_base_config())

    assert captured["environment"] == "sandbox"


@pytest.mark.asyncio
async def test_start_lets_an_explicit_config_environment_win(monkeypatch):
    captured = {}
    monkeypatch.setattr(sm, "create_oauth_router", _spy(captured))
    manager = sm.McpServerManager(_payments("sandbox"))

    with pytest.raises(_StopAtRouter):
        await manager.start(_base_config(environment="live"))

    assert captured["environment"] == "live"


@pytest.mark.asyncio
async def test_start_defaults_to_staging_sandbox_only_when_the_object_has_no_environment(
    monkeypatch,
):
    captured = {}
    monkeypatch.setattr(sm, "create_oauth_router", _spy(captured))
    bare = MagicMock(
        spec=["mcp"]
    )  # neither attribute, as before the key-derived environment existed
    manager = sm.McpServerManager(bare)

    with pytest.raises(_StopAtRouter):
        await manager.start(_base_config())

    assert captured["environment"] == "staging_sandbox"
