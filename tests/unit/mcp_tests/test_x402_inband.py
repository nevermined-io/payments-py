"""
Unit tests for the x402 v2 in-band MCP transport (issue #203).

Covers:
- the spec-shaped payment-required tool result (structuredContent + content[0].text),
- the access-token <-> PaymentPayload round-trip used to carry the payment in
  ``_meta["x402/payment"]``,
- reading the in-band payload from request ``_meta``,
- the happy-path settlement receipt under ``_meta["x402/payment-response"]`` plus
  the Nevermined observability under ``_meta["nevermined/credits"]``,
- settlement-failure-after-execution suppressing tool content and surfacing the
  payment error.
"""

import base64
import json

import pytest
from unittest.mock import AsyncMock, MagicMock

from payments_py.x402.token import decode_access_token, encode_access_token
from payments_py.mcp import build_mcp_integration
from payments_py.mcp.utils.meta import (
    X402_PAYMENT_META_KEY,
    X402_PAYMENT_RESPONSE_META_KEY,
    NEVERMINED_CREDITS_META_KEY,
    payment_required_result,
    read_payment_payload,
)
from payments_py.mcp.utils.errors import PaymentRequiredError, SettlementFailedError
from payments_py.mcp.core.auth import PaywallAuthenticator
from payments_py.mcp.core.paywall import PaywallDecorator
from payments_py.mcp.core.server_manager import (
    McpServerManager,
    _get_mcp_server_class,
)

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------

SAMPLE_PAYLOAD = {
    "x402Version": 2,
    "accepted": {
        "scheme": "nvm:erc4337",
        "network": "eip155:84532",
        "planId": "plan-123",
        "extra": {"agentId": "agent-9"},
    },
    "payload": {
        "signature": "0xdeadbeef",
        "authorization": {"from": "0xabc", "to": "0xdef", "value": "1"},
    },
}


class _FakeSettlement:
    """Mimics the facilitator settlement model (pydantic-like)."""

    def __init__(self, success=True, transaction="0xabc", credits_redeemed="5"):
        self.success = success
        self.transaction = transaction
        self.credits_redeemed = credits_redeemed

    def model_dump(self, by_alias=False):
        return {
            "success": self.success,
            "transaction": self.transaction,
            "network": "eip155:84532",
            "payer": "0x123",
        }


class _FakeRequestContext:
    def __init__(self, meta):
        self.meta = meta


class _FakeServer:
    """Minimal stand-in for the low-level MCP Server."""

    def __init__(self, meta, raise_lookup=False):
        self._meta = meta
        self._raise_lookup = raise_lookup

    @property
    def request_context(self):
        if self._raise_lookup:
            raise LookupError("no active request context")
        return _FakeRequestContext(self._meta)


def _meta_with(extra: dict):
    """Build a real RequestParams.Meta carrying arbitrary _meta keys."""
    from mcp.types import RequestParams

    return RequestParams.Meta.model_validate(extra)


def _make_decorator(settlement):
    """Build a PaywallDecorator wired with mocks for a single tool call."""
    payments = MagicMock()
    payments.environment_name = "staging_sandbox"
    payments.facilitator.settle_permissions = MagicMock(return_value=settlement)

    authenticator = MagicMock()
    authenticator.authenticate = AsyncMock(
        return_value={
            "token": "tok-abc",
            "agent_id": "agent-9",
            "logical_url": "mcp://srv/tools/premium",
            "http_url": None,
            "plan_id": "plan-123",
            "subscriber_address": "0x123",
        }
    )

    credits_context = MagicMock()
    credits_context.resolve = MagicMock(return_value=5)

    decorator = PaywallDecorator(payments, authenticator, credits_context)
    decorator.configure({"agentId": "agent-9", "serverName": "srv"})
    return decorator


# ---------------------------------------------------------------------------
# (i) payment_required_result shape
# ---------------------------------------------------------------------------


class TestPaymentRequiredResult:
    def test_is_error_with_dual_representation(self):
        payment_required = {
            "x402Version": 2,
            "error": "payment required",
            "resource": {"url": "mcp://srv/tools/premium"},
            "accepts": [{"scheme": "nvm:erc4337", "planId": "plan-123"}],
        }

        result = payment_required_result(payment_required)

        assert result.isError is True
        # structuredContent carries the object verbatim.
        assert result.structuredContent == payment_required
        assert result.structuredContent["x402Version"] == 2
        assert len(result.structuredContent["accepts"]) >= 1
        # content[0].text is the JSON-stringified copy.
        assert result.content[0].type == "text"
        assert json.loads(result.content[0].text) == payment_required


# ---------------------------------------------------------------------------
# (ii) token <-> payload round-trip
# ---------------------------------------------------------------------------


