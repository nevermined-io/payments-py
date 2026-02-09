"""
AgentCore x402 Interceptor.

Main interceptor class for protecting AgentCore Gateway tools with
Nevermined payments using the x402 protocol.
"""

import logging
import asyncio
import inspect
from typing import Any, Dict, Optional, Union, TYPE_CHECKING, Callable

from payments_py.x402.helpers import build_payment_required

from .types import (
    InterceptorConfig,
    InterceptorOptions,
    GatewayRequest,
    MCPRequestBody,
    CreditsCallable,
)
from .helpers import (
    extract_token,
    extract_tool_name,
    extract_credits_to_charge,
    build_402_response,
    build_success_response,
    forward_request,
    forward_response,
)

if TYPE_CHECKING:
    from payments_py import Payments

logger = logging.getLogger(__name__)


class AgentCoreInterceptor:
    """
    AWS Lambda interceptor for AgentCore Gateway x402 payments.

    Handles payment verification (REQUEST phase) and settlement (RESPONSE phase)
    for MCP tools protected by Nevermined payment plans.

    Note: This class is typically instantiated via `payments.agentcore.create_interceptor()`.

    Example - Via Payments instance (recommended):
        ```python
        from payments_py import Payments, PaymentOptions

        payments = Payments.get_instance(
            PaymentOptions(nvm_api_key=os.environ["NVM_API_KEY"])
        )

        interceptor = payments.agentcore.create_interceptor(
            plan_id=os.environ["NVM_PLAN_ID"],
        )

        def lambda_handler(event, context):
            return interceptor.handle(event, context)
        ```

    Example - One-liner handler:
        ```python
        lambda_handler = payments.agentcore.create_lambda_handler(
            plan_id=os.environ["NVM_PLAN_ID"],
        )
        ```

    Example - Per-tool configuration:
        ```python
        interceptor = payments.agentcore.create_interceptor(
            tools={
                "getPatient": InterceptorConfig(plan_id="123", credits=1),
                "bookAppointment": InterceptorConfig(plan_id="123", credits=5),
            },
        )
        ```

    Example - Dynamic credits:
        ```python
        def calculate_credits(request):
            args = request.params.arguments if request.params else {}
            return 2 if args.get("detailed") else 1

        interceptor = payments.agentcore.create_interceptor(
            plan_id="123",
            credits=calculate_credits,
        )
        ```

    Example - With hooks:
        ```python
        async def on_settle(request, credits, result):
            print(f"Settled {credits} credits")

        interceptor = payments.agentcore.create_interceptor(
            plan_id="123",
            options=InterceptorOptions(on_after_settle=on_settle),
        )
        ```
    """

    def __init__(
        self,
        payments: "Payments",
        plan_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        credits: Union[int, CreditsCallable] = 1,
        endpoint: Optional[str] = None,
        network: str = "eip155:84532",
        description: Optional[str] = None,
        tools: Optional[Dict[str, InterceptorConfig]] = None,
        options: Optional[InterceptorOptions] = None,
    ):
        """
        Initialize the AgentCore interceptor.

        Args:
            payments: Payments instance (provides API key and environment)
            plan_id: Default plan ID for all tools (required if tools not specified)
            agent_id: Optional agent ID
            credits: Default credits per request (int or callable)
            endpoint: Protected resource endpoint URL
            network: Blockchain network in CAIP-2 format
            description: Description for 402 responses
            tools: Per-tool configuration (overrides defaults)
            options: Global interceptor options
        """
        self._payments = payments
        self.options = options or InterceptorOptions()

        # Per-tool configs
        self.tools = tools or {}

        # Default config for tools not in self.tools
        self.default_config = (
            InterceptorConfig(
                plan_id=plan_id or "",
                agent_id=agent_id,
                credits=credits,
                endpoint=endpoint,
                network=network,
                description=description,
            )
            if plan_id
            else None
        )

        # Validate configuration
        if not plan_id and not tools:
            raise ValueError("Either plan_id or tools configuration is required")

        logger.info(
            f"AgentCoreInterceptor initialized, "
            f"tools configured: {list(self.tools.keys()) if self.tools else 'all (default)'}"
        )

    @property
    def payments(self) -> "Payments":
        """Access to Payments instance."""
        return self._payments

    def get_config(self, tool_name: Optional[str]) -> Optional[InterceptorConfig]:
        """Get configuration for a specific tool."""
        if tool_name and tool_name in self.tools:
            return self.tools[tool_name]
        return self.default_config

    def _resolve_endpoint(
        self,
        config: InterceptorConfig,
        gateway_request: dict,
        context: Any = None,
    ) -> Optional[str]:
        """
        Resolve the endpoint for payment required.

        Priority:
        1. config.endpoint (explicitly configured)
        2. context.invoked_function_arn (Lambda ARN)
        """
        # 1. Explicitly configured
        if config.endpoint:
            return config.endpoint

        # 2. Lambda ARN from context
        if context and hasattr(context, "invoked_function_arn"):
            return context.invoked_function_arn

        return None

    def handle(self, event: dict, context: Any = None) -> dict:
        """
        Main Lambda handler entry point.

        Determines the interception phase (REQUEST or RESPONSE) and
        delegates to the appropriate handler.

        Args:
            event: Lambda event from AgentCore Gateway
            context: Lambda context (optional)

        Returns:
            Interceptor output dict for AgentCore Gateway
        """
        logger.info("Interceptor event received")

        try:
            mcp = event.get("mcp", {})
            gateway_response = mcp.get("gatewayResponse")
            gateway_request = mcp.get("gatewayRequest")

            if gateway_response is not None and gateway_response:
                logger.info("RESPONSE phase: handling settlement")
                return self._handle_response(event, context)
            elif gateway_request is not None:
                logger.info("REQUEST phase: handling verification")
                return self._handle_request(event, context)
            else:
                logger.warning(f"Unknown event structure: {list(mcp.keys())}")
                return {"statusCode": 200, "body": "OK"}

        except Exception as e:
            logger.error(f"Interceptor error: {e}", exc_info=True)
            # Return a generic error - don't expose internal details
            return forward_response(
                {"Content-Type": "application/json"},
                {"error": "Internal interceptor error"},
                500,
            ).model_dump(by_alias=True)

    def _handle_request(self, event: dict, context: Any = None) -> dict:
        """
        Handle REQUEST phase interception.

        1. Check if request is billable
        2. Extract payment token from headers
        3. Verify token with Nevermined
        4. Return 402 or forward request
        """
        mcp = event.get("mcp", {})
        gateway_request = mcp.get("gatewayRequest", {})
        headers = gateway_request.get("headers", {})
        body = gateway_request.get("body", {})

        rpc_id = body.get("id", "1")
        method = body.get("method", "")

        # Check if billable
        if method not in self.options.billable_methods:
            logger.info(f"Non-billable method: {method}")
            return forward_request(headers, body).model_dump(by_alias=True)

        # Get tool config
        tool_name = extract_tool_name(MCPRequestBody.model_validate(body))
        config = self.get_config(tool_name)

        if not config:
            logger.warning(f"No config for tool: {tool_name}")
            return forward_request(headers, body).model_dump(by_alias=True)

        logger.info(f"Billable request for tool: {tool_name}")

        # Resolve endpoint
        endpoint = self._resolve_endpoint(config, gateway_request, context)

        # Build payment required
        payment_required = build_payment_required(
            plan_id=config.plan_id,
            agent_id=config.agent_id,
            endpoint=endpoint,
            http_verb="POST",
            network=config.network,
            description=config.description,
        )

        # Extract token
        token_headers = (
            [self.options.token_header]
            if isinstance(self.options.token_header, str)
            else self.options.token_header
        )
        token = extract_token(headers, token_headers)

        if not token:
            logger.info("No payment token, returning 402")
            return build_402_response(
                payment_required, rpc_id, f"Payment required for tool: {tool_name}"
            ).model_dump(by_alias=True)

        # Verify payment
        try:
            # Resolve credits
            credits = self._resolve_credits_sync(config.credits, body)

            # Call before_verify hook
            if self.options.on_before_verify:
                self._run_hook(
                    self.options.on_before_verify,
                    GatewayRequest.model_validate(gateway_request),
                    payment_required,
                )

            # Verify with Nevermined
            verification = self.payments.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=token,
                max_amount=str(credits),
            )

            if not verification.is_valid:
                logger.warning(f"Verification failed: {verification.invalid_reason}")
                return build_402_response(
                    payment_required,
                    rpc_id,
                    verification.invalid_reason or "Payment verification failed",
                ).model_dump(by_alias=True)

            # Call after_verify hook
            if self.options.on_after_verify:
                self._run_hook(
                    self.options.on_after_verify,
                    GatewayRequest.model_validate(gateway_request),
                    verification,
                )

            logger.info("Payment verified, forwarding request")
            return forward_request(headers, body).model_dump(by_alias=True)

        except Exception as e:
            logger.error(f"Verification error: {e}", exc_info=True)

            if self.options.on_payment_error:
                custom = self._run_hook(
                    self.options.on_payment_error,
                    e,
                    GatewayRequest.model_validate(gateway_request),
                )
                if custom:
                    return custom.model_dump(by_alias=True)

            return build_402_response(
                payment_required, rpc_id, "Payment verification error"
            ).model_dump(by_alias=True)

    def _handle_response(self, event: dict, context: Any = None) -> dict:
        """
        Handle RESPONSE phase interception.

        1. Check if request was billable
        2. Extract credits used from response
        3. Settle payment with Nevermined
        4. Add payment-response header
        """
        mcp = event.get("mcp", {})
        gateway_request = mcp.get("gatewayRequest", {})
        gateway_response = mcp.get("gatewayResponse", {})

        request_headers = gateway_request.get("headers", {})
        request_body = gateway_request.get("body", {})

        response_headers = gateway_response.get("headers", {})
        response_body = gateway_response.get("body", {})
        response_status = gateway_response.get("statusCode", 200)

        # Only settle successful, billable requests
        method = request_body.get("method", "")
        if response_status != 200 or method not in self.options.billable_methods:
            return forward_response(
                response_headers, response_body, response_status
            ).model_dump(by_alias=True)

        # Get payment token from original request
        token_headers = (
            [self.options.token_header]
            if isinstance(self.options.token_header, str)
            else self.options.token_header
        )
        token = extract_token(request_headers, token_headers)

        if not token:
            # No payment was made
            return forward_response(
                response_headers, response_body, response_status
            ).model_dump(by_alias=True)

        # Get tool config
        tool_name = extract_tool_name(MCPRequestBody.model_validate(request_body))
        config = self.get_config(tool_name)

        if not config:
            return forward_response(
                response_headers, response_body, response_status
            ).model_dump(by_alias=True)

        # Extract credits from response (agent-reported) or use config default
        default_credits = (
            self._resolve_credits_sync(config.credits, request_body)
            if callable(config.credits)
            else config.credits
        )
        credits_to_charge = extract_credits_to_charge(
            response_body,
            response_headers,
            default=default_credits if isinstance(default_credits, int) else 1,
        )
        logger.info(f"Credits to charge: {credits_to_charge}")

        # Resolve endpoint
        endpoint = self._resolve_endpoint(config, gateway_request, context)

        # Build payment required for settlement
        payment_required = build_payment_required(
            plan_id=config.plan_id,
            agent_id=config.agent_id,
            endpoint=endpoint,
            http_verb="POST",
            network=config.network,
        )

        try:
            # Settle with Nevermined
            settlement = self.payments.facilitator.settle_permissions(
                payment_required=payment_required,
                x402_access_token=token,
                max_amount=str(credits_to_charge),
            )

            if not settlement.success:
                logger.error(f"Settlement failed: {settlement.error_reason}")
                # Still return response, but log error
            else:
                logger.info(
                    f"Settlement successful: {settlement.credits_redeemed} credits, "
                    f"remaining: {settlement.remaining_balance}"
                )

                # Call after_settle hook
                if self.options.on_after_settle:
                    self._run_hook(
                        self.options.on_after_settle,
                        GatewayRequest.model_validate(gateway_request),
                        credits_to_charge,
                        settlement,
                    )

            return build_success_response(
                response_headers, response_body, settlement, response_status
            ).model_dump(by_alias=True)

        except Exception as e:
            logger.error(f"Settlement error: {e}", exc_info=True)
            # Return response anyway - don't fail the user's request
            return forward_response(
                response_headers, response_body, response_status
            ).model_dump(by_alias=True)

    def _resolve_credits_sync(
        self, credits: Union[int, CreditsCallable], body: dict
    ) -> int:
        """Resolve credits value synchronously."""
        if isinstance(credits, int):
            return credits

        # Call the function
        result = credits(MCPRequestBody.model_validate(body))

        # Handle async
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                # Create a new event loop in a thread
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, result)
                    return future.result()
            else:
                return asyncio.run(result)

        return result

    def _run_hook(self, hook: Callable, *args: Any) -> Any:
        """Run a hook, handling async if needed."""
        result = hook(*args)
        if inspect.isawaitable(result):
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop and loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, result)
                    return future.result()
            else:
                return asyncio.run(result)
        return result


