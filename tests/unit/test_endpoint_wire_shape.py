"""Unit tests asserting that agent endpoint allowlist entries are serialized in
the ``{<VERB>: <url>}`` shape the backend matches with ``Object.entries(ep)[0]``.

Refs nevermined-io/payments-py#274.
"""

from payments_py.common.types import AgentAPIAttributes, Endpoint


def test_endpoint_serializes_as_verb_keyed_mapping():
    endpoint = Endpoint(verb="POST", url="https://myagent.ai/api/v1/:agentId/tasks")
    assert endpoint.model_dump() == {"POST": "https://myagent.ai/api/v1/:agentId/tasks"}


def test_agent_api_attributes_serializes_endpoints_in_wire_shape():
    attrs = AgentAPIAttributes(
        endpoints=[
            {"verb": "POST", "url": "https://myagent.ai/tasks"},
            Endpoint(verb="GET", url="https://myagent.ai/tasks/:taskId"),
        ],
    )
    dumped = attrs.model_dump(exclude_none=True)
    assert dumped["endpoints"] == [
        {"POST": "https://myagent.ai/tasks"},
        {"GET": "https://myagent.ai/tasks/:taskId"},
    ]
    for entry in dumped["endpoints"]:
        verb, url = next(iter(entry.items()))
        assert verb in ("POST", "GET")
        assert url.startswith("https://")


def test_endpoint_accepts_the_wire_shape_as_input():
    attrs = AgentAPIAttributes(endpoints=[{"POST": "https://myagent.ai/tasks"}])
    assert attrs.endpoints == [Endpoint(verb="POST", url="https://myagent.ai/tasks")]


def test_serialized_attributes_round_trip():
    attrs = AgentAPIAttributes(
        endpoints=[Endpoint(verb="DELETE", url="https://myagent.ai/tasks/:taskId")],
    )
    reloaded = AgentAPIAttributes(**attrs.model_dump(exclude_none=True))
    assert reloaded.endpoints == attrs.endpoints
