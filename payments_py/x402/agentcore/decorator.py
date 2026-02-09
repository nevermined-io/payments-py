"""
AgentCore Lambda decorator for Nevermined payment protection using the x402 protocol.

Wraps a Lambda handler function to:

1. Extract the x402 payment token from request headers
2. Verify the subscriber has sufficient credits
3. Execute the wrapped handler (agent work)
4. Settle (burn) credits based on the response
5. Return the response enriched with payment-response headers

Unlike the ``AgentCoreInterceptor`` (which is a separate Lambda invoked by
the Gateway in two phases), this decorator wraps the agent's own handler so
that verify → work → settle happen in a **single invocation**.

Example usage::

    from payments_py import Payments, PaymentOptions
    from payments_py.x402.agentcore import requires_payment

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="testing")
    )

    @requires_payment(payments=payments, plan_id="plan-123", credits=1)
    def lambda_handler(event, context=None):
        request = event["mcp"]["gatewayRequest"]
        body = request["body"]
        tool = body["params"]["name"]
        args = body["params"]["arguments"]

        result = do_work(tool, args)

        return {
            "content": [{"type": "text", "text": json.dumps(result)}],
            "_meta": {"creditsToCharge": 2},
        }
"""

import functools
import json
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from payments_py.x402.helpers import build_payment_required
from payments_py.x402.types import (
    PaymentContext,
    SettleResponse,
    VerifyResponse,
    X402PaymentRequired,
    X402Resource,
    X402Scheme,
    X402SchemeExtra,
)

from .constants import INTERCEPTOR_OUTPUT_VERSION, X402_HEADERS
from .helpers import (
    encode_header,
    extract_credits_to_charge,
    extract_token,
)

logger = logging.getLogger(__name__)

CreditsCallable = Callable[[dict], int]

# Hook type aliases (sync — Lambda handlers are sync)
BeforeVerifyHook = Callable[[X402PaymentRequired], None]
AfterVerifyHook = Callable[[VerifyResponse], None]
AfterSettleHook = Callable[[int, SettleResponse], None]
PaymentErrorHook = Callable[[Exception], Optional[dict]]


@dataclass
class _PaymentConfig:
    """Bundles all payment configuration passed through the decorator lifecycle."""

    payments: Any
    plan_ids: list[str]
    credits: Union[int, CreditsCallable]
    agent_id: Optional[str]
    endpoint: Optional[str]
    network: str
    token_headers: list[str]
    on_before_verify: Optional[BeforeVerifyHook]
    on_after_verify: Optional[AfterVerifyHook]
    on_after_settle: Optional[AfterSettleHook]
    on_payment_error: Optional[PaymentErrorHook]


@dataclass
class _VerifiedPayment:
    """Internal container for verified payment state passed between lifecycle phases."""

    token: str
    payment_required: X402PaymentRequired
    credits_to_charge: int
    payment_context: PaymentContext


# ---------------------------------------------------------------------------
# Event parsing helpers
# ---------------------------------------------------------------------------


def _extract_request(event: dict) -> tuple[dict, dict]:
    """Extract headers and body from an AgentCore MCP event.

    Returns (headers, body) dicts.
    """
    mcp = event.get("mcp", {})
    gateway_request = mcp.get("gatewayRequest", {})
    headers = gateway_request.get("headers", {})
    body = gateway_request.get("body", {})
    return headers, body


def _get_rpc_id(body: dict) -> str:
    """Extract the JSON-RPC id from the request body."""
    return str(body.get("id", "1"))


# ---------------------------------------------------------------------------
# MCP response builders
# ---------------------------------------------------------------------------


def _build_402_response(
    payment_required: X402PaymentRequired,
    rpc_id: str = "1",
    message: str = "Payment required to access this resource",
) -> dict:
    """Build a 402 Payment Required response in MCP/InterceptorOutput format."""
    payment_required_b64 = encode_header(payment_required.model_dump(by_alias=True))

    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {
            "transformedGatewayResponse": {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    X402_HEADERS["PAYMENT_REQUIRED"]: payment_required_b64,
                },
                "body": {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(
                                    {
                                        "error": "Payment required",
                                        "code": 402,
                                        "message": message,
                                    }
                                ),
                            }
                        ],
                    },
                },
            }
        },
    }


