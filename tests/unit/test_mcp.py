import asyncio
import pytest

from payments_py.mcp import build_mcp_integration


class PaymentsMock:
    def __init__(self, redeem_result=None):
        class Req:
            def __init__(self, parent, redeem_result):
                self._parent = parent
                self._redeem_result = redeem_result or {"success": True}

            def start_processing_request(self, agent_id, token, url, method):
                self._parent.calls.append(("start", agent_id, token, url, method))
                return {"agentRequestId": "req-1", "balance": {"isSubscriber": True}}

            def redeem_credits_from_request(self, request_id, token, credits):
                self._parent.calls.append(("redeem", request_id, token, int(credits)))
                return self._redeem_result

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.requests = Req(self, redeem_result)
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


def test_adds_metadata_to_result_after_successful_redemption():
    """Test that metadata is added to the result after successful credit redemption."""
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "test", "credits": 3})
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify the result has metadata
    assert "metadata" in out
    assert out["metadata"] is not None
    assert isinstance(out["metadata"], dict)

    # Verify metadata contains expected fields
    assert out["metadata"].get("success") is True
    assert out["metadata"].get("requestId") == "req-1"
    assert out["metadata"].get("creditsRedeemed") == "3"
    # txHash should be None since our mock doesn't return it
    assert out["metadata"].get("txHash") is None


def test_adds_metadata_with_txhash_when_redeem_returns_it():
    """Test that metadata includes txHash when redeem_credits_from_request returns it."""
    redeem_result = {"success": True, "txHash": "0x1234567890abcdef"}
    pm = PaymentsMock(redeem_result=redeem_result)
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "test", "credits": 5})
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify the result has metadata
    assert "metadata" in out
    assert out["metadata"] is not None
    assert isinstance(out["metadata"], dict)

    # Verify metadata contains expected fields including txHash
    assert out["metadata"].get("success") is True
    assert out["metadata"].get("requestId") == "req-1"
    assert out["metadata"].get("creditsRedeemed") == "5"
    assert out["metadata"].get("txHash") == "0x1234567890abcdef"


def test_does_not_add_metadata_when_redemption_fails():
    """Test that metadata is not added when credit redemption fails."""
    redeem_result = {"success": False, "error": "Insufficient credits"}
    pm = PaymentsMock(redeem_result=redeem_result)
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(base, {"kind": "tool", "name": "test", "credits": 2})
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify the result does not have metadata when redemption fails
    assert "metadata" not in out or out["metadata"] is None or not out["metadata"]


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


class PaymentsMockWithAgentRequest:
    """Mock that includes agentRequest in start_processing_request response."""

    def __init__(self, redeem_result=None):
        class Req:
            def __init__(self, parent, redeem_result):
                self._parent = parent
                self._redeem_result = redeem_result or {"success": True}

            def start_processing_request(self, agent_id, token, url, method):
                self._parent.calls.append(("start", agent_id, token, url, method))
                return {
                    "agentRequestId": "req-123",
                    "agentName": "Test Agent",
                    "agentId": agent_id,
                    "balance": {
                        "balance": 1000,
                        "creditsContract": "0x123",
                        "isSubscriber": True,
                        "pricePerCredit": 0.01,
                    },
                    "urlMatching": url,
                    "verbMatching": method,
                    "batch": False,
                }

            def redeem_credits_from_request(self, request_id, token, credits):
                self._parent.calls.append(("redeem", request_id, token, int(credits)))
                return self._redeem_result

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.requests = Req(self, redeem_result)
        self.agents = Agents()
        self.calls = []


def test_backward_compatibility_handlers_without_context():
    """Test that handlers without context parameter still work."""
    pm = PaymentsMockWithAgentRequest()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    async def old_handler(args, extra=None):
        return {
            "content": [{"type": "text", "text": f"Hello {args.get('name', 'World')}"}]
        }

    wrapped = mcp.with_paywall(
        old_handler, {"kind": "tool", "name": "test", "credits": 2}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({"name": "Alice"}, extra))

    assert out["content"][0]["text"] == "Hello Alice"
    assert ("start", "did:nv:agent", "token") in [(c[0], c[1], c[2]) for c in pm.calls]
    assert ("redeem", "req-123", "token", 2) in pm.calls


def test_handlers_with_context_receive_paywall_context():
    """Test that handlers with context parameter receive PaywallContext."""
    pm = PaymentsMockWithAgentRequest()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    captured_context = None

    async def new_handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {
            "content": [{"type": "text", "text": f"Hello {args.get('name', 'World')}"}]
        }

    wrapped = mcp.with_paywall(
        new_handler, {"kind": "tool", "name": "test", "credits": 3}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({"name": "Bob"}, extra))

    assert out["content"][0]["text"] == "Hello Bob"
    assert captured_context is not None
    assert isinstance(captured_context, dict)


def test_paywall_context_structure():
    """Test that PaywallContext contains all expected fields."""
    pm = PaymentsMockWithAgentRequest()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    captured_context = None

    async def context_handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        context_handler, {"kind": "tool", "name": "test", "credits": 5}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify PaywallContext structure
    assert captured_context is not None
    assert "auth_result" in captured_context
    assert "credits" in captured_context
    assert "agent_request" in captured_context

    # Verify auth_result structure
    auth_result = captured_context["auth_result"]
    assert auth_result["requestId"] == "req-123"
    assert auth_result["token"] == "token"
    assert auth_result["agentId"] == "did:nv:agent"
    assert auth_result["logicalUrl"].startswith("mcp://test-mcp/tools/test")
    assert "agentRequest" in auth_result

    # Verify agent_request structure
    agent_request = captured_context["agent_request"]
    assert agent_request["agentRequestId"] == "req-123"
    assert agent_request["agentName"] == "Test Agent"
    assert agent_request["agentId"] == "did:nv:agent"
    assert agent_request["balance"]["isSubscriber"] is True
    assert agent_request["balance"]["balance"] == 1000
    assert agent_request["urlMatching"].startswith("mcp://test-mcp/tools/test")
    assert agent_request["verbMatching"] == "POST"
    assert agent_request["batch"] is False

    # Verify credits
    assert captured_context["credits"] == 5


def test_context_handlers_can_use_agent_request_data():
    """Test that handlers can access and use agent request data from context."""
    pm = PaymentsMockWithAgentRequest()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "test-mcp"})

    async def business_logic_handler(args, extra=None, context=None):
        if not context:
            return {"error": "No context provided"}

        agent_request = context["agent_request"]
        auth_result = context["auth_result"]
        credits = context["credits"]

        # Use agent request data for business logic
        if not agent_request["balance"]["isSubscriber"]:
            return {"error": "Not a subscriber"}

        if agent_request["balance"]["balance"] < credits:
            return {"error": "Insufficient balance"}

        return {
            "content": [{"type": "text", "text": "Success"}],
            "metadata": {
                "agentName": agent_request["agentName"],
                "requestId": auth_result["requestId"],
                "creditsUsed": credits,
                "balanceRemaining": agent_request["balance"]["balance"] - credits,
            },
        }

    wrapped = mcp.with_paywall(
        business_logic_handler, {"kind": "tool", "name": "business", "credits": 3}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(
        wrapped({"action": "test"}, extra)
    )

    # Verify handler used context data correctly
    assert "error" not in out
    assert out["content"][0]["text"] == "Success"
    assert out["metadata"]["agentName"] == "Test Agent"
    assert out["metadata"]["requestId"] == "req-123"
    assert out["metadata"]["creditsUsed"] == 3
    assert out["metadata"]["balanceRemaining"] == 997  # 1000 - 3
