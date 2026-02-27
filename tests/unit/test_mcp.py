import asyncio
from unittest.mock import patch
import pytest

from payments_py.mcp import build_mcp_integration


# Mock the decode_access_token to return x402-compliant token structure
def mock_decode_token(token):
    return {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "plan123",
            "extra": {"version": "1"},
        },
        "payload": {
            "signature": "0x123",
            "authorization": {
                "from": "0x123subscriber",
                "sessionKeysProvider": "zerodev",
                "sessionKeys": [],
            },
        },
        "extensions": {},
    }


class VerifyResult:
    """Mock verify permissions result with is_valid attribute."""

    def __init__(self, is_valid=True):
        self.is_valid = is_valid


class SettleResult:
    """Mock settle permissions result."""

    def __init__(self, success=True, transaction=None, credits_redeemed="1"):
        self.success = success
        self.transaction = transaction
        self.credits_redeemed = credits_redeemed


def make_settle_result(settle_result):
    """Convert dict to SettleResult if needed."""
    if settle_result is None:
        return SettleResult()
    if isinstance(settle_result, SettleResult):
        return settle_result
    # Handle dict input
    return SettleResult(
        success=settle_result.get("success", True),
        transaction=settle_result.get("txHash"),
        credits_redeemed=settle_result.get("data", {}).get("creditsBurned", "1"),
    )


class PaymentsMock:
    def __init__(self, settle_result=None):
        class Facilitator:
            def __init__(self, parent, settle_result):
                self._parent = parent
                self._settle_result = make_settle_result(settle_result)

            def verify_permissions(
                self, payment_required=None, max_amount=None, x402_access_token=None
            ):
                # Extract plan_id from Pydantic model or dict
                plan_id = None
                if payment_required:
                    if hasattr(payment_required, "accepts"):
                        # Pydantic model
                        accepts = payment_required.accepts
                        if accepts and len(accepts) > 0:
                            plan_id = accepts[0].plan_id
                    elif isinstance(payment_required, dict):
                        plan_id = payment_required.get("accepts", [{}])[0].get("planId")
                self._parent.calls.append(("verify", plan_id, x402_access_token))
                return VerifyResult(is_valid=True)

            def settle_permissions(
                self, payment_required=None, max_amount=None, x402_access_token=None, agent_request_id=None
            ):
                # Extract plan_id from Pydantic model or dict
                plan_id = None
                if payment_required:
                    if hasattr(payment_required, "accepts"):
                        # Pydantic model
                        accepts = payment_required.accepts
                        if accepts and len(accepts) > 0:
                            plan_id = accepts[0].plan_id
                    elif isinstance(payment_required, dict):
                        plan_id = payment_required.get("accepts", [{}])[0].get("planId")
                self._parent.calls.append(
                    ("settle", plan_id, x402_access_token, int(max_amount))
                )
                return self._settle_result

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.facilitator = Facilitator(self, settle_result)
        self.agents = Agents()
        self.calls = []


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_burns_fixed_credits_after_successful_call():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": 2, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))
    assert out
    assert ("verify", "plan123", "token") in pm.calls
    assert ("settle", "plan123", "token", 2) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_adds_metadata_to_result_after_successful_redemption():
    """Test that metadata is added to the result after successful credit redemption."""
    settle_result = {"success": True, "data": {"creditsBurned": "3"}}
    pm = PaymentsMock(settle_result=settle_result)
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": 3, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify the result has _meta
    assert "_meta" in out
    assert out["_meta"] is not None
    assert isinstance(out["_meta"], dict)

    # Verify _meta contains expected fields
    assert out["_meta"].get("success") is True
    assert out["_meta"].get("creditsRedeemed") == "3"
    # txHash should be None since our mock doesn't return it
    assert out["_meta"].get("txHash") is None


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_adds_metadata_with_txhash_when_settle_returns_it():
    """Test that metadata includes txHash when settle_permissions returns it."""
    settle_result = {
        "success": True,
        "txHash": "0x1234567890abcdef",
        "data": {"creditsBurned": "5"},
    }
    pm = PaymentsMock(settle_result=settle_result)
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": 5, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify the result has _meta
    assert "_meta" in out
    assert out["_meta"] is not None
    assert isinstance(out["_meta"], dict)

    # Verify _meta contains expected fields including txHash
    assert out["_meta"].get("success") is True
    assert out["_meta"].get("creditsRedeemed") == "5"
    assert out["_meta"].get("txHash") == "0x1234567890abcdef"


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_adds_metadata_with_failure_info_when_settlement_fails():
    """Test that metadata reports failure when credit settlement fails."""
    settle_result = {"success": False, "error": "Insufficient credits"}
    pm = PaymentsMock(settle_result=settle_result)
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": 2, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify _meta is present with failure info
    assert "_meta" in out
    assert out["_meta"] is not None
    assert out["_meta"]["success"] is False
    assert out["_meta"]["creditsRedeemed"] == "0"
    assert out["_meta"]["planId"] == "plan123"


