"""Unit tests asserting that AgentAPIAttributes accepts payloads with
``endpoints`` and ``agent_definition_url`` omitted.

These two fields are now opt-in **Additional Security**.

Refs nevermined-io/internal#897 #911.
"""

from payments_py.common.types import AgentAPIAttributes, AuthType


def test_accepts_empty_payload():
    attrs = AgentAPIAttributes()
    assert attrs.endpoints is None
    assert attrs.agent_definition_url is None
    assert attrs.open_endpoints is None


def test_accepts_only_authentication_fields():
    attrs = AgentAPIAttributes(auth_type=AuthType.BEARER, token="sk-test-abc")
    assert attrs.auth_type == AuthType.BEARER
    assert attrs.token == "sk-test-abc"
    assert attrs.endpoints is None
    assert attrs.agent_definition_url is None


def test_accepts_only_endpoints_for_additional_security_optin():
    attrs = AgentAPIAttributes(
        endpoints=[{"verb": "POST", "url": "https://example.com/api/run"}],
    )
    assert attrs.endpoints is not None
    assert len(attrs.endpoints) == 1
    assert attrs.agent_definition_url is None


def test_accepts_only_agent_definition_url():
    attrs = AgentAPIAttributes(
        agent_definition_url="https://example.com/openapi.json",
    )
    assert attrs.agent_definition_url == "https://example.com/openapi.json"
    assert attrs.endpoints is None


def test_still_accepts_full_shape():
    attrs = AgentAPIAttributes(
        endpoints=[{"verb": "POST", "url": "https://example.com/api/run"}],
        open_endpoints=["https://example.com/health"],
        agent_definition_url="https://example.com/openapi.json",
        auth_type=AuthType.BEARER,
        token="sk-test",
    )
    assert attrs.endpoints is not None
    assert len(attrs.endpoints) == 1
    assert attrs.open_endpoints == ["https://example.com/health"]
    assert attrs.agent_definition_url == "https://example.com/openapi.json"
    assert attrs.auth_type == AuthType.BEARER
