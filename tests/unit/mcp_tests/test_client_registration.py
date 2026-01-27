"""
Unit tests for OAuth Dynamic Client Registration (RFC 7591).

These tests verify the client registration functionality
following the OAuth 2.0 Dynamic Client Registration Protocol.
"""

import pytest

from payments_py.mcp.http.client_registration import (
    ClientRegistrationError,
    is_client_registration_request,
    process_client_registration,
    validate_client_registration_request,
)


class TestIsClientRegistrationRequest:
    """Tests for is_client_registration_request function."""

    def test_returns_true_for_request_with_redirect_uris(self):
        """Should return True for request with redirect_uris."""
        assert is_client_registration_request(
            {"redirect_uris": ["http://localhost:3000/callback"]}
        )

    def test_returns_true_for_request_with_grant_types(self):
        """Should return True for request with grant_types."""
        assert is_client_registration_request({"grant_types": ["authorization_code"]})

    def test_returns_true_for_request_with_token_endpoint_auth_method(self):
        """Should return True for request with token_endpoint_auth_method."""
        assert is_client_registration_request({"token_endpoint_auth_method": "none"})

    def test_returns_true_for_request_with_client_name(self):
        """Should return True for request with client_name."""
        assert is_client_registration_request({"client_name": "My App"})

    def test_returns_false_for_empty_dict(self):
        """Should return False for empty dict."""
        assert not is_client_registration_request({})

    def test_returns_false_for_none(self):
        """Should return False for None."""
        assert not is_client_registration_request(None)

    def test_returns_false_for_non_dict(self):
        """Should return False for non-dict values."""
        assert not is_client_registration_request("string")
        assert not is_client_registration_request(123)
        assert not is_client_registration_request([])