def _build_error_response(message: str, rpc_id: str = "1") -> dict:
    """Build a generic error response in MCP/InterceptorOutput format."""
    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {
            "transformedGatewayResponse": {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": {
                    "jsonrpc": "2.0",
                    "id": rpc_id,
                    "result": {
                        "isError": True,
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps({"error": message, "code": 500}),
                            }
                        ],
                    },
                },
            }
        },
    }


def _wrap_result_as_response(
    result: dict,
    settlement: SettleResponse,
    rpc_id: str = "1",
) -> dict:
    """Wrap agent result dict into an InterceptorOutput with payment-response header.

    The ``result`` is the dict returned by the decorated function. It can be:
    - A bare MCP result: ``{"content": [...], "_meta": {...}}``
    - A full MCP response body: ``{"jsonrpc": "2.0", "id": "1", "result": {...}}``
    - An InterceptorOutput dict: ``{"interceptorOutputVersion": ..., "mcp": {...}}``
    """
    # Case 1: already an InterceptorOutput — inject payment-response header
    if "interceptorOutputVersion" in result:
        transformed = result.get("mcp", {}).get("transformedGatewayResponse", {})
        if transformed:
            headers = transformed.get("headers", {})
            headers[X402_HEADERS["PAYMENT_RESPONSE"]] = encode_header(
                _settlement_receipt(settlement)
            )
            _inject_meta(transformed.get("body", {}), settlement)
        return result

    # Case 2: full MCP response body with "jsonrpc" key
    if "jsonrpc" in result:
        body = result
    # Case 3: bare MCP result dict — wrap it
    else:
        body = {
            "jsonrpc": "2.0",
            "id": rpc_id,
            "result": result,
        }

    _inject_meta(body, settlement)

    return {
        "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
        "mcp": {
            "transformedGatewayResponse": {
                "statusCode": 200,
                "headers": {
                    "Content-Type": "application/json",
                    X402_HEADERS["PAYMENT_RESPONSE"]: encode_header(
                        _settlement_receipt(settlement)
                    ),
                },
                "body": body,
            }
        },
    }


def _settlement_receipt(settlement: SettleResponse) -> dict:
    return {
        "success": settlement.success,
        "transactionHash": settlement.transaction,
        "network": settlement.network,
        "creditsRedeemed": settlement.credits_redeemed,
        "remainingBalance": settlement.remaining_balance,
    }


def _inject_meta(body: dict, settlement: SettleResponse) -> None:
    """Inject x402 transaction data into result._meta in-place."""
    result = body.get("result")
    if not isinstance(result, dict):
        return
    meta = result.get("_meta", {})
    if not isinstance(meta, dict):
        meta = {}
    meta["x402"] = {
        "success": settlement.success,
        "transaction": settlement.transaction,
        "network": settlement.network,
        "creditsRedeemed": settlement.credits_redeemed,
        "remainingBalance": settlement.remaining_balance,
    }
    result["_meta"] = meta


# ---------------------------------------------------------------------------
# Payment lifecycle
# ---------------------------------------------------------------------------


def _build_payment_required_for_config(config: _PaymentConfig) -> X402PaymentRequired:
    """Build X402PaymentRequired from decorator config.

    For a single plan, delegates to the shared ``build_payment_required`` helper.
    For multiple plans, constructs the accepts array with one X402Scheme per plan.
    """
    if len(config.plan_ids) == 1:
        return build_payment_required(
            plan_id=config.plan_ids[0],
            endpoint=config.endpoint,
            agent_id=config.agent_id,
            network=config.network,
        )

    extra = X402SchemeExtra(agent_id=config.agent_id) if config.agent_id else None
    schemes = [
        X402Scheme(
            scheme="nvm:erc4337",
            network=config.network,
            plan_id=pid,
            extra=extra,
        )
        for pid in config.plan_ids
    ]

    return X402PaymentRequired(
        x402_version=2,
        resource=X402Resource(url=config.endpoint or ""),
        accepts=schemes,
        extensions={},
    )


def _resolve_credits(credits: Union[int, CreditsCallable], event: dict) -> int:
    if isinstance(credits, int):
        return credits
    return credits(event)


