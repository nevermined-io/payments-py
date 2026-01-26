"""
Unit tests for OAuth metadata builders.

These tests verify the OAuth 2.1 metadata generation functions
following RFC 8414, RFC 9728, and OpenID Connect Discovery standards.
"""

import pytest

from payments_py.mcp.http.oauth_metadata import (
    build_authorization_server_metadata,
    build_mcp_protected_resource_metadata,
    build_oidc_configuration,
    build_protected_resource_metadata,
    build_server_info_response,
    get_oauth_urls,
)


@pytest.fixture
def base_config():
    """Base OAuth configuration for tests."""
    return {
        "baseUrl": "http://localhost:3000",
        "agentId": "unit_agent_id_hex",
        "environment": "sandbox",
        "serverName": "test-mcp-server",
        "tools": ["weather.today", "weather.forecast"],
        "resources": ["weather://today/{city}"],
        "prompts": ["weather.ensureCity"],
    }


class TestBuildProtectedResourceMetadata:
    """Tests for buildProtectedResourceMetadata function."""

    def test_builds_protected_resource_metadata_with_required_fields(self, base_config):
        """Should build protected resource metadata with required fields."""
        metadata = build_protected_resource_metadata(base_config)

        assert metadata is not None
        assert metadata["resource"] == "http://localhost:3000"
        assert metadata["authorization_servers"] == ["http://localhost:3000"]
        assert metadata["bearer_methods_supported"] == ["header"]
        assert metadata["resource_documentation"] == "http://localhost:3000/"

    def test_includes_default_scopes(self, base_config):
        """Should include default scopes."""
        metadata = build_protected_resource_metadata(base_config)

        assert "openid" in metadata["scopes_supported"]
        assert "profile" in metadata["scopes_supported"]
        assert "credits" in metadata["scopes_supported"]
        assert "mcp:read" in metadata["scopes_supported"]
        assert "mcp:write" in metadata["scopes_supported"]
        assert "mcp:tools" in metadata["scopes_supported"]

    def test_uses_custom_scopes_when_provided(self, base_config):
        """Should use custom scopes when provided."""
        config = {**base_config, "scopes": ["custom:scope1", "custom:scope2"]}
        metadata = build_protected_resource_metadata(config)

        assert metadata["scopes_supported"] == ["custom:scope1", "custom:scope2"]
        assert "openid" not in metadata["scopes_supported"]


class TestBuildMcpProtectedResourceMetadata:
    """Tests for buildMcpProtectedResourceMetadata function."""

    def test_builds_mcp_specific_protected_resource_metadata(self, base_config):
        """Should build MCP-specific protected resource metadata."""
        metadata = build_mcp_protected_resource_metadata(base_config)

        assert metadata is not None
        assert metadata["resource"] == "http://localhost:3000/mcp"
        assert metadata["authorization_servers"] == ["http://localhost:3000"]
        assert metadata["bearer_methods_supported"] == ["header"]

    def test_includes_mcp_capabilities(self, base_config):
        """Should include MCP capabilities."""
        metadata = build_mcp_protected_resource_metadata(base_config)

        assert metadata["mcp_capabilities"] is not None
        assert metadata["mcp_capabilities"]["tools"] == [
            "weather.today",
            "weather.forecast",
        ]
        assert metadata["mcp_capabilities"]["protocol_version"] == "2024-11-05"

    def test_includes_both_scopes_supported_and_required(self, base_config):
        """Should include both scopes_supported and scopes_required."""
        metadata = build_mcp_protected_resource_metadata(base_config)

        assert metadata["scopes_supported"] is not None
        assert metadata["scopes_required"] is not None
        assert metadata["scopes_supported"] == metadata["scopes_required"]

    def test_uses_custom_protocol_version_when_provided(self, base_config):
        """Should use custom protocol version when provided."""
        config = {**base_config, "protocolVersion": "2024-12-01"}
        metadata = build_mcp_protected_resource_metadata(config)

        assert metadata["mcp_capabilities"]["protocol_version"] == "2024-12-01"