def test_rejects_when_authorization_header_missing():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex"})

    async def base(_args, _extra=None):
        return {}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    with pytest.raises(Exception) as err:
        asyncio.get_event_loop().run_until_complete(
            wrapped({}, {"requestInfo": {"headers": {}}})
        )
    assert getattr(err.value, "code", 0) == -32003


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_burns_dynamic_credits_from_function():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        base,
        {
            "kind": "tool",
            "name": "test",
            "credits": lambda _ctx: 7,
            "planId": "plan123",
        },
    )
    asyncio.get_event_loop().run_until_complete(
        wrapped({}, {"requestInfo": {"headers": {"authorization": "Bearer TT"}}})
    )
    assert ("settle", "plan123", "TT", 7) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_defaults_to_one_credit_when_undefined():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"res": True}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "test", "planId": "plan123"}
    )
    asyncio.get_event_loop().run_until_complete(
        wrapped({}, {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}})
    )
    assert ("settle", "plan123", "tok", 1) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_does_not_settle_when_zero_credits():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"res": True}

    wrapped = mcp.with_paywall(
        base,
        {
            "kind": "tool",
            "name": "test",
            "credits": lambda _ctx: 0,
            "planId": "plan123",
        },
    )
    asyncio.get_event_loop().run_until_complete(
        wrapped({}, {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}})
    )
    assert not any(c[0] == "settle" for c in pm.calls)


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_propagates_error_on_settle_when_configured():
    class P(PaymentsMock):
        def __init__(self):
            super().__init__()

            class F:
                def __init__(self, parent):
                    self._parent = parent

                def verify_permissions(
                    self, payment_required=None, max_amount=None, x402_access_token=None
                ):
                    return VerifyResult(is_valid=True)

                def settle_permissions(
                    self, payment_required=None, max_amount=None, x402_access_token=None, agent_request_id=None
                ):
                    raise RuntimeError("settle failed")

            self.facilitator = F(self)

    pm = P()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "srv"})

    async def base(_args, _extra=None):
        return {"ok": True}

    wrapped = mcp.with_paywall(
        base,
        {
            "kind": "tool",
            "name": "test",
            "credits": 1,
            "onRedeemError": "propagate",
            "planId": "plan123",
        },
    )
    with pytest.raises(Exception) as err:
        asyncio.get_event_loop().run_until_complete(
            wrapped({}, {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}})
        )
    assert getattr(err.value, "code", 0) == -32002


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_attach_register_resource_wraps_and_burns():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "srv"})

    captured = {}

    class Server:
        def register_resource(self, name, template, config, handler):
            captured["wrapped"] = handler

        def register_tool(self, name, config, handler):
            captured["tool"] = handler

        def register_prompt(self, name, config, handler):
            captured["prompt"] = handler

    api = mcp.attach(Server())

    async def handler(_uri, _vars, _extra=None):
        return {
            "contents": [
                {"uri": "mcp://srv/res", "mimeType": "application/json", "text": "{}"}
            ]
        }

    api.register_resource(
        "res.test",
        {"tpl": True},
        {"cfg": True},
        handler,
        {"credits": 3, "planId": "plan123"},
    )
    wrapped = captured["wrapped"]
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped(object(), {"a": "1"}, extra))
    assert ("settle", "plan123", "token", 3) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
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
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "mcp"})

    async def base(_args, _extra=None):
        return {"ok": True}

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "hdr", "credits": 1, "planId": "plan123"}
    )
    for i, variant in enumerate(variants):
        pm.calls.clear()
        asyncio.get_event_loop().run_until_complete(wrapped({}, variant))
        assert ("settle", "plan123", tokens[i], 1) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_settles_after_async_iterable_completes():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "mcp"})

    async def make_iterable(chunks):
        async def gen():
            for c in chunks:
                await asyncio.sleep(0)
                yield c

        return gen()

    async def base(_args, _extra=None):
        return await make_iterable(["one", "two", "three"])

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "stream", "credits": 5, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer tok"}}}
    iterable = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))
    # Not settled yet
    assert not any(c[0] == "settle" for c in pm.calls)
    collected = []

    async def consume():
        async for chunk in iterable:
            collected.append(chunk)

    asyncio.get_event_loop().run_until_complete(consume())
    assert collected == ["one", "two", "three"]
    assert ("settle", "plan123", "tok", 5) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_settles_when_consumer_stops_stream_early():
    pm = PaymentsMock()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "mcp"})

    async def make_iterable(chunks):
        async def gen():
            for c in chunks:
                await asyncio.sleep(0)
                yield c

        return gen()

    async def base(_args, _extra=None):
        return await make_iterable(["one", "two", "three"])

    wrapped = mcp.with_paywall(
        base, {"kind": "tool", "name": "stream", "credits": 2, "planId": "plan123"}
    )
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
    assert ("settle", "plan123", "tok", 2) in pm.calls


