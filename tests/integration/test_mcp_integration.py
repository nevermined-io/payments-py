import asyncio

from payments_py.mcp import build_mcp_integration


class PaymentsMinimal:
    def __init__(self, subscriber=True):
        class Req:
            def __init__(self, outer, subscriber):
                self._outer = outer
                self._subscriber = subscriber

            def start_processing_request(self, agent_id, token, url, method):
                return {
                    "agentRequestId": "req-xyz",
                    "balance": {"isSubscriber": self._subscriber},
                }

            def redeem_credits_from_request(self, request_id, token, credits):
                return {"success": True}

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.requests = Req(self, subscriber)
        self.agents = Agents()


def test_validates_and_burns_with_minimal_mocks():
    payments = PaymentsMinimal()
    mcp = build_mcp_integration(payments)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "mcp-int"})

    async def handler(_args):
        return {"content": [{"type": "text", "text": "hello"}]}

    wrapped = mcp.with_paywall(handler, {"kind": "tool", "name": "test", "credits": 1})
    extra = {"requestInfo": {"headers": {"Authorization": "Bearer abc"}}}
    out = asyncio.run(wrapped({"city": "Madrid"}, extra))
    assert out


def test_integration_edge_not_subscriber_triggers_payment_required():
    payments = PaymentsMinimal(subscriber=False)
    mcp = build_mcp_integration(payments)
    mcp.configure({"agentId": "did:nv:agent", "serverName": "mcp-int"})

    async def handler(_args):
        return {"content": [{"type": "text", "text": "hello"}]}

    wrapped = mcp.with_paywall(handler, {"kind": "tool", "name": "test", "credits": 1})

    async def _run():
        try:
            await wrapped(
                {"city": "Madrid"},
                {"requestInfo": {"headers": {"Authorization": "Bearer tok"}}},
            )
            return None
        except Exception as e:
            return e

    err = asyncio.run(_run())
    assert getattr(err, "code", 0) == -32003