class TestAccessTokenRoundTrip:
    def test_encode_decode_round_trip(self):
        token = encode_access_token(SAMPLE_PAYLOAD)
        assert decode_access_token(token) == SAMPLE_PAYLOAD

    def test_decode_recovers_foreign_encoded_token(self):
        # The property that actually matters: a token the BACKEND produced with a
        # different JSON serialization (different key order / whitespace than our
        # compact encoder) must still decode to the same payload, and re-encoding
        # it for the facilitator must preserve the payload object. (Byte-identity
        # of our own output is not the invariant; semantic recovery is.)
        foreign = (
            base64.urlsafe_b64encode(
                json.dumps(SAMPLE_PAYLOAD, indent=2, sort_keys=True).encode()
            )
            .decode()
            .rstrip("=")
        )
        assert foreign != encode_access_token(
            SAMPLE_PAYLOAD
        )  # genuinely different bytes
        assert decode_access_token(foreign) == SAMPLE_PAYLOAD
        assert (
            decode_access_token(encode_access_token(decode_access_token(foreign)))
            == SAMPLE_PAYLOAD
        )


# ---------------------------------------------------------------------------
# (iii) read_payment_payload
# ---------------------------------------------------------------------------


class TestReadPaymentPayload:
    def test_reads_inband_payload(self):
        meta = _meta_with({X402_PAYMENT_META_KEY: SAMPLE_PAYLOAD})
        server = _FakeServer(meta)
        assert read_payment_payload(server) == SAMPLE_PAYLOAD

    def test_returns_none_when_absent(self):
        meta = _meta_with({"progressToken": "abc"})
        server = _FakeServer(meta)
        assert read_payment_payload(server) is None

    def test_returns_none_when_no_meta(self):
        assert read_payment_payload(_FakeServer(None)) is None

    def test_returns_none_outside_request_context(self):
        assert read_payment_payload(_FakeServer(None, raise_lookup=True)) is None

    def test_returns_none_when_payload_not_a_dict(self):
        # A malformed in-band payload (string/list instead of an object) is
        # ignored rather than crashing the dispatcher.
        meta = _meta_with({X402_PAYMENT_META_KEY: "not-a-dict"})
        assert read_payment_payload(_FakeServer(meta)) is None


# ---------------------------------------------------------------------------
# (iv) happy-path settlement receipt
# ---------------------------------------------------------------------------


class TestPaywallSettlementReceipt:
    @pytest.mark.asyncio
    async def test_attaches_spec_and_nevermined_meta(self):
        decorator = _make_decorator(_FakeSettlement(success=True))

        def handler(args, extra, ctx):
            return {"content": [{"type": "text", "text": "ok"}]}

        protected = decorator.protect(handler, {"name": "premium", "kind": "tool"})
        result = await protected({"q": "x"}, {"requestInfo": {"headers": {}}})

        meta = result["_meta"]
        # Spec settlement receipt.
        assert meta[X402_PAYMENT_RESPONSE_META_KEY]["success"] is True
        assert meta[X402_PAYMENT_RESPONSE_META_KEY]["transaction"] == "0xabc"
        # Nevermined-namespaced observability.
        assert meta[NEVERMINED_CREDITS_META_KEY]["success"] is True
        assert meta[NEVERMINED_CREDITS_META_KEY]["creditsRedeemed"] == "5"
        assert meta[NEVERMINED_CREDITS_META_KEY]["planId"] == "plan-123"
        # The tool content is preserved on success.
        assert result["content"][0]["text"] == "ok"


# ---------------------------------------------------------------------------
# (v) settlement failure after execution
# ---------------------------------------------------------------------------


class TestSettlementFailureSuppressesContent:
    @pytest.mark.asyncio
    async def test_raises_settlement_failed_and_dispatch_suppresses_content(self):
        decorator = _make_decorator(_FakeSettlement(success=False))

        def handler(args, extra, ctx):
            return {"content": [{"type": "text", "text": "secret-paid-result"}]}

        protected = decorator.protect(handler, {"name": "premium", "kind": "tool"})

        with pytest.raises(SettlementFailedError) as exc_info:
            await protected({"q": "x"}, {"requestInfo": {"headers": {}}})

        # SettlementFailedError is a PaymentRequiredError carrying PaymentRequired.
        err = exc_info.value
        assert isinstance(err, PaymentRequiredError)
        assert err.payment_required["x402Version"] == 2
        assert err.payment_required["error"] == "settlement failed"
        # The PaymentRequired reflects the authenticated plan and resource.
        assert err.payment_required["accepts"][0]["planId"] == "plan-123"
        assert err.payment_required["resource"]["url"] == "mcp://srv/tools/premium"

        # The tool dispatcher converts it into an error tool result that does
        # NOT contain the executed tool's content.
        result = payment_required_result(err.payment_required)
        assert result.isError is True
        assert result.structuredContent["x402Version"] == 2
        serialized = json.dumps([c.model_dump() for c in result.content]) + json.dumps(
            result.structuredContent
        )
        assert "secret-paid-result" not in serialized


