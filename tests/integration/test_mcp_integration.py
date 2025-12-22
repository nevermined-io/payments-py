import asyncio
from unittest.mock import patch

from payments_py.mcp import build_mcp_integration

# Mock decode_access_token for tests
mock_decode_token = lambda token: {"planId": "plan-123", "subscriberAddress": "0xSubscriber123"}


class PaymentsMinimal:
    def __init__(self, subscriber=True):
        class Facilitator:
            def __init__(self, outer, subscriber):
                self._outer = outer
                self._subscriber = subscriber

            def verify_permissions(
                self, plan_id, max_amount, x402_access_token, subscriber_address
            ):
                if not self._subscriber:
                    raise Exception("Not a subscriber")
                return {"success": True}

            def settle_permissions(
                self, plan_id, max_amount, x402_access_token, subscriber_address
            ):
                return {
                    "success": True,
                    "txHash": "0x123",
                    "data": {"creditsBurned": max_amount},
                }

        class Agents:
            def get_agent_plans(self, agent_id):
                return {"plans": []}

        self.facilitator = Facilitator(self, subscriber)
        self.agents = Agents()


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
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


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
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


@patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_token)
def test_context_integration_with_real_like_data():
    """Test PaywallContext with x402 context data."""

    class PaymentsWithX402:
        def __init__(self, subscriber=True):
            class Facilitator:
                def __init__(self, outer, subscriber):
                    self._outer = outer
                    self._subscriber = subscriber

                def verify_permissions(
                    self, plan_id, max_amount, x402_access_token, subscriber_address
                ):
                    if not self._subscriber:
                        raise Exception("Not a subscriber")
                    return {"success": True}

                def settle_permissions(
                    self, plan_id, max_amount, x402_access_token, subscriber_address
                ):
                    return {
                        "success": True,
                        "txHash": f"0x{hash(f'{plan_id}-{max_amount}') % 1000000000:x}",
                        "data": {"creditsBurned": max_amount},
                    }

            class Agents:
                def get_agent_plans(self, agent_id):
                    return {
                        "plans": [
                            {"id": "plan-1", "name": "Basic Plan"},
                            {"id": "plan-2", "name": "Premium Plan"},
                        ]
                    }

            self.facilitator = Facilitator(self, subscriber)
            self.agents = Agents()

    payments = PaymentsWithX402(subscriber=True)
    mcp = build_mcp_integration(payments)
    mcp.configure({"agentId": "did:nv:agent:abc123", "serverName": "weather-service"})

    captured_contexts = []

    async def weather_handler(args, extra=None, context=None):
        captured_contexts.append(context)

        if not context:
            return {"error": "No context provided"}

        auth_result = context["auth_result"]
        credits = context["credits"]

        # Simulate business logic using context data
        city = args.get("city", "Unknown")

        # Generate weather response with metadata
        weather_data = {
            "city": city,
            "temperature": 22,
            "condition": "sunny",
            "humidity": 65,
        }

        return {
            "content": [
                {
                    "type": "text",
                    "text": f"Weather in {city}: {weather_data['temperature']}°C, {weather_data['condition']}",
                }
            ],
            "metadata": {
                "agentId": auth_result["agentId"],
                "planId": context.get("plan_id"),
                "subscriberAddress": context.get("subscriber_address"),
                "creditsUsed": credits,
                "weatherData": weather_data,
            },
        }

    wrapped = mcp.with_paywall(
        weather_handler, {"kind": "tool", "name": "get-weather", "credits": 5}
    )

    extra = {"requestInfo": {"headers": {"authorization": "Bearer weather-token-123"}}}
    result = asyncio.run(wrapped({"city": "Madrid"}, extra))

    # Verify the handler executed successfully
    assert "error" not in result
    assert "Weather in Madrid: 22°C, sunny" in result["content"][0]["text"]

    # Verify context was captured
    assert len(captured_contexts) == 1
    context = captured_contexts[0]

    # Verify x402 PaywallContext structure
    assert context["auth_result"]["token"] == "weather-token-123"
    assert context["auth_result"]["agentId"] == "did:nv:agent:abc123"
    assert (
        "mcp://weather-service/tools/get-weather"
        in context["auth_result"]["logicalUrl"]
    )

    # Verify x402 specific data
    assert context["plan_id"] == "plan-123"  # From mocked decode_access_token
    assert (
        context["subscriber_address"] == "0xSubscriber123"
    )  # From mocked decode_access_token

    # Verify credits
    assert context["credits"] == 5

    # Verify metadata in result
    assert result["metadata"]["agentId"] == "did:nv:agent:abc123"
    assert result["metadata"]["planId"] == "plan-123"
    assert result["metadata"]["subscriberAddress"] == "0xSubscriber123"
    assert result["metadata"]["creditsUsed"] == 5