def _verify_payment(
    event: dict,
    config: _PaymentConfig,
) -> tuple[Optional[dict], Optional[_VerifiedPayment]]:
    """Run verification lifecycle. Returns (error_dict | None, verified | None)."""
    headers, body = _extract_request(event)
    rpc_id = _get_rpc_id(body)

    payment_required = _build_payment_required_for_config(config)

    # Extract token
    token = extract_token(headers, config.token_headers)
    if not token:
        if config.on_payment_error:
            custom = config.on_payment_error(Exception("Missing payment token"))
            if custom is not None:
                return custom, None
        return _build_402_response(payment_required, rpc_id), None

    credits_to_charge = _resolve_credits(config.credits, event)

    if config.on_before_verify:
        config.on_before_verify(payment_required)

    verification = config.payments.facilitator.verify_permissions(
        payment_required=payment_required,
        x402_access_token=token,
        max_amount=str(credits_to_charge),
    )

    if not verification.is_valid:
        reason = verification.invalid_reason or "Payment verification failed"
        logger.warning("Verification failed: %s", reason)
        if config.on_payment_error:
            custom = config.on_payment_error(
                Exception(f"Verification failed: {reason}")
            )
            if custom is not None:
                return custom, None
        return (
            _build_402_response(
                payment_required, rpc_id, message=f"Verification failed: {reason}"
            ),
            None,
        )

    if config.on_after_verify:
        config.on_after_verify(verification)

    payment_context = PaymentContext(
        token=token,
        payment_required=payment_required,
        credits_to_settle=credits_to_charge,
        verified=True,
        agent_request_id=verification.agent_request_id,
        agent_request=verification.agent_request,
    )

    return None, _VerifiedPayment(
        token=token,
        payment_required=payment_required,
        credits_to_charge=credits_to_charge,
        payment_context=payment_context,
    )


def _settle_payment(
    verified: _VerifiedPayment,
    result: dict,
    config: _PaymentConfig,
) -> Optional[SettleResponse]:
    """Settle credits after successful execution. Returns SettleResponse or None."""
    # Allow the agent response to override credits via _meta.creditsToCharge
    actual_credits = verified.credits_to_charge

    # Normalize result to a response body for credits extraction.
    # The handler can return:
    # - Bare result: {"content": [...], "_meta": {"creditsToCharge": N}}
    # - Full MCP body: {"jsonrpc": "2.0", "result": {"_meta": ...}}
    # - InterceptorOutput: {"mcp": {"transformedGatewayResponse": {"body": ...}}}
    if "mcp" in result:
        response_body = (
            result.get("mcp", {})
            .get("transformedGatewayResponse", {})
            .get("body", result)
        )
    elif "jsonrpc" in result:
        response_body = result
    else:
        # Bare result — wrap it so extract_credits_to_charge can find _meta
        response_body = {"result": result}

    reported = extract_credits_to_charge(response_body, default=actual_credits)
    if reported != actual_credits:
        logger.info(
            "Agent reported %d credits (config default: %d)", reported, actual_credits
        )
        actual_credits = reported

    try:
        settlement = config.payments.facilitator.settle_permissions(
            payment_required=verified.payment_required,
            x402_access_token=verified.token,
            max_amount=str(actual_credits),
            agent_request_id=verified.payment_context.agent_request_id,
        )

        if settlement.success:
            logger.info(
                "Settlement OK: %s credits, remaining %s",
                settlement.credits_redeemed,
                settlement.remaining_balance,
            )
            if config.on_after_settle:
                config.on_after_settle(actual_credits, settlement)
        else:
            logger.error("Settlement failed: %s", settlement.error_reason)

        return settlement

    except Exception as e:
        logger.error("Settlement error: %s", e, exc_info=True)
        return None


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------


