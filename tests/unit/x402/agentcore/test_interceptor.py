"""
Unit tests for AgentCore x402 interceptor.
"""

import json
import base64
from unittest.mock import MagicMock

import pytest

from payments_py.x402.agentcore import (
    AgentCoreInterceptor,
    create_interceptor,
    create_lambda_handler,
    InterceptorConfig,
    InterceptorOptions,
    MCPRequestBody,
    X402_HEADERS,
)
from payments_py.x402.types import VerifyResponse, SettleResponse


@pytest.fixture
def mock_payments():
    """Create a mock Payments instance."""
    mock = MagicMock()

    # Mock verify_permissions
    verify_response = VerifyResponse(
        is_valid=True,
        invalid_reason=None,
        payer="0x1234567890abcdef",
        agent_request_id="test-request-id-123",
    )
    mock.facilitator.verify_permissions.return_value = verify_response

    # Mock settle_permissions
    settle_response = SettleResponse(
        success=True,
        error_reason=None,
        payer="0x1234567890abcdef",
        transaction="0xabc123",
        network="eip155:84532",
        credits_redeemed="1",
        remaining_balance="99",
    )
    mock.facilitator.settle_permissions.return_value = settle_response

    return mock


@pytest.fixture
def valid_token():
    """Create a valid test token."""
    return "test-x402-token-123"


@pytest.fixture
def request_event():
    """Create a REQUEST phase event."""
    return {
        "mcp": {
            "gatewayRequest": {
                "headers": {"Content-Type": "application/json"},
                "body": {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "method": "tools/call",
                    "params": {"name": "Target1___getPatient", "arguments": {"id": "123"}},
                },
            }
        }
    }


@pytest.fixture
def request_event_with_token(request_event, valid_token):
    """Create a REQUEST phase event with payment token."""
    request_event["mcp"]["gatewayRequest"]["headers"]["payment-signature"] = valid_token
    return request_event


@pytest.fixture
def response_event(request_event_with_token):
    """Create a RESPONSE phase event."""
    return {
        "mcp": {
            "gatewayRequest": request_event_with_token["mcp"]["gatewayRequest"],
            "gatewayResponse": {
                "headers": {"Content-Type": "application/json"},
                "body": {
                    "jsonrpc": "2.0",
                    "id": "1",
                    "result": {
                        "content": [{"type": "text", "text": '{"patientId": "123"}'}],
                        "_meta": {"creditsToCharge": 2},
                    },
                },
                "statusCode": 200,
            },
        }
    }


class TestAgentCoreInterceptor:
    """Tests for AgentCoreInterceptor class."""

    def test_requires_plan_id_or_tools(self, mock_payments):
        """Test that either plan_id or tools must be provided."""
        with pytest.raises(ValueError, match="Either plan_id or tools"):
            AgentCoreInterceptor(payments=mock_payments)

    def test_initialization_with_plan_id(self, mock_payments):
        """Test initialization with plan_id."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan-123",
        )
        assert interceptor.default_config is not None
        assert interceptor.default_config.plan_id == "test-plan-123"

    def test_initialization_with_tools(self, mock_payments):
        """Test initialization with per-tool configs."""
        tools = {
            "getPatient": InterceptorConfig(plan_id="plan-1", credits=1),
            "bookAppointment": InterceptorConfig(plan_id="plan-2", credits=5),
        }
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            tools=tools,
        )
        assert len(interceptor.tools) == 2
        assert interceptor.get_config("getPatient").credits == 1
        assert interceptor.get_config("bookAppointment").credits == 5


class TestRequestPhase:
    """Tests for REQUEST phase handling."""

    def test_non_billable_method_passes_through(self, mock_payments):
        """Test that non-billable methods are forwarded."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        event = {
            "mcp": {
                "gatewayRequest": {
                    "headers": {},
                    "body": {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/list",
                        "params": None,
                    },
                }
            }
        }

        result = interceptor.handle(event)
        assert "transformedGatewayRequest" in result["mcp"]
        # Verify that verify_permissions was NOT called
        mock_payments.facilitator.verify_permissions.assert_not_called()

    def test_returns_402_without_token(self, mock_payments, request_event):
        """Test that 402 is returned when no token is provided."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(request_event)

        assert "transformedGatewayResponse" in result["mcp"]
        response = result["mcp"]["transformedGatewayResponse"]
        assert response["statusCode"] == 200  # AgentCore uses 200 with isError
        assert response["body"]["result"]["isError"] is True
        assert response["body"]["result"]["_meta"]["x402"] is True
        assert X402_HEADERS["PAYMENT_REQUIRED"] in response["headers"]

    def test_forwards_request_with_valid_token(
        self, mock_payments, request_event_with_token
    ):
        """Test that request is forwarded with valid token."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(request_event_with_token)

        assert "transformedGatewayRequest" in result["mcp"]
        mock_payments.facilitator.verify_permissions.assert_called_once()

    def test_returns_402_when_verification_fails(
        self, mock_payments, request_event_with_token
    ):
        """Test that 402 is returned when verification fails."""
        mock_payments.facilitator.verify_permissions.return_value = VerifyResponse(
            is_valid=False,
            invalid_reason="Insufficient credits",
        )

        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(request_event_with_token)

        assert "transformedGatewayResponse" in result["mcp"]
        body = result["mcp"]["transformedGatewayResponse"]["body"]
        assert body["result"]["isError"] is True


