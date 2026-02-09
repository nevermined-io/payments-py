"""
Unit tests for AgentCore x402 helper functions.
"""

import json

from payments_py.x402.agentcore.helpers import (
    encode_header,
    decode_header,
    extract_token,
    extract_tool_name,
    extract_credits_to_charge,
)
from payments_py.x402.agentcore.types import MCPRequestBody


class TestEncodeDecodeHeader:
    """Tests for encode_header and decode_header."""

    def test_encode_header(self):
        """Test encoding a dict to base64 JSON."""
        data = {"key": "value", "number": 42}
        encoded = encode_header(data)
        assert isinstance(encoded, str)
        # Decode and verify
        decoded = decode_header(encoded)
        assert decoded == data

    def test_decode_header_with_valid_data(self):
        """Test decoding valid base64 JSON."""
        import base64

        data = {"x402Version": 2, "planId": "123"}
        encoded = base64.b64encode(json.dumps(data).encode()).decode()
        decoded = decode_header(encoded)
        assert decoded == data

    def test_decode_header_with_invalid_data(self):
        """Test decoding invalid data returns empty dict."""
        assert decode_header("not-valid-base64!") == {}
        assert decode_header("") == {}


class TestExtractToken:
    """Tests for extract_token function."""

    def test_extract_token_from_standard_header(self):
        """Test extracting token from payment-signature header."""
        headers = {"payment-signature": "test-token-123"}
        token = extract_token(headers, ["payment-signature"])
        assert token == "test-token-123"

    def test_extract_token_case_insensitive(self):
        """Test that header matching is case-insensitive."""
        headers = {"PAYMENT-SIGNATURE": "test-token-123"}
        token = extract_token(headers, ["payment-signature"])
        assert token == "test-token-123"

    def test_extract_token_multiple_headers(self):
        """Test extracting token from multiple possible headers."""
        headers = {"x-custom-token": "custom-123"}
        token = extract_token(headers, ["payment-signature", "x-custom-token"])
        assert token == "custom-123"

    def test_extract_token_missing(self):
        """Test that None is returned when token is missing."""
        headers = {"other-header": "value"}
        token = extract_token(headers, ["payment-signature"])
        assert token is None

    def test_extract_token_empty_headers(self):
        """Test with empty headers dict."""
        headers = {}
        token = extract_token(headers, ["payment-signature"])
        assert token is None


class TestExtractToolName:
    """Tests for extract_tool_name function."""

    def test_extract_tool_from_prefixed_name(self):
        """Test extracting tool name from AgentCore prefixed format."""
        body = MCPRequestBody(
            method="tools/call",
            params={"name": "HealthcareTarget___getPatient", "arguments": {}},
        )
        assert extract_tool_name(body) == "getPatient"

    def test_extract_tool_from_simple_name(self):
        """Test extracting tool name without prefix."""
        body = MCPRequestBody(
            method="tools/call",
            params={"name": "getPatient", "arguments": {}},
        )
        assert extract_tool_name(body) == "getPatient"

    def test_extract_tool_non_tools_call_method(self):
        """Test that non-tools/call methods return None."""
        body = MCPRequestBody(
            method="tools/list",
            params=None,
        )
        assert extract_tool_name(body) is None

    def test_extract_tool_no_params(self):
        """Test with missing params."""
        body = MCPRequestBody(
            method="tools/call",
            params=None,
        )
        assert extract_tool_name(body) is None

    def test_extract_tool_multiple_separators(self):
        """Test with multiple ___ separators."""
        body = MCPRequestBody(
            method="tools/call",
            params={"name": "Target___Sub___toolName", "arguments": {}},
        )
        # Should return the last part
        assert extract_tool_name(body) == "toolName"


class TestExtractCreditsToCharge:
    """Tests for extract_credits_to_charge function."""

    def test_from_meta_field(self):
        """Test extracting credits from _meta.creditsToCharge."""
        body = {
            "result": {
                "content": [{"type": "text", "text": "response"}],
                "_meta": {"creditsToCharge": 5},
            }
        }
        assert extract_credits_to_charge(body) == 5

    def test_from_header(self):
        """Test extracting credits from X-Credits-To-Charge header."""
        body = {"result": {"content": []}}
        headers = {"X-Credits-To-Charge": "3"}
        assert extract_credits_to_charge(body, headers) == 3

    def test_from_header_lowercase(self):
        """Test extracting credits from lowercase header."""
        body = {"result": {"content": []}}
        headers = {"x-credits-to-charge": "7"}
        assert extract_credits_to_charge(body, headers) == 7

    def test_from_content_json(self):
        """Test extracting credits from content text JSON."""
        body = {
            "result": {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({"data": "value", "creditsToCharge": 10}),
                    }
                ]
            }
        }
        assert extract_credits_to_charge(body) == 10

    def test_from_direct_body(self):
        """Test extracting credits from direct body field."""
        body = {"creditsToCharge": 15}
        assert extract_credits_to_charge(body) == 15

    def test_default_value(self):
        """Test that default value is returned when no credits found."""
        body = {"result": {"content": []}}
        assert extract_credits_to_charge(body) == 1
        assert extract_credits_to_charge(body, {}, default=10) == 10

    def test_priority_order(self):
        """Test that _meta takes priority over other sources."""
        body = {
            "result": {
                "content": [
                    {"type": "text", "text": json.dumps({"creditsToCharge": 20})}
                ],
                "_meta": {"creditsToCharge": 5},
            },
            "creditsToCharge": 100,
        }
        headers = {"X-Credits-To-Charge": "50"}
        # _meta should take priority
        assert extract_credits_to_charge(body, headers) == 5

    def test_invalid_json_in_content(self):
        """Test handling of invalid JSON in content."""
        body = {"result": {"content": [{"type": "text", "text": "not valid json"}]}}
        assert extract_credits_to_charge(body) == 1

    def test_empty_result(self):
        """Test with empty result."""
        body = {"result": {}}
        assert extract_credits_to_charge(body) == 1

    def test_non_dict_result(self):
        """Test with non-dict result."""
        body = {"result": "string result"}
        assert extract_credits_to_charge(body) == 1
