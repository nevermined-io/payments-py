import asyncio
import pytest

from payments_py.mcp import build_mcp_integration


class PaymentsMock:
    def __init__(self):
        class Req:
            def __init__(self, parent):
                self._parent = parent

            def start_processing_request(self, agent_id, token, url, method):
                self._parent.calls.append(("start", agent_id, token, url, method))
                return {"agentRequestId": "req-1", "balance": {"isSubscriber": True}}

            def redeem_credits_from_request(self, request_id, token, credits):
                self._parent.calls.append(("redeem", request_id, token, int(credits)))
                return {"success": True}

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.requests = Req(self)
        self.agents = Agents()
        self.calls = []


def test_burns_fixed_credits_after_successful_call():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "test", "credits": 2})
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))
    assert out
    assert ("start", "did:nv:agent", "token") in [(c[0], c[1], c[2]) for c in pm.calls]
    assert ("redeem", "req-1", "token", 2) in pm.calls


def test_rejects_when_authorization_header_missing():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent"})

    async def base(_args, _extra=None):
        return {}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "test", "credits": 1})
    with pytest.raises(Exception) as err:
        asyncio.get_event_loop().run_until_complete(
            wrapped({}, {"requestInfo": {"headers": {}}})
        )
    assert getattr(err.value, "code", 0) == -32003


def test_burns_dynamic_credits_from_function():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": lambda _ctx: 7}
    )
    asyncio.get_event_loop().run_until_complete(
        wrapped({}, {"requestInfo": {"headers": {"authorization": "Bearer TT"}}})
    )
    assert ("redeem", "req-1", "TT", 7) in pm.calls


def test_defaults_to_one_credit_when_undefined():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:x", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"res": True}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "test"})
    asyncio.get_event_loop().run_until_complete(
        wrapped({}, {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}})
    )
    assert ("redeem", "req-1", "tok", 1) in pm.calls


def test_does_not_redeem_when_zero_credits():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:x", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"res": True}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": lambda _ctx: 0}
    )
    asyncio.get_event_loop().run_until_complete(
        wrapped({}, {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}})
    )
    assert not any(c[0] == "redeem" for c in pm.calls)


def test_propagates_error_on_redeem_when_configured():
    class P(PaymentsMock):
        def __init__(self):
            super().__init__()

            class R:
                def __init__(self, parent):
                    self._parent = parent

                def start_processing_request(self, agent_id, token, url, method):
                    return {"agentRequestId": "r", "balance": {"isSubscriber": True}}

                def redeem_credits_from_request(self, request_id, token, credits):
                    raise RuntimeError("redeem failed")

            self.requests = R(self)

    pm = P()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:x", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"ok": True}

    wrapped = mcp.with_paywall(
        base,
        {"kind": "tool", "name": "test", "credits": 1, "onRedeemError": "propagate"},
    )
    with pytest.raises(Exception) as err:
        asyncio.get_event_loop().run_until_complete(
            wrapped({}, {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}})
        )
    assert getattr(err.value, "code", 0) == -32002


def test_attach_register_resource_wraps_and_burns():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "srv"})

    captured = {}

    class Server:
        def registerResource(self, name, template, config, handler):
            captured["wrapped"] = handler

        def registerTool(self, name, config, handler):
            captured["tool"] = handler

        def registerPrompt(self, name, config, handler):
            captured["prompt"] = handler

    api = mcp.attach(Server())

    async def handler(_uri, _vars, _extra=None):
        return {
            "contents": [
                {"uri": "mcp://srv/res", "mimeType": "application/json", "text": "{}"}
            ]
        }

    api.registerResource(
        "res.test", {"tpl": True}, {"cfg": True}, handler, {"credits": 3}
    )
    wrapped = captured["wrapped"]
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped(object(), {"a": "1"}, extra))
    assert ("redeem", "req-1", "token", 3) in pm.calls


def test_accepts_authorization_from_multiple_header_containers():
    tokens = ["A", "B", "C", "D", "E"]
    variants = [
        {"requestInfo": {"headers": {"authorization": f"Bearer {tokens[0]}"}}},
        {"request": {"headers": {"Authorization": f"Bearer {tokens[1]}"}}},
        {"headers": {"authorization": f"Bearer {tokens[2]}"}},
        {"connection": {"headers": {"authorization": f"Bearer {tokens[3]}"}}},
        {
            "socket": {
                "handshake": {"headers": {"Authorization": f"Bearer {tokens[4]}"}}
            }
        },
    ]

    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "mcp"})

    async def base(_args, _extra=None):
        return {"ok": True}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "hdr", "credits": 1})
    for i, variant in enumerate(variants):
        pm.calls.clear()
        asyncio.get_event_loop().run_until_complete(wrapped({}, variant))
        assert ("redeem", "req-1", tokens[i], 1) in pm.calls


def test_redeems_after_async_iterable_completes():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "mcp"})

    async def make_iterable(chunks):
        async def gen():
            for c in chunks:
                await asyncio.sleep(0)
                yield c

        return gen()

    async def base(_args, _extra=None):
        return await make_iterable(["one", "two", "three"])

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "stream", "credits": 5})
    extra = {"requestInfo": {"headers": {"authorization": "Bearer tok"}}}
    iterable = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))
    # Not redeemed yet
    assert not any(c[0] == "redeem" for c in pm.calls)
    collected = []

    async def consume():
        async for chunk in iterable:
            collected.append(chunk)

    asyncio.get_event_loop().run_until_complete(consume())
    assert collected == ["one", "two", "three"]
    assert ("redeem", "req-1", "tok", 5) in pm.calls


def test_redeems_when_consumer_stops_stream_early():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "mcp"})

    async def make_iterable(chunks):
        async def gen():
            for c in chunks:
                await asyncio.sleep(0)
                yield c

        return gen()

    async def base(_args, _extra=None):
        return await make_iterable(["one", "two", "three"])

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "stream", "credits": 2})
    extra = {"requestInfo": {"headers": {"authorization": "Bearer tok"}}}
    iterable = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    async def consume_first_and_close():
        count = 0
        ait = iterable.__aiter__()
        try:
            await ait.__anext__()
            count += 1
        finally:
            if hasattr(ait, "aclose"):
                try:
                    await ait.aclose()
                except Exception:
                    pass
        return count

    count = asyncio.get_event_loop().run_until_complete(consume_first_and_close())
    assert count == 1
    assert ("redeem", "req-1", "tok", 2) in pm.calls
