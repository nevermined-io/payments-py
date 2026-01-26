"""
E2E tests for MCP OAuth server endpoints.

These tests verify the OAuth discovery endpoints and server functionality
by starting a real HTTP server and making requests to it.
"""

import asyncio

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from payments_py.mcp import build_mcp_integration


def mock_decode_access_token(token: str):
    """Mock x402 token decoder."""
    return {
        "x402Version": 2,
        "accepted": {
            "scheme": "nvm:erc4337",
            "network": "eip155:84532",
            "planId": "plan-123",
            "extra": {"version": "1"},
        },
        "payload": {
            "signature": "0x123",
            "authorization": {
                "from": "0xSubscriber123",
                "sessionKeysProvider": "zerodev",
                "sessionKeys": [],
            },
        },
        "extensions": {},
    }


class PaymentsMock:
    """Mock Payments for E2E server tests."""

    def __init__(self):
        self._environment_name = "sandbox"
        self.facilitator = MagicMock()
        self.facilitator.verify_permissions = AsyncMock(return_value={"isValid": True})
        self.facilitator.settle_permissions = AsyncMock(
            return_value={
                "success": True,
                "transaction": "0xtest123",
                "network": "eip155:84532",
                "creditsRedeemed": "5",
            }
        )
        self.agents = MagicMock()
        self.agents.get_agent_plans = AsyncMock(
            return_value={"plans": [{"planId": "plan-123", "name": "Test Plan"}]}
        )
        # Initialize mcp attribute for server manager
        self._mcp = None

    @property
    def mcp(self):
        if self._mcp is None:
            self._mcp = build_mcp_integration(self)
        return self._mcp


# Test port for E2E tests (use high port to avoid conflicts)
TEST_PORT = 18890


async def create_and_start_server(port: int = TEST_PORT):
    """Create, configure, and start a test MCP server."""
    mock_payments = PaymentsMock()

    # Configure MCP
    mock_payments.mcp.configure(
        {"agentId": "test-agent-123", "serverName": "test-mcp-server"}
    )

    # Register a test tool
    async def weather_handler(args, context=None):
        city = args.get("city", "Unknown")
        return {
            "content": [{"type": "text", "text": f"Weather in {city}: 22°C, sunny"}]
        }

    mock_payments.mcp.register_tool(
        "weather",
        {"description": "Get weather for a city"},
        weather_handler,
        {"credits": 5},
    )

    # Register a test resource
    async def config_handler(uri, variables, context=None):
        return {
            "contents": [
                {
                    "uri": str(uri),
                    "mimeType": "application/json",
                    "text": '{"version": "1.0.0", "debug": false}',
                }
            ]
        }

    mock_payments.mcp.register_resource(
        "data://config",
        {"name": "Configuration", "mimeType": "application/json"},
        config_handler,
        {"credits": 2},
    )

    # Register a test prompt
    async def greeting_handler(args, context=None):
        name = args.get("name", "User")
        return {
            "messages": [
                {"role": "user", "content": {"type": "text", "text": f"Hello {name}!"}}
            ]
        }

    mock_payments.mcp.register_prompt(
        "greeting",
        {"name": "Greeting", "description": "Greet a user"},
        greeting_handler,
        {"credits": 1},
    )

    # Start the server
    result = await mock_payments.mcp.start(
        {
            "port": port,
            "agentId": "test-agent-123",
            "serverName": "test-mcp-server",
            "version": "0.1.0",
            "description": "Test MCP server for E2E tests",
        }
    )

    # Give server time to fully start
    await asyncio.sleep(0.5)

    return {
        "mock_payments": mock_payments,
        "result": result,
        "base_url": f"http://localhost:{port}",
    }