def requires_payment(
    payments: Any,
    plan_id: Optional[str] = None,
    plan_ids: Optional[list[str]] = None,
    credits: Union[int, CreditsCallable] = 1,
    agent_id: Optional[str] = None,
    endpoint: Optional[str] = None,
    network: str = "eip155:84532",
    token_header: Union[str, list[str]] = None,
    on_before_verify: Optional[BeforeVerifyHook] = None,
    on_after_verify: Optional[AfterVerifyHook] = None,
    on_after_settle: Optional[AfterSettleHook] = None,
    on_payment_error: Optional[PaymentErrorHook] = None,
) -> Callable:
    """
    Decorator that protects an AgentCore Lambda handler with x402 payment.

    Wraps verify → handler → settle in a single invocation. The decorated
    function receives the full AgentCore MCP event and can return:

    - A bare MCP result dict: ``{"content": [...], "_meta": {...}}``
    - A full MCP response body: ``{"jsonrpc": "2.0", "result": {...}}``
    - A complete InterceptorOutput dict

    The decorator enriches the response with ``payment-response`` headers
    and ``_meta.x402`` transaction data.

    **Credits flow**:

    - ``credits`` is used for both **verify** and **settle** by default.
    - If the handler returns ``_meta.creditsToCharge`` in its response,
      that value overrides ``credits`` for settlement only.

    Args:
        payments: Payments instance (must have ``payments.facilitator``)
        plan_id: Single plan ID (convenience alias for ``plan_ids``)
        plan_ids: List of plan IDs to accept
        credits: Credits to verify and settle. Static int or callable
            ``(event) -> int``. The handler can override the settle amount
            by returning ``_meta.creditsToCharge`` in its response.
        agent_id: Agent identifier for Nevermined
        endpoint: Protected resource URL (for payment_required)
        network: Blockchain network in CAIP-2 format
        token_header: Header name(s) for the x402 token
        on_before_verify: Hook called before verification
        on_after_verify: Hook called after successful verification
        on_after_settle: Hook called after successful settlement
        on_payment_error: Hook called on errors, can return custom response

    Example::

        @requires_payment(
            payments=payments,
            plan_id="plan-123",
            agent_id="agent-456",
            credits=1,
        )
        def lambda_handler(event, context=None):
            body = event["mcp"]["gatewayRequest"]["body"]
            args = body["params"]["arguments"]
            return {
                "content": [{"type": "text", "text": "Hello!"}],
                "_meta": {"creditsToCharge": 3},  # overrides credits for settle
            }
    """
    resolved_plan_ids = plan_ids or ([plan_id] if plan_id else None)
    if not resolved_plan_ids:
        raise ValueError("Either plan_id or plan_ids must be provided")

    resolved_token_headers = (
        [token_header]
        if isinstance(token_header, str)
        else (token_header or ["payment-signature", "PAYMENT-SIGNATURE"])
    )

    config = _PaymentConfig(
        payments=payments,
        plan_ids=resolved_plan_ids,
        credits=credits,
        agent_id=agent_id,
        endpoint=endpoint,
        network=network,
        token_headers=resolved_token_headers,
        on_before_verify=on_before_verify,
        on_after_verify=on_after_verify,
        on_after_settle=on_after_settle,
        on_payment_error=on_payment_error,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(event: dict, context: Any = None) -> dict:
            return _execute_with_payment(func, event, context, config)

        return wrapper

    return decorator


def _execute_with_payment(
    func: Callable,
    event: dict,
    context: Any,
    config: _PaymentConfig,
) -> dict:
    """Synchronous payment verification, execution, and settlement."""
    _, body = _extract_request(event)
    rpc_id = _get_rpc_id(body)

    try:
        # 1. Verify
        error, verified = _verify_payment(event, config)
        if error is not None:
            return error

        # 2. Execute handler
        result = func(event, context)

        # 3. Settle
        settlement = _settle_payment(verified, result, config)

        # 4. Wrap response
        if settlement:
            return _wrap_result_as_response(result, settlement, rpc_id)

        # Settlement failed — return result without payment headers
        if "interceptorOutputVersion" in result:
            return result
        return {
            "interceptorOutputVersion": INTERCEPTOR_OUTPUT_VERSION,
            "mcp": {
                "transformedGatewayResponse": {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": (
                        result
                        if "jsonrpc" in result
                        else {"jsonrpc": "2.0", "id": rpc_id, "result": result}
                    ),
                }
            },
        }

    except Exception as exc:
        logger.error("requires_payment error: %s", exc, exc_info=True)

        if config.on_payment_error:
            custom = config.on_payment_error(exc)
            if custom is not None:
                return custom

        return _build_error_response(str(exc), rpc_id)
