"""
Unit tests for AgentCore x402 types.
"""

import pytest
from pydantic import ValidationError

from payments_py.x402.agentcore.types import (
    MCPParams,
    MCPRequestBody,
    MCPContentItem,
    MCPResult,
    MCPResponseBody,
    GatewayRequest,
    GatewayResponse,
    InterceptorEvent,
    InterceptorOutput,
)


class TestMCPParams:
    """Tests for MCPParams model."""

    def test_basic_creation(self):
        """Test basic MCPParams creation."""
        params = MCPParams(name="getPatient", arguments={"id": "123"})
        assert params.name == "getPatient"
        assert params.arguments == {"id": "123"}

    def test_default_arguments(self):
        """Test default empty arguments."""
        params = MCPParams(name="listTools")
        assert params.arguments == {}

    def test_allows_extra_fields(self):
        """Test that extra fields are allowed."""
        params = MCPParams(name="test", arguments={}, extra_field="allowed")
        assert params.model_extra.get("extra_field") == "allowed"


class TestMCPRequestBody:
    """Tests for MCPRequestBody model."""

    def test_tools_call_request(self):
        """Test tools/call request body."""
        body = MCPRequestBody(
            jsonrpc="2.0",
            id="1",
            method="tools/call",
            params={"name": "getPatient", "arguments": {"id": "123"}},
        )
        assert body.method == "tools/call"
        assert body.params.name == "getPatient"

    def test_tools_list_request(self):
        """Test tools/list request without params."""
        body = MCPRequestBody(
            jsonrpc="2.0",
            id="1",
            method="tools/list",
        )
        assert body.method == "tools/list"
        assert body.params is None

    def test_string_id(self):
        """Test request with string ID."""
        body = MCPRequestBody(
            method="tools/call",
            id="request-123",
        )
        assert body.id == "request-123"

    def test_integer_id(self):
        """Test request with integer ID."""
        body = MCPRequestBody(
            method="tools/call",
            id=42,
        )
        assert body.id == 42


class TestMCPContentItem:
    """Tests for MCPContentItem model."""

    def test_text_content(self):
        """Test text content item."""
        item = MCPContentItem(type="text", text="Hello, world!")
        assert item.type == "text"
        assert item.text == "Hello, world!"

    def test_default_type(self):
        """Test default content type is text."""
        item = MCPContentItem()
        assert item.type == "text"


class TestMCPResult:
    """Tests for MCPResult model."""

    def test_success_result(self):
        """Test successful result."""
        result = MCPResult(
            content=[MCPContentItem(type="text", text="result")],
            is_error=False,
        )
        assert len(result.content) == 1
        assert result.is_error is False

    def test_error_result(self):
        """Test error result."""
        result = MCPResult(
            content=[MCPContentItem(type="text", text="error message")],
            is_error=True,
        )
        assert result.is_error is True

    def test_alias_is_error(self):
        """Test isError alias."""
        data = {"content": [], "isError": True}
        result = MCPResult.model_validate(data)
        assert result.is_error is True


class TestMCPResponseBody:
    """Tests for MCPResponseBody model."""

    def test_success_response(self):
        """Test successful response body."""
        body = MCPResponseBody(
            jsonrpc="2.0",
            id="1",
            result=MCPResult(content=[]),
        )
        assert body.result is not None
        assert body.error is None

    def test_error_response(self):
        """Test error response body."""
        body = MCPResponseBody(
            jsonrpc="2.0",
            id="1",
            error={"code": -32600, "message": "Invalid request"},
        )
        assert body.result is None
        assert body.error is not None


class TestGatewayRequest:
    """Tests for GatewayRequest model."""

    def test_basic_request(self):
        """Test basic gateway request."""
        request = GatewayRequest(
            headers={"Content-Type": "application/json"},
            body=MCPRequestBody(method="tools/call"),
        )
        assert request.headers["Content-Type"] == "application/json"
        assert request.body.method == "tools/call"

    def test_from_dict(self):
        """Test parsing from dict (as received from Lambda)."""
        data = {
            "headers": {"payment-signature": "token-123"},
            "body": {
                "jsonrpc": "2.0",
                "id": "1",
                "method": "tools/call",
                "params": {"name": "test", "arguments": {}},
            },
        }
        request = GatewayRequest.model_validate(data)
        assert request.headers["payment-signature"] == "token-123"
        assert request.body.params.name == "test"


class TestGatewayResponse:
    """Tests for GatewayResponse model."""

    def test_success_response(self):
        """Test successful gateway response."""
        response = GatewayResponse(
            headers={"Content-Type": "application/json"},
            body={"jsonrpc": "2.0", "id": "1", "result": {"content": []}},
            status_code=200,
        )
        assert response.status_code == 200

    def test_alias_status_code(self):
        """Test statusCode alias."""
        data = {
            "headers": {},
            "body": {},
            "statusCode": 500,
        }
        response = GatewayResponse.model_validate(data)
        assert response.status_code == 500


class TestInterceptorEvent:
    """Tests for InterceptorEvent model."""

    def test_request_phase_event(self):
        """Test REQUEST phase event (only gatewayRequest)."""
        data = {
            "gatewayRequest": {
                "headers": {},
                "body": {"jsonrpc": "2.0", "id": "1", "method": "tools/call"},
            }
        }
        event = InterceptorEvent.model_validate(data)
        assert event.gateway_request is not None
        assert event.gateway_response is None

    def test_response_phase_event(self):
        """Test RESPONSE phase event (both request and response)."""
        data = {
            "gatewayRequest": {
                "headers": {},
                "body": {"jsonrpc": "2.0", "id": "1", "method": "tools/call"},
            },
            "gatewayResponse": {
                "headers": {},
                "body": {"jsonrpc": "2.0", "id": "1", "result": {}},
                "statusCode": 200,
            },
        }
        event = InterceptorEvent.model_validate(data)
        assert event.gateway_request is not None
        assert event.gateway_response is not None


class TestInterceptorOutput:
    """Tests for InterceptorOutput model."""

    def test_request_phase_output(self):
        """Test REQUEST phase output (transformedGatewayRequest)."""
        output = InterceptorOutput(
            interceptor_output_version="1.0",
            mcp={
                "transformedGatewayRequest": {
                    "headers": {},
                    "body": {},
                }
            },
        )
        assert output.interceptor_output_version == "1.0"
        assert "transformedGatewayRequest" in output.mcp

    def test_response_phase_output(self):
        """Test RESPONSE phase output (transformedGatewayResponse)."""
        output = InterceptorOutput(
            mcp={
                "transformedGatewayResponse": {
                    "statusCode": 200,
                    "headers": {},
                    "body": {},
                }
            },
        )
        assert "transformedGatewayResponse" in output.mcp

    def test_serialization_with_alias(self):
        """Test that serialization uses camelCase aliases."""
        output = InterceptorOutput(
            interceptor_output_version="1.0",
            mcp={"transformedGatewayRequest": {"headers": {}, "body": {}}},
        )
        dumped = output.model_dump(by_alias=True)
        assert "interceptorOutputVersion" in dumped
        assert dumped["interceptorOutputVersion"] == "1.0"