class TestBuildAuthorizationServerMetadata:
    """Tests for buildAuthorizationServerMetadata function."""

    def test_builds_authorization_server_metadata_with_required_endpoints(
        self, base_config
    ):
        """Should build authorization server metadata with all required endpoints."""
        metadata = build_authorization_server_metadata(base_config)

        assert metadata is not None
        assert metadata["issuer"] is not None
        assert metadata["authorization_endpoint"] is not None
        assert metadata["token_endpoint"] is not None
        assert metadata["registration_endpoint"] == "http://localhost:3000/register"
        assert metadata["jwks_uri"] is not None

    def test_includes_supported_response_types_and_grant_types(self, base_config):
        """Should include supported response types and grant types."""
        metadata = build_authorization_server_metadata(base_config)

        assert metadata["response_types_supported"] == ["code"]
        assert "authorization_code" in metadata["grant_types_supported"]
        assert "refresh_token" in metadata["grant_types_supported"]

    def test_supports_pkce_with_s256(self, base_config):
        """Should support PKCE with S256."""
        metadata = build_authorization_server_metadata(base_config)

        assert metadata["code_challenge_methods_supported"] == ["S256"]

    def test_includes_scopes(self, base_config):
        """Should include scopes."""
        metadata = build_authorization_server_metadata(base_config)

        assert "openid" in metadata["scopes_supported"]
        assert "credits" in metadata["scopes_supported"]

    def test_supports_client_secret_post_authentication(self, base_config):
        """Should support client_secret_post authentication."""
        metadata = build_authorization_server_metadata(base_config)

        assert "client_secret_post" in metadata["token_endpoint_auth_methods_supported"]

    def test_uses_custom_oauth_urls_when_provided(self, base_config):
        """Should use custom OAuth URLs when provided."""
        config = {
            **base_config,
            "oauthUrls": {
                "issuer": "https://custom-issuer.com",
                "authorizationUri": "https://custom-issuer.com/oauth/authorize",
                "tokenUri": "https://custom-api.com/oauth/token",
                "jwksUri": "https://custom-api.com/.well-known/jwks.json",
                "userinfoUri": "https://custom-api.com/oauth/userinfo",
            },
        }
        metadata = build_authorization_server_metadata(config)

        assert metadata["issuer"] == "https://custom-issuer.com"
        assert (
            metadata["authorization_endpoint"]
            == "https://custom-issuer.com/oauth/authorize"
        )
        assert metadata["token_endpoint"] == "https://custom-api.com/oauth/token"
        assert metadata["jwks_uri"] == "https://custom-api.com/.well-known/jwks.json"


class TestBuildOidcConfiguration:
    """Tests for buildOidcConfiguration function."""

    def test_builds_oidc_configuration_with_required_fields(self, base_config):
        """Should build OIDC configuration with required fields."""
        config = build_oidc_configuration(base_config)

        assert config is not None
        assert config["issuer"] is not None
        assert config["authorization_endpoint"] is not None
        assert config["token_endpoint"] is not None
        assert config["jwks_uri"] is not None
        assert config["userinfo_endpoint"] is not None
        assert config["registration_endpoint"] == "http://localhost:3000/register"

    def test_includes_openid_scope_even_if_not_in_custom_scopes(self, base_config):
        """Should include openid scope even if not in custom scopes."""
        config = {**base_config, "scopes": ["profile", "credits"]}
        oidc_config = build_oidc_configuration(config)

        assert "openid" in oidc_config["scopes_supported"]
        assert "profile" in oidc_config["scopes_supported"]
        assert "credits" in oidc_config["scopes_supported"]

    def test_does_not_duplicate_openid_scope(self, base_config):
        """Should not duplicate openid scope."""
        config = {**base_config, "scopes": ["openid", "profile"]}
        oidc_config = build_oidc_configuration(config)

        openid_count = oidc_config["scopes_supported"].count("openid")
        assert openid_count == 1

    def test_supports_none_and_client_secret_post_auth_methods(self, base_config):
        """Should support none and client_secret_post auth methods."""
        config = build_oidc_configuration(base_config)

        assert "none" in config["token_endpoint_auth_methods_supported"]
        assert "client_secret_post" in config["token_endpoint_auth_methods_supported"]

    def test_includes_supported_signing_algorithms(self, base_config):
        """Should include supported signing algorithms."""
        config = build_oidc_configuration(base_config)

        assert "RS256" in config["id_token_signing_alg_values_supported"]
        assert "HS256" in config["id_token_signing_alg_values_supported"]

    def test_includes_standard_oidc_claims(self, base_config):
        """Should include standard OIDC claims."""
        config = build_oidc_configuration(base_config)

        assert "sub" in config["claims_supported"]
        assert "iss" in config["claims_supported"]
        assert "aud" in config["claims_supported"]
        assert "exp" in config["claims_supported"]
        assert "iat" in config["claims_supported"]
        assert "name" in config["claims_supported"]
        assert "email" in config["claims_supported"]