class TestResponsePhase:
    """Tests for RESPONSE phase handling."""

    def test_settles_payment_on_success(self, mock_payments, response_event):
        """Test that payment is settled on successful response."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(response_event)

        assert "transformedGatewayResponse" in result["mcp"]
        response = result["mcp"]["transformedGatewayResponse"]

        # Verify settle was called
        mock_payments.facilitator.settle_permissions.assert_called_once()

        # Verify payment-response header is present
        assert X402_HEADERS["PAYMENT_RESPONSE"] in response["headers"]

        # Decode and verify payment response
        payment_response = json.loads(
            base64.b64decode(response["headers"][X402_HEADERS["PAYMENT_RESPONSE"]])
        )
        assert payment_response["success"] is True

    def test_uses_credits_from_response_meta(self, mock_payments, response_event):
        """Test that creditsToCharge from _meta is used for settlement."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(response_event)

        # The response has _meta.creditsToCharge = 2
        call_args = mock_payments.facilitator.settle_permissions.call_args
        assert call_args.kwargs["max_amount"] == "2"

    def test_skips_settlement_on_non_200_response(self, mock_payments, response_event):
        """Test that settlement is skipped for non-200 responses."""
        response_event["mcp"]["gatewayResponse"]["statusCode"] = 500

        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(response_event)

        # Verify settle was NOT called
        mock_payments.facilitator.settle_permissions.assert_not_called()

    def test_skips_settlement_without_token(self, mock_payments):
        """Test that settlement is skipped when original request had no token."""
        event = {
            "mcp": {
                "gatewayRequest": {
                    "headers": {},  # No token
                    "body": {
                        "jsonrpc": "2.0",
                        "id": "1",
                        "method": "tools/call",
                        "params": {"name": "getPatient", "arguments": {}},
                    },
                },
                "gatewayResponse": {
                    "headers": {},
                    "body": {"jsonrpc": "2.0", "id": "1", "result": {"content": []}},
                    "statusCode": 200,
                },
            }
        }

        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = interceptor.handle(event)

        # Verify settle was NOT called
        mock_payments.facilitator.settle_permissions.assert_not_called()


