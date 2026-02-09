"""
AgentCore Gateway Lambda interceptor for Nevermined payment protection using the x402 protocol.

This module provides an interceptor to protect AWS Bedrock AgentCore Gateway
tools with Nevermined payment verification and settlement following the x402 protocol.

Example usage (Pattern A - via payments.agentcore):
    ```python
    from payments_py import Payments, PaymentOptions

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="testing")
    )

    lambda_handler = payments.agentcore.create_lambda_handler(
        plan_id="plan-123",
    )
    ```

Example usage (Pattern B - direct import):
    ```python
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.agentcore import create_interceptor

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="testing")
    )

    interceptor = create_interceptor(
        payments=payments,
        plan_id="plan-123",
        credits=1,
    )

    def lambda_handler(event, context):
        return interceptor.handle(event, context)
    ```

For full documentation, see the interceptor module.

Installation:
    pip install payments-py
"""

from payments_py.x402.types import PaymentContext
from .interceptor import (
    AgentCoreInterceptor,
    create_interceptor,
    create_lambda_handler,
    AgentCoreAPI,
)
from .decorator import requires_payment
from .types import (
    # Configuration
    InterceptorConfig,
    InterceptorOptions,
    CreditsCallable,
    # MCP types (for advanced usage)
    MCPRequestBody,
    MCPResponseBody,
    MCPResult,
    GatewayRequest,
    GatewayResponse,
    InterceptorOutput,
)
from .helpers import (
    extract_tool_name,
    extract_credits_to_charge,
)
from .constants import (
    X402_HEADERS,
    MCP_METHODS,
)

__all__ = [
    # Main exports
    "requires_payment",
    "create_interceptor",
    "create_lambda_handler",
    "AgentCoreInterceptor",
    "PaymentContext",
    "CreditsCallable",
    "AgentCoreAPI",
    # Configuration
    "InterceptorConfig",
    "InterceptorOptions",
    # MCP types
    "MCPRequestBody",
    "MCPResponseBody",
    "MCPResult",
    "GatewayRequest",
    "GatewayResponse",
    "InterceptorOutput",
    # Helpers
    "extract_tool_name",
    "extract_credits_to_charge",
    # Constants
    "X402_HEADERS",
    "MCP_METHODS",
]