# =============================================================================
# Module-level Factory Functions (like Strands pattern)
# =============================================================================


def create_interceptor(
    payments: "Payments",
    plan_id: Optional[str] = None,
    plan_ids: Optional[list[str]] = None,
    agent_id: Optional[str] = None,
    credits: Union[int, CreditsCallable] = 1,
    endpoint: Optional[str] = None,
    network: str = "eip155:84532",
    description: Optional[str] = None,
    tools: Optional[Dict[str, InterceptorConfig]] = None,
    options: Optional[InterceptorOptions] = None,
) -> AgentCoreInterceptor:
    """
    Create an AgentCore Gateway interceptor for x402 payment protection.

    This is the primary factory function (similar to Strands' requires_payment).

    Args:
        payments: The Payments instance (with payments.facilitator)
        plan_id: Single plan ID to accept (convenience alias for plan_ids)
        plan_ids: List of plan IDs to accept
        agent_id: Optional agent identifier
        credits: Static int or callable that returns credits to charge
        endpoint: Protected resource endpoint URL
        network: Blockchain network in CAIP-2 format (default: Base Sepolia)
        description: Human-readable description for 402 responses
        tools: Per-tool configuration dict
        options: Global interceptor options

    Returns:
        Configured AgentCoreInterceptor instance

    Example:
        ```python
        from payments_py import Payments, PaymentOptions
        from payments_py.x402.agentcore import create_interceptor

        payments = Payments.get_instance(
            PaymentOptions(nvm_api_key=os.environ["NVM_API_KEY"])
        )

        interceptor = create_interceptor(
            payments=payments,
            plan_id=os.environ["NVM_PLAN_ID"],
            credits=1,
        )

        def lambda_handler(event, context):
            return interceptor.handle(event, context)
        ```
    """
    resolved_plan_id = plan_id or (plan_ids[0] if plan_ids else None)

    return AgentCoreInterceptor(
        payments=payments,
        plan_id=resolved_plan_id,
        agent_id=agent_id,
        credits=credits,
        endpoint=endpoint,
        network=network,
        description=description,
        tools=tools,
        options=options,
    )