class PaymentsMockWithX402Context:
    """Mock that includes x402 context (plan_id, subscriber_address) in responses."""

    def __init__(self, settle_result=None):
        class Facilitator:
            def __init__(self, parent, settle_result):
                self._parent = parent
                self._settle_result = make_settle_result(settle_result)

            def verify_permissions(
                self, payment_required=None, max_amount=None, x402_access_token=None
            ):
                plan_id = None
                if payment_required:
                    if hasattr(payment_required, "accepts"):
                        accepts = payment_required.accepts
                        if accepts and len(accepts) > 0:
                            plan_id = accepts[0].plan_id
                    elif isinstance(payment_required, dict):
                        plan_id = payment_required.get("accepts", [{}])[0].get("planId")
                self._parent.calls.append(("verify", plan_id, x402_access_token))
                return VerifyResult(is_valid=True)

            def settle_permissions(
                self, payment_required=None, max_amount=None, x402_access_token=None, agent_request_id=None
            ):
                plan_id = None
                if payment_required:
                    if hasattr(payment_required, "accepts"):
                        accepts = payment_required.accepts
                        if accepts and len(accepts) > 0:
                            plan_id = accepts[0].plan_id
                    elif isinstance(payment_required, dict):
                        plan_id = payment_required.get("accepts", [{}])[0].get("planId")
                self._parent.calls.append(
                    ("settle", plan_id, x402_access_token, int(max_amount))
                )
                return self._settle_result

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.facilitator = Facilitator(self, settle_result)
        self.agents = Agents()
        self.calls = []


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_backward_compatibility_handlers_without_context():
    """Test that handlers without context parameter still work."""
    pm = PaymentsMockWithX402Context()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def old_handler(args, extra=None):
        return {
            "content": [{"type": "text", "text": f"Hello {args.get('name', 'World')}"}]
        }

    wrapped = mcp.with_paywall(
        old_handler, {"kind": "tool", "name": "test", "credits": 2, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({"name": "Alice"}, extra))

    assert out["content"][0]["text"] == "Hello Alice"
    assert ("verify", "plan123", "token") in pm.calls
    assert ("settle", "plan123", "token", 2) in pm.calls


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_handlers_with_context_receive_paywall_context():
    """Test that handlers with context parameter receive PaywallContext."""
    pm = PaymentsMockWithX402Context()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    captured_context = None

    async def new_handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {
            "content": [{"type": "text", "text": f"Hello {args.get('name', 'World')}"}]
        }

    wrapped = mcp.with_paywall(
        new_handler, {"kind": "tool", "name": "test", "credits": 3, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({"name": "Bob"}, extra))

    assert out["content"][0]["text"] == "Hello Bob"
    assert captured_context is not None
    assert isinstance(captured_context, dict)


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_paywall_context_structure():
    """Test that PaywallContext contains all expected fields for x402."""
    pm = PaymentsMockWithX402Context()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    captured_context = None

    async def context_handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        context_handler,
        {"kind": "tool", "name": "test", "credits": 5, "planId": "plan123"},
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify PaywallContext structure for x402
    assert captured_context is not None
    assert "auth_result" in captured_context
    assert "credits" in captured_context
    assert "plan_id" in captured_context
    assert "subscriber_address" in captured_context

    # Verify auth_result structure for x402
    auth_result = captured_context["auth_result"]
    assert auth_result["token"] == "token"
    assert auth_result["agent_id"] == "unit_agent_id_hex"
    assert auth_result["logical_url"].startswith("mcp://test-mcp/tools/test")
    assert auth_result["plan_id"] == "plan123"
    assert auth_result["subscriber_address"] == "0x123subscriber"

    # Verify x402 specific fields in context
    assert captured_context["plan_id"] == "plan123"
    assert captured_context["subscriber_address"] == "0x123subscriber"

    # Verify credits
    assert captured_context["credits"] == 5


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_context_handlers_can_use_x402_context_data():
    """Test that handlers can access and use x402 context data."""
    pm = PaymentsMockWithX402Context()
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def business_logic_handler(args, extra=None, context=None):
        if not context:
            return {"error": "No context provided"}

        auth_result = context["auth_result"]
        credits = context["credits"]
        plan_id = context.get("plan_id")
        subscriber_address = context.get("subscriber_address")

        return {
            "content": [{"type": "text", "text": "Success"}],
            "metadata": {
                "plan_id": plan_id,
                "subscriber_address": subscriber_address,
                "creditsUsed": credits,
                "agent_id": auth_result["agent_id"],
            },
        }

    wrapped = mcp.with_paywall(
        business_logic_handler,
        {"kind": "tool", "name": "business", "credits": 3, "planId": "plan123"},
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(
        wrapped({"action": "test"}, extra)
    )

    # Verify handler used context data correctly
    assert "error" not in out
    assert out["content"][0]["text"] == "Success"
    assert out["metadata"]["plan_id"] == "plan123"
    assert out["metadata"]["subscriber_address"] == "0x123subscriber"
    assert out["metadata"]["creditsUsed"] == 3
    assert out["metadata"]["agent_id"] == "unit_agent_id_hex"


# --- Observability / agent_request propagation tests ---


MOCK_AGENT_REQUEST = {
    "agentRequestId": "arId-test-1234",
    "agentName": "test-mcp-server",
    "agentId": "agent-0x42",
    "balance": {
        "planId": "plan123",
        "planName": "Test Plan",
        "planType": "credits",
        "holderAddress": "0x123subscriber",
        "balance": 100,
        "creditsContract": "0xcredits",
        "isSubscriber": True,
        "pricePerCredit": 0.01,
    },
    "urlMatching": "mcp://test-mcp/tools/test",
    "verbMatching": "POST",
    "batch": False,
}


class VerifyResultWithAgentRequest:
    """Mock verify result that includes agent_request (as returned by the backend)."""

    def __init__(self, is_valid=True, agent_request=None, agent_request_id=None):
        self.is_valid = is_valid
        self.agent_request = agent_request
        self.agent_request_id = agent_request_id


class PaymentsMockWithAgentRequest:
    """Mock that returns agent_request from verify_permissions."""

    def __init__(self, agent_request=None, agent_request_id=None, settle_result=None):
        self._agent_request = agent_request
        self._agent_request_id = agent_request_id

        class Facilitator:
            def __init__(self, parent, settle_result):
                self._parent = parent
                self._settle_result = make_settle_result(settle_result)

            def verify_permissions(
                self, payment_required=None, max_amount=None, x402_access_token=None
            ):
                self._parent.calls.append(("verify", x402_access_token))
                return VerifyResultWithAgentRequest(
                    is_valid=True,
                    agent_request=self._parent._agent_request,
                    agent_request_id=self._parent._agent_request_id,
                )

            def settle_permissions(
                self, payment_required=None, max_amount=None, x402_access_token=None, agent_request_id=None
            ):
                self._parent.calls.append(("settle", x402_access_token, int(max_amount), agent_request_id))
                return self._settle_result

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.facilitator = Facilitator(self, settle_result)
        self.agents = Agents()
        self.calls = []


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_agent_request_propagated_to_paywall_context():
    """Test that agent_request from verify_permissions is included in PaywallContext."""
    pm = PaymentsMockWithAgentRequest(
        agent_request=MOCK_AGENT_REQUEST, agent_request_id="arId-test-1234"
    )
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    captured_context = None

    async def handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        handler, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    assert captured_context is not None
    assert "agent_request" in captured_context
    assert captured_context["agent_request"] == MOCK_AGENT_REQUEST
    assert captured_context["agent_request_id"] == "arId-test-1234"

    # Also propagated inside auth_result
    assert captured_context["auth_result"]["agent_request"] == MOCK_AGENT_REQUEST
    assert captured_context["auth_result"]["agent_request_id"] == "arId-test-1234"


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_agent_request_none_when_not_returned_by_verify():
    """Test backward compat: agent_request is None when verify doesn't return it."""
    pm = PaymentsMockWithAgentRequest(agent_request=None)
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    captured_context = None

    async def handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        handler, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    assert captured_context is not None
    assert captured_context.get("agent_request") is None
    assert captured_context.get("agent_request_id") is None


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_agent_request_id_passed_to_settle():
    """Test that agent_request_id is forwarded to settle_permissions."""
    pm = PaymentsMockWithAgentRequest(
        agent_request=MOCK_AGENT_REQUEST, agent_request_id="arId-test-1234"
    )
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def handler(args, extra=None, context=None):
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        handler, {"kind": "tool", "name": "test", "credits": 3, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    # Verify settle was called with the agent_request_id
    settle_calls = [c for c in pm.calls if c[0] == "settle"]
    assert len(settle_calls) == 1
    assert settle_calls[0] == ("settle", "token", 3, "arId-test-1234")


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_agent_request_can_be_parsed_as_start_agent_request():
    """Test that agent_request dict can be parsed into a StartAgentRequest model."""
    from payments_py.common.types import StartAgentRequest

    pm = PaymentsMockWithAgentRequest(
        agent_request=MOCK_AGENT_REQUEST, agent_request_id="arId-test-1234"
    )
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    captured_context = None

    async def handler(args, extra=None, context=None):
        nonlocal captured_context
        captured_context = context
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        handler, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    start_req = StartAgentRequest(**captured_context["agent_request"])

    assert start_req.agent_request_id == "arId-test-1234"
    assert start_req.agent_name == "test-mcp-server"
    assert start_req.agent_id == "agent-0x42"
    assert start_req.balance.plan_id == "plan123"
    assert start_req.balance.holder_address == "0x123subscriber"
    assert start_req.balance.price_per_credit == 0.01
    assert start_req.batch is False


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_agent_request_usable_with_observability_api():
    """Test full chain: verify → auth → paywall → handler → with_openai().

    Verifies that agent_request from the paywall can be used to create
    an observability-enabled OpenAI config, without real API keys.
    """
    from payments_py.common.types import StartAgentRequest
    from payments_py.api.observability_api import with_openai

    pm = PaymentsMockWithAgentRequest(
        agent_request=MOCK_AGENT_REQUEST, agent_request_id="arId-test-1234"
    )
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    oai_config_captured = None

    async def handler(args, extra=None, context=None):
        nonlocal oai_config_captured
        start_req = StartAgentRequest(**context["agent_request"])
        oai_config_captured = with_openai(
            api_key="sk-fake-key",
            helicone_api_key="hlk-fake-key",
            helicone_base_logging_url="https://helicone.test/jawn/v1/gateway/oai/v1",
            account_address="0xbuilder",
            environment_name="testing",
            start_agent_request=start_req,
            custom_properties={"tool": "test"},
        )
        return {"content": [{"type": "text", "text": "ok"}]}

    wrapped = mcp.with_paywall(
        handler, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    assert oai_config_captured is not None
    assert oai_config_captured.api_key == "sk-fake-key"
    assert oai_config_captured.base_url == "https://helicone.test/jawn/v1/gateway/oai/v1"

    headers = oai_config_captured.default_headers
    assert headers["Helicone-Auth"] == "Bearer hlk-fake-key"
    assert headers["Helicone-Property-consumerAddress"] == "0x123subscriber"
    assert headers["Helicone-Property-agentId"] == "agent-0x42"
    assert headers["Helicone-Property-planId"] == "plan123"
    assert headers["Helicone-Property-agentName"] == "test-mcp-server"
    assert headers["Helicone-Property-agentRequestId"] == "arId-test-1234"
    assert headers["Helicone-Property-pricePerCredit"] == "0.01"
    assert headers["Helicone-Property-tool"] == "test"


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_tool_handler_forwards_paywall_context_to_fn():
    """Test that the tool handler adapter forwards paywall_context to user functions that accept it."""
    pm = PaymentsMockWithAgentRequest(
        agent_request=MOCK_AGENT_REQUEST, agent_request_id="arId-test-1234"
    )
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    captured_ctx = None

    # Simulate what @mcp.tool does: create handler that unpacks args and forwards paywall_context
    import inspect
    import functools

    def my_tool(query: str, paywall_context=None) -> str:
        nonlocal captured_ctx
        captured_ctx = paywall_context
        return f"result: {query}"

    _fn_params = inspect.signature(my_tool).parameters
    _accepts_paywall_ctx = "paywall_context" in _fn_params

    @functools.wraps(my_tool)
    async def handler(args, context=None, paywall_context=None):
        call_args = dict(args)
        if _accepts_paywall_ctx and paywall_context is not None:
            call_args["paywall_context"] = paywall_context
        result = my_tool(**call_args)
        return {"content": [{"type": "text", "text": result}]}

    wrapped = mcp.with_paywall(
        handler, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({"query": "hello"}, extra))

    assert out["content"][0]["text"] == "result: hello"
    assert captured_ctx is not None
    assert captured_ctx["agent_request"] == MOCK_AGENT_REQUEST
    assert captured_ctx["agent_request_id"] == "arId-test-1234"


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_handlers_without_context_still_work_with_agent_request():
    """Test that old handlers ignoring context still work when agent_request is present."""
    pm = PaymentsMockWithAgentRequest(
        agent_request=MOCK_AGENT_REQUEST, agent_request_id="arId-test-1234"
    )
    mcp = build_mcp_integration(pm)
    mcp.configure({"agentId": "unit_agent_id_hex", "serverName": "test-mcp"})

    async def old_handler(args, extra=None):
        return {"content": [{"type": "text", "text": "old-style"}]}

    wrapped = mcp.with_paywall(
        old_handler, {"kind": "tool", "name": "test", "credits": 1, "planId": "plan123"}
    )
    extra = {"requestInfo": {"headers": {"authorization": "Bearer token"}}}
    out = asyncio.get_event_loop().run_until_complete(wrapped({}, extra))

    assert out["content"][0]["text"] == "old-style"
    assert ("verify", "token") in pm.calls