class TestMcpOAuthDiscoveryEndpoints:
    """Tests for OAuth discovery endpoints (/.well-known/*)."""

    @pytest.mark.asyncio
    async def test_oauth_protected_resource_metadata(self):
        """Should return valid OAuth protected resource metadata (RFC 9728)."""
        server_data = await create_and_start_server(18890)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{base_url}/.well-known/oauth-protected-resource"
                )

            assert response.status_code == 200
            assert "application/json" in response.headers.get("content-type", "")

            data = response.json()

            # Required fields per RFC 9728
            assert data["resource"] == base_url
            assert "authorization_servers" in data
            assert isinstance(data["authorization_servers"], list)
            assert len(data["authorization_servers"]) > 0

            # MCP-specific scopes
            assert "scopes_supported" in data
            assert "mcp:tools" in data["scopes_supported"]
            assert "mcp:read" in data["scopes_supported"]
            assert "mcp:write" in data["scopes_supported"]

            # Optional but recommended
            assert data["bearer_methods_supported"] == ["header"]
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_oauth_authorization_server_metadata(self):
        """Should return valid OAuth authorization server metadata (RFC 8414)."""
        server_data = await create_and_start_server(18891)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{base_url}/.well-known/oauth-authorization-server"
                )

            assert response.status_code == 200
            assert "application/json" in response.headers.get("content-type", "")

            data = response.json()

            # Required fields per RFC 8414
            assert "issuer" in data
            assert "authorization_endpoint" in data
            assert "token_endpoint" in data

            # Response types and grant types
            assert data["response_types_supported"] == ["code"]
            assert "authorization_code" in data["grant_types_supported"]
            assert "refresh_token" in data["grant_types_supported"]

            # PKCE support
            assert data["code_challenge_methods_supported"] == ["S256"]

            # Scopes
            assert "openid" in data["scopes_supported"]
            assert "mcp:tools" in data["scopes_supported"]

            # Token endpoint auth methods
            assert "client_secret_post" in data["token_endpoint_auth_methods_supported"]

            # Registration and JWKS
            assert "registration_endpoint" in data
            assert "jwks_uri" in data
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_openid_configuration(self):
        """Should return valid OpenID Connect configuration."""
        server_data = await create_and_start_server(18892)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{base_url}/.well-known/openid-configuration"
                )

            assert response.status_code == 200
            assert "application/json" in response.headers.get("content-type", "")

            data = response.json()

            # Required OIDC Discovery fields
            assert "issuer" in data
            assert "authorization_endpoint" in data
            assert "token_endpoint" in data
            assert "jwks_uri" in data
            assert "response_types_supported" in data
            assert "subject_types_supported" in data
            assert "id_token_signing_alg_values_supported" in data

            # OIDC-specific
            assert "userinfo_endpoint" in data

            # Must include 'openid' scope
            assert "openid" in data["scopes_supported"]

            # Claims supported
            assert "claims_supported" in data
            assert "sub" in data["claims_supported"]
            assert "iss" in data["claims_supported"]

            # Auth methods
            assert "none" in data["token_endpoint_auth_methods_supported"]
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_consistent_issuer_across_endpoints(self):
        """Should have consistent issuer across all discovery endpoints."""
        server_data = await create_and_start_server(18893)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                auth_server_res = await client.get(
                    f"{base_url}/.well-known/oauth-authorization-server"
                )
                oidc_res = await client.get(
                    f"{base_url}/.well-known/openid-configuration"
                )

            auth_server_data = auth_server_res.json()
            oidc_data = oidc_res.json()

            # Issuer should be consistent
            assert auth_server_data["issuer"] == oidc_data["issuer"]

            # Endpoints should also be consistent
            assert (
                auth_server_data["authorization_endpoint"]
                == oidc_data["authorization_endpoint"]
            )
            assert auth_server_data["token_endpoint"] == oidc_data["token_endpoint"]
            assert auth_server_data["jwks_uri"] == oidc_data["jwks_uri"]
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)


class TestMcpServerInfoEndpoint:
    """Tests for server info endpoint (/)."""

    @pytest.mark.asyncio
    async def test_server_info_endpoint(self):
        """Should return server info with all endpoints."""
        server_data = await create_and_start_server(18894)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/")

            assert response.status_code == 200
            data = response.json()

            assert data["name"] == "test-mcp-server"
            assert data["version"] == "0.1.0"

            # Endpoints
            assert "endpoints" in data
            assert data["endpoints"]["mcp"] == f"{base_url}/mcp"
            assert data["endpoints"]["health"] == f"{base_url}/health"
            assert data["endpoints"]["register"] == f"{base_url}/register"

            # OAuth info
            assert "oauth" in data
            assert "authorization_server_metadata" in data["oauth"]
            assert "protected_resource_metadata" in data["oauth"]
            assert "openid_configuration" in data["oauth"]
            assert data["oauth"]["client_id"] == "test-agent-123"
            assert "scopes" in data["oauth"]
            assert "mcp:tools" in data["oauth"]["scopes"]

            # MCP capabilities
            assert "weather" in data["tools"]
            assert "data://config" in data["resources"]
            assert "greeting" in data["prompts"]
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)


class TestMcpHealthEndpoint:
    """Tests for health check endpoint."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Should return health status."""
        server_data = await create_and_start_server(18895)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{base_url}/health")

            assert response.status_code == 200
            data = response.json()

            assert data["status"] == "ok"
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)


