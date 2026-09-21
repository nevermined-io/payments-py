"""
Unit tests for OAuth metadata builders.

These tests verify the OAuth 2.1 metadata generation functions
following RFC 8414, RFC 9728, and OpenID Connect Discovery standards.
"""

import pytest
from urllib.parse import parse_qsl, urlsplit

from payments_py.environments import EnvironmentInfo, Environments
from payments_py.mcp.http.oauth_metadata import (
    build_authorization_server_metadata,
    build_mcp_protected_resource_metadata,
    build_oidc_configuration,
    build_protected_resource_metadata,
    build_server_info_response,
    get_oauth_urls,
    OAUTH_TIER_PARAM,
    _with_tier_param,
    _origin_of,
    resolve_oauth_tier,
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

    def test_omits_client_id_when_no_agent_id(self, base_config):
        """Plan-centric: server-info OAuth omits client_id when no agentId is set
        (must not advertise client_id: null)."""
        cfg = {k: v for k, v in base_config.items() if k != "agentId"}
        info = build_server_info_response(cfg)
        assert "client_id" not in info["oauth"]

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

    def test_omits_disabled_discovery_advertisements(self, base_config):
        """Should only advertise mounted OAuth discovery routes."""
        info = build_server_info_response(
            {
                **base_config,
                "enableOAuthDiscovery": False,
            }
        )

        assert "authorization_server_metadata" not in info["oauth"]
        assert "protected_resource_metadata" not in info["oauth"]
        assert "openid_configuration" not in info["oauth"]
        assert info["oauth"]["authorization_endpoint"]
        assert info["oauth"]["token_endpoint"]

    def test_never_advertises_x402_discovery_endpoint(self, base_config):
        """x402 v2 MCP transport signals payment in band — no discovery endpoint."""
        info = build_server_info_response(base_config)

        assert "x402_payment" not in info["endpoints"]
        assert "x402_payment_discovery" not in info["oauth"]

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


class TestAuthorizationEndpointCarriesTheTier:
    """nvm-monorepo#3430 / payments-py#277: the authorize URL this server advertises
    must name the API tier, because one Nevermined web app serves both tiers'
    consent screens and boots on Live by default — a bare URL sent a sandbox
    server's users to the LIVE consent screen ("Connector not authorized").
    Same param name + values as the API's own RFC 8414 document (``network``)."""

    @pytest.mark.parametrize(
        "environment,expected",
        [
            ("sandbox", "https://nevermined.app/oauth/authorize?network=sandbox"),
            (
                "staging_sandbox",
                "https://nevermined.dev/oauth/authorize?network=sandbox",
            ),
            ("live", "https://nevermined.app/oauth/authorize?network=live"),
            ("staging_live", "https://nevermined.dev/oauth/authorize?network=live"),
        ],
    )
    def test_named_environments_advertise_their_tier_in_every_document(
        self, base_config, environment, expected
    ):
        assert get_oauth_urls(environment)["authorizationUri"] == expected
        config = {**base_config, "environment": environment}
        assert (
            build_authorization_server_metadata(config)["authorization_endpoint"]
            == expected
        )
        assert build_oidc_configuration(config)["authorization_endpoint"] == expected
        assert (
            build_server_info_response(config)["oauth"]["authorization_endpoint"]
            == expected
        )

    def test_param_is_network_and_the_url_has_one_query_string(self):
        assert OAUTH_TIER_PARAM == "network"
        uri = get_oauth_urls("sandbox")["authorizationUri"]
        assert uri.count("?") == 1
        parts = urlsplit(uri)
        assert parts.path == "/oauth/authorize"
        assert parse_qsl(parts.query) == [("network", "sandbox")]

    def test_tier_is_not_stamped_on_token_jwks_userinfo_or_issuer(self):
        urls = get_oauth_urls("sandbox")
        for key in ("tokenUri", "jwksUri", "userinfoUri", "issuer"):
            assert "network=" not in urls[key]

    def test_explicit_authorization_uri_override_passes_through_untouched(self):
        urls = get_oauth_urls(
            "sandbox", {"authorizationUri": "https://custom-issuer.com/oauth/authorize"}
        )
        assert urls["authorizationUri"] == "https://custom-issuer.com/oauth/authorize"

    def test_resolve_oauth_tier_named_custom_and_unclassifiable(self):
        assert resolve_oauth_tier("sandbox", "ignored") == "sandbox"
        assert resolve_oauth_tier("staging_sandbox", "ignored") == "sandbox"
        assert resolve_oauth_tier("live", "ignored") == "live"
        assert resolve_oauth_tier("staging_live", "ignored") == "live"
        assert (
            resolve_oauth_tier("custom", "https://api.sandbox.nevermined.app/")
            == "sandbox"
        )
        assert resolve_oauth_tier("custom", "https://api.live.nevermined.dev") == "live"
        # Every host shape the API actually serves: branded per-org subdomains, the
        # Commerce MCP; and ``hostname`` lowercases + strips port/credentials/path.
        assert (
            resolve_oauth_tier("custom", "https://acme.api.sandbox.nevermined.app")
            == "sandbox"
        )
        assert (
            resolve_oauth_tier("custom", "https://mcp.api.live.nevermined.dev")
            == "live"
        )
        assert (
            resolve_oauth_tier("custom", "https://API.Sandbox.nevermined.app:8443/x")
            == "sandbox"
        )
        # Anchored on the ``api.<tier>`` label pair — a bare ``sandbox`` label elsewhere
        # is NOT a tier.
        assert resolve_oauth_tier("custom", "https://sandbox.nevermined.app") is None
        assert (
            resolve_oauth_tier("custom", "https://api.nevermined.app/sandbox") is None
        )
        # Unclassifiable: a local stack, no hostname, or the one input urlsplit refuses
        # (an unbalanced IPv6 literal) — no guessed tier.
        assert resolve_oauth_tier("custom", "http://localhost:3001") is None
        assert resolve_oauth_tier("custom", "not a url") is None
        assert resolve_oauth_tier("custom", "http://[::1") is None

    @pytest.mark.parametrize(
        "backend,expected",
        [
            (
                "https://api.sandbox.nevermined.app",
                "https://nevermined.app/oauth/authorize?network=sandbox",
            ),
            (
                "https://api.live.nevermined.app/",
                "https://nevermined.app/oauth/authorize?network=live",
            ),
            ("http://localhost:3001", "https://nevermined.app/oauth/authorize"),
        ],
    )
    def test_custom_derives_the_tier_through_the_public_surface(
        self, monkeypatch, backend, expected
    ):
        # ``Environments["custom"]`` holds values read from the env at import, but the
        # LOOKUP is call-time on the same dict object — so swapping the entry drives
        # the public ``get_oauth_urls("custom")`` path (the one production uses).
        monkeypatch.setitem(
            Environments,
            "custom",
            EnvironmentInfo(
                frontend="https://nevermined.app",
                backend=backend,
                proxy="",
                helicone_url="",
            ),
        )
        assert get_oauth_urls("custom")["authorizationUri"] == expected

    def test_custom_tier_follows_the_backend_the_document_publishes(self, monkeypatch):
        # ``custom`` + a ``tokenUri`` override pointing at a real tier used to publish a
        # sandbox token_endpoint next to a BARE authorize URL — the #277 bug, silently.
        monkeypatch.setitem(
            Environments,
            "custom",
            EnvironmentInfo(
                frontend="https://nevermined.app",
                backend="http://localhost:3001",
                proxy="",
                helicone_url="",
            ),
        )
        sandbox = get_oauth_urls(
            "custom", {"tokenUri": "https://api.sandbox.nevermined.app/oauth/token"}
        )
        assert sandbox["authorizationUri"].endswith("?network=sandbox")
        live = get_oauth_urls(
            "custom", {"tokenUri": "https://api.live.nevermined.app/oauth/token"}
        )
        assert live["authorizationUri"].endswith("?network=live")
        # A local override keeps the bare URL.
        local = get_oauth_urls(
            "custom", {"tokenUri": "http://localhost:3001/oauth/token"}
        )
        assert "network=" not in local["authorizationUri"]

    def test_unknown_environment_falls_back_to_sandbox_including_the_tier(self):
        # Pre-existing fallback (``environment`` is a hand-typed string in
        # ``create_oauth_router``); the document is now internally consistent.
        urls = get_oauth_urls("staging")  # type: ignore[arg-type]
        assert urls["tokenUri"] == "https://api.sandbox.nevermined.app/oauth/token"
        assert (
            urls["authorizationUri"]
            == "https://nevermined.app/oauth/authorize?network=sandbox"
        )

    @pytest.mark.parametrize(
        "base,expected",
        [
            (
                "https://nevermined.app/oauth/authorize",
                "https://nevermined.app/oauth/authorize?network=sandbox",
            ),
            # An existing query (blank value kept), port and fragment round-trip; an
            # existing ``network`` is replaced, not duplicated.
            (
                "https://x.example:8443/oauth/authorize?foo=&network=live#frag",
                "https://x.example:8443/oauth/authorize?foo=&network=sandbox#frag",
            ),
            # The one input urlsplit refuses falls back to concatenation (TS parity).
            (
                "http://[::1:3000/oauth/authorize",
                "http://[::1:3000/oauth/authorize?network=sandbox",
            ),
        ],
    )
    def test_with_tier_param_keeps_one_query_string(self, base, expected):
        assert _with_tier_param(base, "sandbox") == expected
        assert _with_tier_param(base, None) == base


class TestIssuerIsTheApiOriginPerTier:
    """payments-py#291: ``issuer`` used to be the frontend origin — the same string for both
    tiers — while ``token_endpoint`` and the API's own RFC 8414 document named the backend.
    Since nvm-monorepo#3532 the web app returns RFC 9207 ``iss`` = the CANONICAL API origin of
    the tier, which an RFC 9207 client compares with the discovered ``issuer`` by simple string
    comparison — so the frontend value made every RFC 9207 client that discovered through this
    server reject its codes. Hardcoded per environment so a regression to the frontend, or to
    the request host, cannot pass by mirroring the implementation."""

    CUSTOM_LOCAL = EnvironmentInfo(
        frontend="https://nevermined.app",
        backend="http://localhost:3001",
        proxy="",
        helicone_url="",
    )

    @pytest.mark.parametrize(
        "environment, backend, frontend",
        [
            ("sandbox", "https://api.sandbox.nevermined.app", "https://nevermined.app"),
            (
                "staging_sandbox",
                "https://api.sandbox.nevermined.dev",
                "https://nevermined.dev",
            ),
            ("live", "https://api.live.nevermined.app", "https://nevermined.app"),
            (
                "staging_live",
                "https://api.live.nevermined.dev",
                "https://nevermined.dev",
            ),
        ],
    )
    def test_issuer_is_the_backend_origin_never_the_frontend(
        self, environment, backend, frontend
    ):
        urls = get_oauth_urls(environment)
        assert urls["issuer"] == backend
        assert urls["issuer"] != frontend
        # Every document that describes this AS agrees on its identifier.
        config = {
            "baseUrl": "http://localhost:3000",
            "agentId": "a",
            "environment": environment,
        }
        assert build_authorization_server_metadata(config)["issuer"] == backend
        assert build_oidc_configuration(config)["issuer"] == backend

    def test_the_two_tiers_now_publish_different_issuers(self):
        assert get_oauth_urls("sandbox")["issuer"] != get_oauth_urls("live")["issuer"]
        assert (
            get_oauth_urls("staging_sandbox")["issuer"]
            != get_oauth_urls("staging_live")["issuer"]
        )

    @pytest.mark.parametrize(
        "environment, canonical",
        [
            ("sandbox", "https://api.sandbox.nevermined.app"),
            ("live", "https://api.live.nevermined.app"),
            ("staging_sandbox", "https://api.sandbox.nevermined.dev"),
            ("staging_live", "https://api.live.nevermined.dev"),
        ],
    )
    @pytest.mark.parametrize(
        "token_uri",
        [
            "https://gw.corp.com/oauth/token",  # same-tier proxy: still the same AS
            "https://api.live.nevermined.app/oauth/token",  # cross-tier: a misconfiguration
            "https://api.sandbox.nevermined.dev/oauth/token",
            "api.sandbox.nevermined.app/oauth/token",  # malformed: never a raw string
            "/oauth/token",
        ],
    )
    def test_named_environment_keeps_its_canonical_issuer_under_any_token_uri_override(
        self, environment, canonical, token_uri
    ):
        # The environment IS the identity: the web app returns ``iss`` for that tier from fixed
        # config, so a proxy in front of the token endpoint must not move the issuer — and neither
        # may a cross-tier or malformed override. (Every row is a genuine override for at least
        # three of the four environments; the tier match is what makes the cross-tier rows.)
        urls = get_oauth_urls(environment, {"tokenUri": token_uri})
        assert urls["issuer"] == canonical
        assert urls["tokenUri"] == token_uri

    @pytest.mark.parametrize(
        "token_uri, issuer",
        [
            # A branded per-org subdomain and the Commerce MCP host serve the same API as
            # ``api.<tier>.nevermined.<tld>``; the API's own document and the web app's ``iss``
            # both say the canonical origin — the only value that passes the RFC 9207 compare.
            (
                "https://acme.api.live.nevermined.app/oauth/token",
                "https://api.live.nevermined.app",
            ),
            (
                "https://mcp.api.sandbox.nevermined.dev/oauth/token",
                "https://api.sandbox.nevermined.dev",
            ),
            (
                "https://mcp.api.live.nevermined.dev/oauth/token",
                "https://api.live.nevermined.dev",
            ),
            # A trailing-dot FQDN is the same host to DNS — canonicalised, never one byte off.
            (
                "https://api.sandbox.nevermined.app./oauth/token",
                "https://api.sandbox.nevermined.app",
            ),
            (
                "HTTPS://API.Sandbox.Nevermined.app:443/oauth/token",
                "https://api.sandbox.nevermined.app",
            ),
            # A foreign host that happens to classify keeps its OWN origin — no canonical form.
            (
                "https://api.live.example.com/oauth/token",
                "https://api.live.example.com",
            ),
            (
                "https://x.api.live.example.com:8443/oauth/token",
                "https://x.api.live.example.com:8443",
            ),
            # Unclassifiable: its own origin.
            ("https://gw.corp.com/oauth/token", "https://gw.corp.com"),
        ],
    )
    def test_custom_follows_the_published_backend_canonicalised_for_nevermined_hosts(
        self, monkeypatch, token_uri, issuer
    ):
        monkeypatch.setitem(Environments, "custom", self.CUSTOM_LOCAL)
        assert get_oauth_urls("custom", {"tokenUri": token_uri})["issuer"] == issuer

    def test_custom_local_stack_issuer_is_its_own_backend(self, monkeypatch):
        monkeypatch.setitem(Environments, "custom", self.CUSTOM_LOCAL)
        assert get_oauth_urls("custom")["issuer"] == "http://localhost:3001"

    def test_custom_unparsable_override_falls_back_to_the_environment_backend_origin(
        self, monkeypatch
    ):
        monkeypatch.setitem(Environments, "custom", self.CUSTOM_LOCAL)
        assert (
            get_oauth_urls("custom", {"tokenUri": "not a url"})["issuer"]
            == "http://localhost:3001"
        )

    def test_custom_with_nothing_parsable_publishes_the_raw_string_and_warns_once(
        self, monkeypatch, caplog
    ):
        # ``localhost:3001`` parses with ``localhost`` as the SCHEME and no host: no origin
        # anywhere, so the raw string minus its trailing slash is served — loudly, once.
        from payments_py.mcp.http import oauth_metadata as om

        monkeypatch.setattr(om, "_issuer_warned", set())
        monkeypatch.setitem(
            Environments,
            "custom",
            EnvironmentInfo(
                frontend="https://nevermined.app",
                backend="localhost:3001/",
                proxy="",
                helicone_url="",
            ),
        )
        with caplog.at_level("WARNING", logger="payments_py.mcp.http.oauth_metadata"):
            assert get_oauth_urls("custom")["issuer"] == "localhost:3001"
            assert get_oauth_urls("custom")["issuer"] == "localhost:3001"
        warnings = [
            r for r in caplog.records if "Could not derive an OAuth issuer" in r.message
        ]
        assert len(warnings) == 1
        assert "oauthUrls.issuer" in warnings[0].message

    def test_custom_non_nevermined_host_warns_once_per_value_unless_overridden(
        self, monkeypatch, caplog
    ):
        # ``gw.corp.com`` / ``api.live.example.com`` have no canonical form; the derived origin is
        # right for a foreign API and WRONG for a proxy in front of the real API — the SDK cannot
        # tell, so it says what it derived and names ``oauthUrls.issuer``.
        from payments_py.mcp.http import oauth_metadata as om

        monkeypatch.setattr(om, "_issuer_warned", set())
        monkeypatch.setitem(Environments, "custom", self.CUSTOM_LOCAL)

        def proxy_warnings():
            return [
                r.message for r in caplog.records if "proxy or gateway" in r.message
            ]

        with caplog.at_level("WARNING", logger="payments_py.mcp.http.oauth_metadata"):
            urls = get_oauth_urls(
                "custom", {"tokenUri": "https://gw.corp.com/oauth/token"}
            )
            assert urls["issuer"] == "https://gw.corp.com"
            get_oauth_urls("custom", {"tokenUri": "https://gw.corp.com/oauth/token"})
            assert len(proxy_warnings()) == 1
            assert "'gw.corp.com'" in proxy_warnings()[0]
            assert "oauthUrls.issuer" in proxy_warnings()[0]
            # A DIFFERENT non-canonical value warns again (a changed typo re-alerts) …
            get_oauth_urls(
                "custom", {"tokenUri": "https://api.live.example.com/oauth/token"}
            )
            assert len(proxy_warnings()) == 2
            # … an operator who already set ``oauthUrls.issuer`` is not told to set it …
            get_oauth_urls(
                "custom",
                {
                    "tokenUri": "https://other.example.com/oauth/token",
                    "issuer": "https://api.live.nevermined.app",
                },
            )
            assert len(proxy_warnings()) == 2
            # … and a loopback stack is not a proxy.
            get_oauth_urls("custom")  # http://localhost:3001
            assert len(proxy_warnings()) == 2

    def test_unknown_environment_falls_back_to_the_sandbox_issuer(self):
        assert get_oauth_urls("staging")["issuer"] == "https://api.sandbox.nevermined.app"  # type: ignore[arg-type]

    @pytest.mark.parametrize(
        "backend, expected",
        [
            # RFC 9207 §2.4 is a simple string comparison against the ``iss`` the web app
            # returns — ``new URL(backendUrl).origin`` — so this side reduces the same way.
            (
                "HTTPS://API.Sandbox.Nevermined.app/oauth/token",
                "https://api.sandbox.nevermined.app",
            ),
            ("https://api.live.nevermined.app/", "https://api.live.nevermined.app"),
            (
                "https://api.live.nevermined.app:443/x",
                "https://api.live.nevermined.app",
            ),
            ("http://host.example:80/x", "http://host.example"),
            (
                "https://host.example:80/x",
                "https://host.example:80",
            ),  # not https's default
            ("http://host.example:443/x", "http://host.example:443"),
            (
                "https://user:pw@host.example/x",
                "https://host.example",
            ),  # never publish credentials
            ("http://localhost:3001/api/v1", "http://localhost:3001"),
            ("http://[::1]:3001/", "http://[::1]:3001"),
            # No origin: unparsable, scheme-less, scheme-only, bad port.
            ("http://[::1/", None),
            ("not a url/", None),
            ("api.sandbox.nevermined.app/oauth/token", None),
            ("localhost:3001", None),
            ("https://host.example:99999/", None),
        ],
    )
    def test_origin_of_reduces_to_a_whatwg_origin_or_none(self, backend, expected):
        assert _origin_of(backend) == expected

    def test_explicit_issuer_override_still_passes_through_untouched(self):
        urls = get_oauth_urls("sandbox", {"issuer": "https://custom-issuer.com"})
        assert urls["issuer"] == "https://custom-issuer.com"
        assert urls["tokenUri"] == "https://api.sandbox.nevermined.app/oauth/token"

    def test_override_hygiene_none_and_empty_never_replace_a_computed_value(self):
        assert (
            get_oauth_urls("sandbox", {"issuer": None})["issuer"]  # type: ignore[dict-item]
            == "https://api.sandbox.nevermined.app"
        )
        assert (
            get_oauth_urls("sandbox", {"issuer": ""})["issuer"]
            == "https://api.sandbox.nevermined.app"
        )
        assert (
            get_oauth_urls("sandbox", {"tokenUri": ""})["tokenUri"]
            == "https://api.sandbox.nevermined.app/oauth/token"
        )
        config = {
            "baseUrl": "http://localhost:3000",
            "agentId": "a",
            "environment": "sandbox",
            "oauthUrls": {"issuer": None},
        }
        assert (
            build_authorization_server_metadata(config)["issuer"]
            == "https://api.sandbox.nevermined.app"
        )