class TestBuildServerInfoResponse:
    """Tests for buildServerInfoResponse function."""

    def test_builds_server_info_with_all_endpoints(self, base_config):
        """Should build server info with all endpoints."""
        info = build_server_info_response(base_config)

        assert info is not None
        assert info["name"] == "test-mcp-server"
        assert info["version"] == "1.0.0"
        assert info["endpoints"] is not None
        assert info["endpoints"]["mcp"] == "http://localhost:3000/mcp"
        assert info["endpoints"]["health"] == "http://localhost:3000/health"
        assert info["endpoints"]["register"] == "http://localhost:3000/register"

    def test_includes_oauth_endpoints(self, base_config):
        """Should include OAuth endpoints."""
        info = build_server_info_response(base_config)

        assert info["oauth"] is not None
        assert (
            info["oauth"]["authorization_server_metadata"]
            == "http://localhost:3000/.well-known/oauth-authorization-server"
        )
        assert (
            info["oauth"]["protected_resource_metadata"]
            == "http://localhost:3000/.well-known/oauth-protected-resource"
        )
        assert (
            info["oauth"]["openid_configuration"]
            == "http://localhost:3000/.well-known/openid-configuration"
        )

    def test_includes_mcp_capabilities(self, base_config):
        """Should include MCP capabilities."""
        info = build_server_info_response(base_config)

        assert info["tools"] == ["weather.today", "weather.forecast"]
        assert info["resources"] == ["weather://today/{city}"]
        assert info["prompts"] == ["weather.ensureCity"]

    def test_uses_custom_version_and_description(self, base_config):
        """Should use custom version and description."""
        info = build_server_info_response(
            base_config, version="2.0.0", description="Custom MCP server"
        )

        assert info["version"] == "2.0.0"
        assert info["description"] == "Custom MCP server"

    def test_includes_client_id_in_oauth_info(self, base_config):
        """Should include client_id (agentId) in OAuth info."""
        info = build_server_info_response(base_config)

        assert info["oauth"]["client_id"] == "unit_agent_id_hex"

    def test_includes_scopes_in_oauth_info(self, base_config):
        """Should include scopes in OAuth info."""
        info = build_server_info_response(base_config)

        assert info["oauth"]["scopes"] is not None
        assert isinstance(info["oauth"]["scopes"], list)
        assert len(info["oauth"]["scopes"]) > 0


class TestGetOAuthUrls:
    """Tests for getOAuthUrls function."""

    def test_returns_urls_for_sandbox_environment(self):
        """Should return URLs for sandbox environment."""
        urls = get_oauth_urls("sandbox")

        assert urls["issuer"] is not None
        assert "/oauth/authorize" in urls["authorizationUri"]
        assert "/oauth/token" in urls["tokenUri"]
        assert "/.well-known/jwks.json" in urls["jwksUri"]
        assert "/oauth/userinfo" in urls["userinfoUri"]

    def test_returns_urls_for_live_environment(self):
        """Should return URLs for live environment."""
        urls = get_oauth_urls("live")

        assert urls["issuer"] is not None
        assert "/oauth/authorize" in urls["authorizationUri"]
        assert "/oauth/token" in urls["tokenUri"]

    def test_allows_partial_url_overrides(self):
        """Should allow partial URL overrides."""
        urls = get_oauth_urls("sandbox", {"issuer": "https://custom-issuer.com"})

        assert urls["issuer"] == "https://custom-issuer.com"
        # Other URLs should still use sandbox defaults
        assert urls["tokenUri"] is not None
        assert urls["tokenUri"] != "https://custom-issuer.com"

    def test_allows_complete_url_overrides(self):
        """Should allow complete URL overrides."""
        custom_urls = {
            "issuer": "https://custom-issuer.com",
            "authorizationUri": "https://custom-issuer.com/auth",
            "tokenUri": "https://custom-api.com/token",
            "jwksUri": "https://custom-api.com/jwks",
            "userinfoUri": "https://custom-api.com/userinfo",
        }
        urls = get_oauth_urls("sandbox", custom_urls)

        assert urls == custom_urls