# ---------------------------------------------------------------------------
# (vi) auth-side PaymentRequired with real `accepts` from agent plans
# ---------------------------------------------------------------------------


class TestAuthBuildsPaymentRequired:
    @pytest.mark.asyncio
    async def test_missing_header_payment_required_lists_plans(self):
        payments = MagicMock()
        payments.environment_name = "staging_sandbox"
        payments.agents.get_agent_plans = MagicMock(
            return_value={
                "plans": [
                    {"planId": "plan-123", "metadata": {"main": {"name": "Basic"}}},
                    {"planId": "plan-456", "metadata": {"main": {"name": "Pro"}}},
                ]
            }
        )
        auth = PaywallAuthenticator(payments)

        with pytest.raises(PaymentRequiredError) as exc_info:
            await auth.authenticate(
                {"requestInfo": {"headers": {}}},
                {},
                "agent-9",
                "srv",
                "premium",
                "tool",
                {},
            )

        pr = exc_info.value.payment_required
        plan_ids = [a.get("planId") for a in pr["accepts"]]
        assert "plan-123" in plan_ids and "plan-456" in plan_ids
        assert "Basic" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_plan_lookup_error_still_valid_and_logged(self, caplog):
        payments = MagicMock()
        payments.environment_name = "staging_sandbox"
        payments.agents.get_agent_plans = MagicMock(
            side_effect=RuntimeError("backend 500")
        )
        auth = PaywallAuthenticator(payments)

        with caplog.at_level("ERROR"):
            with pytest.raises(PaymentRequiredError) as exc_info:
                await auth.authenticate(
                    {"requestInfo": {"headers": {}}},
                    {},
                    "agent-9",
                    "srv",
                    "premium",
                    "tool",
                    {},
                )

        # Still a structurally-valid PaymentRequired, AND the swallowed backend
        # failure is logged (not silently masked as "user hasn't paid").
        assert exc_info.value.payment_required["x402Version"] == 2
        assert "Failed to fetch agent plans" in caplog.text
        # A backend outage is surfaced as "plans unavailable", NOT a clean 402,
        # so the empty accepts list isn't read by the client as "free".
        assert exc_info.value.payment_required["error"] == "plans unavailable"


# ---------------------------------------------------------------------------
# (vii) free / no-credit path skips the spec settlement receipt
# ---------------------------------------------------------------------------


class TestFreeCallNoReceipt:
    @pytest.mark.asyncio
    async def test_no_settlement_receipt_for_free_call(self):
        decorator = _make_decorator(_FakeSettlement(success=True))
        # Zero credits → no settlement happens.
        decorator._credits.resolve = MagicMock(return_value=0)

        def handler(args, extra, ctx):
            return {"content": [{"type": "text", "text": "free"}]}

        protected = decorator.protect(handler, {"name": "premium", "kind": "tool"})
        result = await protected({"q": "x"}, {"requestInfo": {"headers": {}}})

        meta = result["_meta"]
        assert X402_PAYMENT_RESPONSE_META_KEY not in meta
        assert meta[NEVERMINED_CREDITS_META_KEY]["success"] is True
        assert result["content"][0]["text"] == "free"


# ---------------------------------------------------------------------------
# (viii) the REAL dispatcher wiring (McpServerManager.call_tool)
# ---------------------------------------------------------------------------


class _DispatchVerifyResult:
    def __init__(self, is_valid=True):
        self.is_valid = is_valid
        self.agent_request = None
        self.agent_request_id = None


def _make_dispatch_payments(settlement):
    payments = MagicMock()
    payments.environment_name = "staging_sandbox"
    payments.facilitator.verify_permissions = MagicMock(
        return_value=_DispatchVerifyResult(True)
    )
    payments.facilitator.settle_permissions = MagicMock(return_value=settlement)
    payments.agents.get_agent_plans = MagicMock(
        return_value={"plans": [{"planId": "plan-123"}]}
    )
    payments.mcp = build_mcp_integration(payments)
    return payments