def create_lambda_handler(
    payments: "Payments",
    plan_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    credits: Union[int, CreditsCallable] = 1,
    **kwargs: Any,
) -> Callable[[dict, Any], dict]:
    """
    Create a Lambda handler function ready to use.

    Convenience wrapper that creates an interceptor and returns
    its handle method as a callable.

    Args:
        payments: The Payments instance
        plan_id: Plan ID for all tools
        agent_id: Optional agent ID
        credits: Credits per request
        **kwargs: Additional arguments for create_interceptor

    Returns:
        Lambda handler function (event, context) -> dict

    Example:
        ```python
        from payments_py import Payments, PaymentOptions
        from payments_py.x402.agentcore import create_lambda_handler

        payments = Payments.get_instance(
            PaymentOptions(nvm_api_key=os.environ["NVM_API_KEY"])
        )

        lambda_handler = create_lambda_handler(
            payments=payments,
            plan_id=os.environ["NVM_PLAN_ID"],
        )
        ```
    """
    interceptor = create_interceptor(
        payments=payments,
        plan_id=plan_id,
        agent_id=agent_id,
        credits=credits,
        **kwargs,
    )

    return interceptor.handle


# =============================================================================
# Internal API class for payments.agentcore access
# =============================================================================


class _AgentCoreAPI:
    """
    Internal API class attached to Payments.agentcore.

    Provides convenience methods that delegate to the module-level
    factory functions, automatically injecting the payments instance.
    """

    def __init__(self, payments: "Payments"):
        self._payments = payments

    def create_interceptor(self, **kwargs: Any) -> AgentCoreInterceptor:
        """Create interceptor - delegates to module function."""
        return create_interceptor(payments=self._payments, **kwargs)

    def create_lambda_handler(self, **kwargs: Any) -> Callable[[dict, Any], dict]:
        """Create lambda handler - delegates to module function."""
        return create_lambda_handler(payments=self._payments, **kwargs)