class TestValidateClientRegistrationRequest:
    """Tests for validate_client_registration_request function."""

    def test_validates_request_with_redirect_uris(self):
        """Should validate request with valid redirect_uris."""
        # Should not raise
        validate_client_registration_request(
            {"redirect_uris": ["http://localhost:3000/callback"]}
        )

    def test_raises_when_redirect_uris_missing(self):
        """Should raise when redirect_uris is missing."""
        with pytest.raises(ClientRegistrationError) as exc_info:
            validate_client_registration_request({})

        assert exc_info.value.error_code == "invalid_request"
        assert "redirect_uris" in str(exc_info.value)

    def test_raises_when_redirect_uris_empty(self):
        """Should raise when redirect_uris is empty."""
        with pytest.raises(ClientRegistrationError) as exc_info:
            validate_client_registration_request({"redirect_uris": []})

        assert exc_info.value.error_code == "invalid_request"

    def test_raises_when_redirect_uri_invalid_url(self):
        """Should raise when redirect_uri is invalid URL."""
        with pytest.raises(ClientRegistrationError) as exc_info:
            validate_client_registration_request({"redirect_uris": ["not-a-valid-url"]})

        assert exc_info.value.error_code == "invalid_redirect_uri"

    def test_validates_multiple_redirect_uris(self):
        """Should validate multiple valid redirect_uris."""
        # Should not raise
        validate_client_registration_request(
            {
                "redirect_uris": [
                    "http://localhost:3000/callback",
                    "https://example.com/oauth/callback",
                ]
            }
        )

    def test_raises_when_grant_type_invalid(self):
        """Should raise when grant_type is invalid."""
        with pytest.raises(ClientRegistrationError) as exc_info:
            validate_client_registration_request(
                {
                    "redirect_uris": ["http://localhost:3000/callback"],
                    "grant_types": ["invalid_grant"],
                }
            )

        assert exc_info.value.error_code == "invalid_client_metadata"
        assert "grant_type" in str(exc_info.value)

    def test_validates_supported_grant_types(self):
        """Should validate supported grant types."""
        # Should not raise
        validate_client_registration_request(
            {
                "redirect_uris": ["http://localhost:3000/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
            }
        )

    def test_raises_when_response_type_invalid(self):
        """Should raise when response_type is invalid."""
        with pytest.raises(ClientRegistrationError) as exc_info:
            validate_client_registration_request(
                {
                    "redirect_uris": ["http://localhost:3000/callback"],
                    "response_types": ["invalid_response"],
                }
            )

        assert exc_info.value.error_code == "invalid_client_metadata"
        assert "response_type" in str(exc_info.value)

    def test_raises_when_auth_method_invalid(self):
        """Should raise when token_endpoint_auth_method is invalid."""
        with pytest.raises(ClientRegistrationError) as exc_info:
            validate_client_registration_request(
                {
                    "redirect_uris": ["http://localhost:3000/callback"],
                    "token_endpoint_auth_method": "invalid_method",
                }
            )

        assert exc_info.value.error_code == "invalid_client_metadata"


class TestProcessClientRegistration:
    """Tests for process_client_registration function."""

    @pytest.fixture
    def base_config(self):
        """Base OAuth configuration for tests."""
        return {
            "baseUrl": "http://localhost:3000",
            "agentId": "unit_agent_id_hex",
            "environment": "sandbox",
        }

    @pytest.mark.asyncio
    async def test_returns_client_id_as_agent_id(self, base_config):
        """Should return client_id as agentId."""
        response = await process_client_registration(
            {"redirect_uris": ["http://localhost:3000/callback"]},
            base_config,
        )

        assert response["client_id"] == "unit_agent_id_hex"

    @pytest.mark.asyncio
    async def test_returns_redirect_uris(self, base_config):
        """Should return redirect_uris from request."""
        redirect_uris = [
            "http://localhost:3000/callback",
            "https://example.com/callback",
        ]
        response = await process_client_registration(
            {"redirect_uris": redirect_uris},
            base_config,
        )

        assert response["redirect_uris"] == redirect_uris

    @pytest.mark.asyncio
    async def test_returns_default_grant_types(self, base_config):
        """Should return default grant_types when not provided."""
        response = await process_client_registration(
            {"redirect_uris": ["http://localhost:3000/callback"]},
            base_config,
        )

        assert response["grant_types"] == ["authorization_code"]

    @pytest.mark.asyncio
    async def test_returns_custom_grant_types(self, base_config):
        """Should return custom grant_types when provided."""
        response = await process_client_registration(
            {
                "redirect_uris": ["http://localhost:3000/callback"],
                "grant_types": ["authorization_code", "refresh_token"],
            },
            base_config,
        )

        assert response["grant_types"] == ["authorization_code", "refresh_token"]

    @pytest.mark.asyncio
    async def test_returns_default_response_types(self, base_config):
        """Should return default response_types when not provided."""
        response = await process_client_registration(
            {"redirect_uris": ["http://localhost:3000/callback"]},
            base_config,
        )

        assert response["response_types"] == ["code"]

    @pytest.mark.asyncio
    async def test_returns_client_issued_at(self, base_config):
        """Should return client_id_issued_at timestamp."""
        response = await process_client_registration(
            {"redirect_uris": ["http://localhost:3000/callback"]},
            base_config,
        )

        assert "client_id_issued_at" in response
        assert isinstance(response["client_id_issued_at"], int)
        assert response["client_id_issued_at"] > 0

    @pytest.mark.asyncio
    async def test_returns_scope_string(self, base_config):
        """Should return scope as space-separated string."""
        response = await process_client_registration(
            {"redirect_uris": ["http://localhost:3000/callback"]},
            base_config,
        )

        assert "scope" in response
        assert isinstance(response["scope"], str)
        assert " " in response["scope"]  # Space-separated

    @pytest.mark.asyncio
    async def test_no_client_secret_for_none_auth_method(self, base_config):
        """Should not return client_secret for 'none' auth method."""
        response = await process_client_registration(
            {
                "redirect_uris": ["http://localhost:3000/callback"],
                "token_endpoint_auth_method": "none",
            },
            base_config,
        )

        assert "client_secret" not in response

    @pytest.mark.asyncio
    async def test_returns_client_secret_for_client_secret_post(self, base_config):
        """Should return client_secret for 'client_secret_post' auth method."""
        response = await process_client_registration(
            {
                "redirect_uris": ["http://localhost:3000/callback"],
                "token_endpoint_auth_method": "client_secret_post",
            },
            base_config,
        )

        assert "client_secret" in response
        assert len(response["client_secret"]) > 0
        assert response["client_secret_expires_at"] == 0  # Never expires

    @pytest.mark.asyncio
    async def test_returns_client_name(self, base_config):
        """Should return client_name from request or default."""
        # With custom name
        response1 = await process_client_registration(
            {
                "redirect_uris": ["http://localhost:3000/callback"],
                "client_name": "My Custom App",
            },
            base_config,
        )
        assert response1["client_name"] == "My Custom App"

        # With default name
        response2 = await process_client_registration(
            {"redirect_uris": ["http://localhost:3000/callback"]},
            base_config,
        )
        assert response2["client_name"] == "MCP Client"

    @pytest.mark.asyncio
    async def test_includes_optional_fields(self, base_config):
        """Should include optional fields when provided."""
        response = await process_client_registration(
            {
                "redirect_uris": ["http://localhost:3000/callback"],
                "client_uri": "https://example.com",
                "logo_uri": "https://example.com/logo.png",
                "contacts": ["admin@example.com"],
            },
            base_config,
        )

        assert response["client_uri"] == "https://example.com"
        assert response["logo_uri"] == "https://example.com/logo.png"
        assert response["contacts"] == ["admin@example.com"]


class TestClientRegistrationError:
    """Tests for ClientRegistrationError exception."""

    def test_stores_error_code_and_message(self):
        """Should store error code and message."""
        error = ClientRegistrationError("invalid_request", "Missing redirect_uris")

        assert error.error_code == "invalid_request"
        assert str(error) == "Missing redirect_uris"

    def test_default_status_code_is_400(self):
        """Should have default status code of 400."""
        error = ClientRegistrationError("invalid_request", "Error message")

        assert error.status_code == 400

    def test_custom_status_code(self):
        """Should allow custom status code."""
        error = ClientRegistrationError(
            "server_error", "Internal error", status_code=500
        )

        assert error.status_code == 500

    def test_to_json_returns_error_response(self):
        """Should return proper error response dict."""
        error = ClientRegistrationError("invalid_redirect_uri", "Bad URI")

        json_response = error.to_json()

        assert json_response == {
            "error": "invalid_redirect_uri",
            "error_description": "Bad URI",
        }