class TestMcpClientRegistration:
    """Tests for OAuth dynamic client registration (RFC 7591)."""

    @pytest.mark.asyncio
    async def test_client_registration_endpoint(self):
        """Should handle client registration requests."""
        server_data = await create_and_start_server(18896)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/register",
                    json={
                        "redirect_uris": ["http://localhost:3000/callback"],
                        "client_name": "Test MCP Client",
                        "token_endpoint_auth_method": "none",
                    },
                )

            # 201 Created is the correct response per RFC 7591
            assert response.status_code == 201
            data = response.json()

            # Required response fields per RFC 7591
            assert "client_id" in data
            assert data["client_id"] == "test-agent-123"
            assert "client_id_issued_at" in data
            assert "redirect_uris" in data
            assert data["redirect_uris"] == ["http://localhost:3000/callback"]
            assert data["client_name"] == "Test MCP Client"
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_client_registration_with_secret(self):
        """Should generate client secret when requested."""
        server_data = await create_and_start_server(18897)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/register",
                    json={
                        "redirect_uris": ["http://localhost:3000/callback"],
                        "token_endpoint_auth_method": "client_secret_post",
                    },
                )

            # 201 Created is the correct response per RFC 7591
            assert response.status_code == 201
            data = response.json()

            assert "client_secret" in data
            assert len(data["client_secret"]) > 0
            assert data["client_secret_expires_at"] == 0  # Never expires
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.asyncio
    async def test_client_registration_validation_error(self):
        """Should return error for invalid registration request."""
        server_data = await create_and_start_server(18898)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/register",
                    json={
                        # Missing redirect_uris
                        "client_name": "Invalid Client",
                    },
                )

            assert response.status_code == 400
            data = response.json()

            assert "error" in data
            assert data["error"] == "invalid_request"
            assert "redirect_uris" in data.get("error_description", "")
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)


class TestMcpEndpointWithoutAuth:
    """Tests for MCP endpoint without authentication."""

    @pytest.mark.asyncio
    async def test_mcp_endpoint_rejects_without_auth(self):
        """Should reject MCP requests without authentication."""
        server_data = await create_and_start_server(18899)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "weather", "arguments": {"city": "Madrid"}},
                    },
                    headers={"Content-Type": "application/json"},
                )

            # Should reject with 401 Unauthorized
            assert response.status_code == 401
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)


class TestMcpEndpointWithAuth:
    """Tests for MCP endpoint with authentication.

    NOTE: These tests are skipped because the Python MCP SDK uses SSE transport
    which requires a different flow:
    1. First establish SSE connection (GET) to get a session_id
    2. Then POST messages with session_id in query params

    The SDK doesn't support direct HTTP request/response pattern.
    """

    @pytest.mark.skip(
        reason="Python MCP SDK requires SSE session flow, not direct HTTP"
    )
    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_mcp_tool_call_with_valid_token(self):
        """Should execute tool with valid token."""
        server_data = await create_and_start_server(18900)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": "weather", "arguments": {"city": "Madrid"}},
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-token-123",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            assert "result" in data
            assert "content" in data["result"]
            assert "Madrid" in data["result"]["content"][0]["text"]
            assert "sunny" in data["result"]["content"][0]["text"]
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.skip(
        reason="Python MCP SDK requires SSE session flow, not direct HTTP"
    )
    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_mcp_tools_list_with_valid_token(self):
        """Should list tools with valid token."""
        server_data = await create_and_start_server(18901)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/list",
                        "params": {},
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-token-123",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            assert "result" in data
            assert "tools" in data["result"]

            tool_names = [t["name"] for t in data["result"]["tools"]]
            assert "weather" in tool_names
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)

    @pytest.mark.skip(
        reason="Python MCP SDK requires SSE session flow, not direct HTTP"
    )
    @pytest.mark.asyncio
    @patch("payments_py.mcp.core.auth.decode_access_token", mock_decode_access_token)
    async def test_mcp_prompts_list_with_valid_token(self):
        """Should list prompts with valid token."""
        server_data = await create_and_start_server(18902)
        base_url = server_data["base_url"]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    f"{base_url}/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "prompts/list",
                        "params": {},
                    },
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": "Bearer test-token-123",
                    },
                )

            assert response.status_code == 200
            data = response.json()

            assert "result" in data
            assert "prompts" in data["result"]

            prompt_names = [p["name"] for p in data["result"]["prompts"]]
            assert "greeting" in prompt_names
        finally:
            await server_data["result"]["stop"]()
            await asyncio.sleep(0.3)
