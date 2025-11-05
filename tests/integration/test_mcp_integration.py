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


def test_context_integration_with_real_like_data():
    """Test PaywallContext with realistic agent request data."""

    class PaymentsWithAgentRequest:
        def __init__(self, subscriber=True, balance=1000):
            class Req:
                def __init__(self, outer, subscriber, balance):
                    self._outer = outer
                    self._subscriber = subscriber
                    self._balance = balance

                def start_processing_request(self, agent_id, token, url, method):
                    return {
                        "agentRequestId": f"req-{agent_id}-{hash(token) % 10000}",
                        "agentName": f"Agent {agent_id.split(':')[-1]}",
                        "agentId": agent_id,
                        "balance": {
                            "balance": self._balance,
                            "creditsContract": "0x1234567890abcdef",
                            "isSubscriber": self._subscriber,
                            "pricePerCredit": 0.01,
                        },
                        "urlMatching": url,
                        "verbMatching": method,
                        "batch": False,
                    }

                def redeem_credits_from_request(self, request_id, token, credits):
                    return {
                        "success": True,
                        "txHash": f"0x{hash(f'{request_id}-{token}-{credits}') % 1000000000:x}",
                    }

            class Agents:
                def get_agent_plans(self, agent_id):
                    return {
                        "plans": [
                            {"id": "plan-1", "name": "Basic Plan"},
                            {"id": "plan-2", "name": "Premium Plan"},
                        ]
                    }

            self.requests = Req(self, subscriber, balance)
            self.agents = Agents()

    payments = PaymentsWithAgentRequest(subscriber=True, balance=5000)
    mcp = build_mcp_integration(payments)
    mcp.configure({"agentId": "did:nv:agent:abc123", "serverName": "weather-service"})

    captured_contexts = []

    async def weather_handler(args, extra=None, context=None):
        captured_contexts.append(context)

        if not context:
            return {"error": "No context provided"}

        agent_request = context["agent_request"]
        auth_result = context["auth_result"]
        credits = context["credits"]

        # Simulate business logic using context data
        city = args.get("city", "Unknown")

        # Check if agent has sufficient balance
        if agent_request["balance"]["balance"] < credits:
            return {
                "error": "Insufficient balance",
                "required": credits,
                "available": agent_request["balance"]["balance"],
            }

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
                "agentName": agent_request["agentName"],
                "requestId": auth_result["requestId"],
                "creditsUsed": credits,
                "balanceRemaining": agent_request["balance"]["balance"] - credits,
                "isSubscriber": agent_request["balance"]["isSubscriber"],
                "pricePerCredit": agent_request["balance"]["pricePerCredit"],
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

    # Verify PaywallContext structure
    assert context["auth_result"]["requestId"].startswith("req-did:nv:agent:abc123-")
    assert context["auth_result"]["token"] == "weather-token-123"
    assert context["auth_result"]["agentId"] == "did:nv:agent:abc123"
    assert (
        "mcp://weather-service/tools/get-weather"
        in context["auth_result"]["logicalUrl"]
    )

    # Verify agent request data
    assert context["agent_request"]["agentName"] == "Agent abc123"
    assert context["agent_request"]["agentId"] == "did:nv:agent:abc123"
    assert context["agent_request"]["balance"]["balance"] == 5000
    assert context["agent_request"]["balance"]["isSubscriber"] is True
    assert context["agent_request"]["balance"]["pricePerCredit"] == 0.01
    assert context["agent_request"]["urlMatching"].startswith(
        "mcp://weather-service/tools/get-weather"
    )
    assert context["agent_request"]["verbMatching"] == "POST"
    assert context["agent_request"]["batch"] is False

    # Verify credits
    assert context["credits"] == 5

    # Verify metadata in result
    assert result["metadata"]["agentName"] == "Agent abc123"
    assert result["metadata"]["creditsUsed"] == 5
    assert result["metadata"]["balanceRemaining"] == 4995  # 5000 - 5
    assert result["metadata"]["isSubscriber"] is True
    assert result["metadata"]["pricePerCredit"] == 0.01