class TestMockMode:
    """Tests for mock mode functionality."""

    def test_mock_mode_skips_verification(self, mock_payments, request_event_with_token):
        """Test that mock mode skips Nevermined verification."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
            options=InterceptorOptions(mock_mode=True),
        )

        result = interceptor.handle(request_event_with_token)

        assert "transformedGatewayRequest" in result["mcp"]
        # Verify that verify_permissions was NOT called
        mock_payments.facilitator.verify_permissions.assert_not_called()

    def test_mock_mode_returns_mock_settlement(self, mock_payments, response_event):
        """Test that mock mode returns mock settlement."""
        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
            options=InterceptorOptions(mock_mode=True),
        )

        result = interceptor.handle(response_event)

        # Verify settle was NOT called
        mock_payments.facilitator.settle_permissions.assert_not_called()

        # Verify payment-response header is present with mock data
        response = result["mcp"]["transformedGatewayResponse"]
        assert X402_HEADERS["PAYMENT_RESPONSE"] in response["headers"]

        payment_response = json.loads(
            base64.b64decode(response["headers"][X402_HEADERS["PAYMENT_RESPONSE"]])
        )
        assert payment_response["success"] is True
        assert "mock" in payment_response["transactionHash"]


class TestDynamicCredits:
    """Tests for dynamic credits calculation."""

    def test_callable_credits(self, mock_payments, request_event_with_token):
        """Test that callable credits function works."""

        def calculate_credits(request: MCPRequestBody) -> int:
            return 3

        interceptor = AgentCoreInterceptor(
            payments=mock_payments,
            plan_id="test-plan",
            credits=calculate_credits,
        )

        result = interceptor.handle(request_event_with_token)

        assert "transformedGatewayRequest" in result["mcp"]
        call_args = mock_payments.facilitator.verify_permissions.call_args
        assert call_args.kwargs["max_amount"] == "3"


class TestFactoryFunctions:
    """Tests for factory functions."""

    def test_create_interceptor(self, mock_payments):
        """Test create_interceptor factory function."""
        interceptor = create_interceptor(
            payments=mock_payments,
            plan_id="test-plan",
            credits=5,
        )

        assert isinstance(interceptor, AgentCoreInterceptor)
        assert interceptor.default_config.credits == 5

    def test_create_lambda_handler(self, mock_payments):
        """Test create_lambda_handler factory function."""
        handler = create_lambda_handler(
            payments=mock_payments,
            plan_id="test-plan",
        )

        assert callable(handler)

    def test_create_lambda_handler_is_working(
        self, mock_payments, request_event_with_token
    ):
        """Test that handler returned by create_lambda_handler works."""
        handler = create_lambda_handler(
            payments=mock_payments,
            plan_id="test-plan",
        )

        result = handler(request_event_with_token, None)

        assert "transformedGatewayRequest" in result["mcp"]


class TestInterceptorConfig:
    """Tests for InterceptorConfig dataclass."""

    def test_default_values(self):
        """Test InterceptorConfig default values."""
        config = InterceptorConfig(plan_id="test-plan")
        assert config.plan_id == "test-plan"
        assert config.credits == 1
        assert config.agent_id is None
        assert config.network == "eip155:84532"

    def test_custom_values(self):
        """Test InterceptorConfig with custom values."""
        config = InterceptorConfig(
            plan_id="custom-plan",
            credits=10,
            agent_id="agent-123",
            network="eip155:1",
            description="Test config",
        )
        assert config.plan_id == "custom-plan"
        assert config.credits == 10
        assert config.agent_id == "agent-123"
        assert config.network == "eip155:1"
        assert config.description == "Test config"


class TestInterceptorOptions:
    """Tests for InterceptorOptions dataclass."""

    def test_default_values(self):
        """Test InterceptorOptions default values."""
        options = InterceptorOptions()
        assert options.token_header == ["payment-signature", "PAYMENT-SIGNATURE"]
        assert options.billable_methods == ["tools/call"]
        assert options.default_credits == 1
        assert options.mock_mode is False
        assert options.on_before_verify is None

    def test_custom_values(self):
        """Test InterceptorOptions with custom values."""
        options = InterceptorOptions(
            token_header="X-Custom-Token",
            billable_methods=["tools/call", "resources/read"],
            mock_mode=True,
        )
        assert options.token_header == "X-Custom-Token"
        assert "resources/read" in options.billable_methods
        assert options.mock_mode is True


class TestPaymentsAgentCoreProperty:
    """Tests for payments.agentcore property."""

    def test_agentcore_property_creates_interceptor(self, mock_payments):
        """Test that payments.agentcore.create_interceptor works."""
        # Create a minimal Payments mock with the agentcore property
        from payments_py.x402.agentcore import _AgentCoreAPI

        api = _AgentCoreAPI(mock_payments)
        interceptor = api.create_interceptor(plan_id="test-plan")

        assert isinstance(interceptor, AgentCoreInterceptor)

    def test_agentcore_property_creates_handler(self, mock_payments):
        """Test that payments.agentcore.create_lambda_handler works."""
        from payments_py.x402.agentcore import _AgentCoreAPI

        api = _AgentCoreAPI(mock_payments)
        handler = api.create_lambda_handler(plan_id="test-plan")

        assert callable(handler)