async def _build_dispatch_manager(payments, *, on_log=None, on_redeem_error="ignore"):
    """Build a real ``McpServerManager`` with one registered tool and the real
    ``call_tool`` dispatcher wired up (without binding an HTTP port)."""
    recorded = {}

    async def tool_handler(args, extra=None, ctx=None):
        recorded["extra"] = extra
        return {"content": [{"type": "text", "text": "secret-paid-result"}]}

    manager = McpServerManager(payments)
    manager._config = {"agentId": "agent-9", "serverName": "srv"}
    manager._log = on_log
    manager.register_tool(
        "premium",
        {"description": "x", "inputSchema": {"type": "object"}},
        tool_handler,
        {"credits": 5, "onRedeemError": on_redeem_error},
    )
    server_class = await _get_mcp_server_class()
    manager._mcp_server = server_class(name="srv", version="1.0.0")
    await manager._register_handlers_with_paywall()
    return manager, recorded


async def _invoke_call_tool(manager, *, inband_payload=None, session_headers=None):
    from mcp.types import CallToolRequest
    from mcp.shared.context import RequestContext
    from mcp.server.lowlevel.server import request_ctx

    if session_headers is not None:
        sm = MagicMock()
        sm.get_current_request_context = MagicMock(
            return_value={"headers": session_headers}
        )
        manager._session_manager = sm

    meta = (
        _meta_with({X402_PAYMENT_META_KEY: inband_payload}) if inband_payload else None
    )
    ctx_token = request_ctx.set(
        RequestContext(
            request_id=1,
            meta=meta,
            session=MagicMock(),
            lifespan_context=None,
        )
    )
    try:
        handler = manager._mcp_server.request_handlers[CallToolRequest]
        req = CallToolRequest(
            method="tools/call", params={"name": "premium", "arguments": {}}
        )
        server_result = await handler(req)
    finally:
        request_ctx.reset(ctx_token)
    return server_result.root  # CallToolResult


class TestDispatcherInBand:
    @pytest.mark.asyncio
    async def test_inband_payload_reencoded_to_bearer(self):
        payments = _make_dispatch_payments(_FakeSettlement(success=True))
        manager, recorded = await _build_dispatch_manager(payments)

        result = await _invoke_call_tool(manager, inband_payload=SAMPLE_PAYLOAD)

        # The handler received the in-band payload re-encoded as a Bearer token.
        expected = "Bearer " + encode_access_token(SAMPLE_PAYLOAD)
        assert recorded["extra"]["requestInfo"]["headers"]["authorization"] == expected
        assert not result.isError

    @pytest.mark.asyncio
    async def test_payment_required_converted_to_error_result(self):
        payments = _make_dispatch_payments(_FakeSettlement(success=False))
        manager, _ = await _build_dispatch_manager(payments)

        result = await _invoke_call_tool(manager, inband_payload=SAMPLE_PAYLOAD)

        # SettlementFailedError → spec-shaped error tool result, no paid content.
        assert result.isError is True
        assert result.structuredContent["x402Version"] == 2
        blob = json.dumps([c.model_dump() for c in result.content]) + json.dumps(
            result.structuredContent
        )
        assert "secret-paid-result" not in blob

    @pytest.mark.asyncio
    async def test_header_fallback_when_no_inband_payload(self):
        logs = []
        payments = _make_dispatch_payments(_FakeSettlement(success=True))
        manager, recorded = await _build_dispatch_manager(payments, on_log=logs.append)

        token = encode_access_token(SAMPLE_PAYLOAD)
        result = await _invoke_call_tool(
            manager, session_headers={"authorization": f"Bearer {token}"}
        )

        # No in-band payload → the deprecated Authorization-header path is used,
        # and a deprecation notice is logged.
        assert (
            recorded["extra"]["requestInfo"]["headers"]["authorization"]
            == f"Bearer {token}"
        )
        assert any("deprecated" in m.lower() for m in logs)
        assert not result.isError


# ---------------------------------------------------------------------------
# (ix) onRedeemError "propagate" raises Misconfiguration
# ---------------------------------------------------------------------------


class TestOnRedeemErrorPropagate:
    @pytest.mark.asyncio
    async def test_propagate_raises_misconfiguration(self):
        from payments_py.mcp.utils.errors import ERROR_CODES

        decorator = _make_decorator(None)
        # settle_permissions throws → with onRedeemError "propagate" the paywall
        # raises a JSON-RPC Misconfiguration (-32002) rather than suppressing.
        decorator._payments.facilitator.settle_permissions = MagicMock(
            side_effect=RuntimeError("settle boom")
        )

        def handler(args, extra, ctx):
            return {"content": [{"type": "text", "text": "ok"}]}

        protected = decorator.protect(
            handler,
            {"name": "premium", "kind": "tool", "onRedeemError": "propagate"},
        )

        with pytest.raises(Exception) as exc_info:
            await protected({"q": "x"}, {"requestInfo": {"headers": {}}})

        assert getattr(exc_info.value, "code", None) == ERROR_CODES["Misconfiguration"]
