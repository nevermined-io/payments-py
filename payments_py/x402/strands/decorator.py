"""
Strands agent tool decorator for Nevermined payment protection using the x402 protocol.

Wraps a Strands ``@tool`` function to:

1. Extract the x402 payment token from ``tool_context.invocation_state`` or kwargs
2. Verify the subscriber has sufficient credits
3. Execute the wrapped tool function
4. Settle (burn) credits after successful execution

Payment errors follow the x402 MCP transport spec: errors are returned as tool
results with ``status: "error"`` (not raised as exceptions). Each error includes
a human-readable text block and a structured JSON block with the full
``X402PaymentRequired`` object so clients can programmatically acquire a token.

In Strands, tool errors flow through the LLM as results. Clients that need
the structured ``PaymentRequired`` should use
``extract_payment_required(agent.messages)`` to search the conversation history.

Server-side example::

    from strands import tool, Agent
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.strands import requires_payment

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="sandbox")
    )

    @tool(context=True)
    @requires_payment(payments=payments, plan_id="plan-123", credits=1)
    def analyze_data(query: str, tool_context=None) -> dict:
        return {"status": "success", "content": [{"text": f"Analysis: {query}"}]}

    agent = Agent(tools=[analyze_data])
    state = {"payment_token": "x402-token-here"}
    result = agent("Analyze sales data", invocation_state=state)

Client-side extraction::

    from payments_py.x402.strands import extract_payment_required

    result = agent("Analyze data")
    payment_required = extract_payment_required(agent.messages)
    if payment_required:
        plan_id = payment_required["accepts"][0]["planId"]
        # Acquire token for plan_id, then call again with payment_token=...
"""

import functools
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from payments_py.x402.helpers import build_payment_required
from payments_py.x402.types import (
    PaymentContext,
    VerifyResponse,
    X402PaymentRequired,
    X402Resource,
    X402Scheme,
    X402SchemeExtra,
)

logger = logging.getLogger(__name__)

CreditsCallable = Callable[..., int]

# Hook type aliases
BeforeVerifyHook = Callable[[X402PaymentRequired], None]
AfterVerifyHook = Callable[[VerifyResponse], None]
AfterSettleHook = Callable[[int, Any], None]
PaymentErrorHook = Callable[[Exception], Optional[dict]]


@dataclass
class _PaymentConfig:
    """Bundles all payment configuration passed through the decorator lifecycle."""

    payments: Any
    plan_ids: list[str]
    credits: Union[int, CreditsCallable]
    agent_id: Optional[str]
    network: str
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


def _build_payment_required_for_plans(
    plan_ids: list[str],
    endpoint: str,
    agent_id: Optional[str] = None,
    network: str = "eip155:84532",
) -> X402PaymentRequired:
    """Build X402PaymentRequired with one or more plan_ids in the accepts array.

    For a single plan, delegates to the shared ``build_payment_required`` helper.
    For multiple plans, constructs the accepts array directly.
    """
    if len(plan_ids) == 1:
        return build_payment_required(
            plan_id=plan_ids[0],
            endpoint=endpoint,
            agent_id=agent_id,
            network=network,
        )

    extra = X402SchemeExtra(agent_id=agent_id) if agent_id else None
    schemes = [
        X402Scheme(
            scheme="nvm:erc4337",
            network=network,
            plan_id=pid,
            extra=extra,
        )
        for pid in plan_ids
    ]

    return X402PaymentRequired(
        x402_version=2,
        resource=X402Resource(url=endpoint),
        accepts=schemes,
        extensions={},
    )


def _resolve_credits(credits: Union[int, CreditsCallable], kwargs: dict) -> int:
    """Resolve credits value -- handles both static int and callable."""
    if isinstance(credits, int):
        return credits
    return credits(kwargs)


def _error_result(message: str) -> dict:
    """Return a Strands-compatible error result."""
    return {"status": "error", "content": [{"text": message}]}


def _payment_required_result(
    message: str, payment_required: X402PaymentRequired
) -> dict:
    """Return a Strands-compatible error result with x402 PaymentRequired.

    Follows the x402 MCP transport pattern: error result includes both a
    human-readable text block and a structured JSON block containing the
    full PaymentRequired object so clients can programmatically acquire
    the correct payment token.

    See: https://github.com/coinbase/x402/blob/main/specs/transports-v2/mcp.md
    """
    return {
        "status": "error",
        "content": [
            {"text": message},
            {"json": payment_required.model_dump(by_alias=True)},
        ],
    }


def _is_error_result(result: Any) -> bool:
    """Check if a result is an error result."""
    return isinstance(result, dict) and result.get("status") == "error"


def _handle_payment_error(
    error: Exception,
    on_payment_error: Optional[PaymentErrorHook],
    payment_required: Optional[X402PaymentRequired] = None,
) -> dict:
    """Invoke the error hook if provided, otherwise return a default error result.

    Hook precedence: if the hook returns a dict, that dict is used as-is.
    If the hook returns None (or is not set), falls back to an x402-compliant
    error containing payment_required when available, or a plain error otherwise.
    """
    if on_payment_error:
        custom = on_payment_error(error)
        if custom is not None:
            return custom

    if payment_required is not None:
        return _payment_required_result(str(error), payment_required)
    return _error_result(str(error))


def _find_x402_json_in_tool_result(block: dict) -> Optional[dict]:
    """Search a toolResult block for a nested x402 PaymentRequired JSON payload.

    Supports two Strands message layouts:
    - Wrapped:  ``{"toolResult": {"content": [...], ...}}``
    - Flat:     ``{"type": "toolResult", "content": [...], ...}``
    """
    if "toolResult" in block:
        tool_result = block["toolResult"]
        if not isinstance(tool_result, dict):
            return None
        inner_content = tool_result.get("content")
    elif block.get("type") == "toolResult":
        inner_content = block.get("content")
    else:
        return None

    if not isinstance(inner_content, list):
        return None

    for inner_block in inner_content:
        if not isinstance(inner_block, dict):
            continue
        json_payload = inner_block.get("json")
        if isinstance(json_payload, dict) and "x402Version" in json_payload:
            return json_payload

    return None


def extract_payment_required(messages: list) -> Optional[dict]:
    """Extract the first x402 PaymentRequired dict from Strands agent messages.

    Searches ``agent.messages`` for ``toolResult`` content blocks that contain
    a ``json`` entry with an ``x402Version`` key (the x402 PaymentRequired
    signature). Returns the first match, or ``None`` if no PaymentRequired
    is found.

    Args:
        messages: The ``agent.messages`` list (Strands conversation history).

    Returns:
        The PaymentRequired dict (with keys like ``x402Version``, ``accepts``,
        ``resource``) or ``None``.

    Example:
        ```python
        from payments_py.x402.strands import extract_payment_required

        result = agent("Do something")
        pr = extract_payment_required(agent.messages)
        if pr:
            plan_id = pr["accepts"][0]["planId"]
        ```
    """
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            payload = _find_x402_json_in_tool_result(block)
            if payload is not None:
                return payload
    return None


def _extract_payment_token(kwargs: dict) -> Optional[str]:
    """Extract payment token from tool_context.invocation_state.

    Falls back to kwargs["payment_token"] for backward compatibility,
    but the primary path is via invocation_state (requires @tool(context=True)).
    """
    tool_context = kwargs.get("tool_context")
    if tool_context is not None:
        invocation_state = getattr(tool_context, "invocation_state", None)
        if isinstance(invocation_state, dict):
            token = invocation_state.get("payment_token")
            if token:
                return token

    return kwargs.get("payment_token")


def _set_invocation_state(kwargs: dict, key: str, value: Any) -> None:
    """Store a value in tool_context.invocation_state if available."""
    tool_context = kwargs.get("tool_context")
    if tool_context is None:
        return

    invocation_state = getattr(tool_context, "invocation_state", None)
    if isinstance(invocation_state, dict):
        invocation_state[key] = value


def _clean_kwargs(kwargs: dict) -> dict:
    """Remove payment-specific kwargs before passing to the wrapped function."""
    cleaned = dict(kwargs)
    cleaned.pop("payment_token", None)
    return cleaned


def _verify_payment(
    func: Callable,
    kwargs: dict,
    config: _PaymentConfig,
) -> tuple[Optional[dict], Optional[_VerifiedPayment]]:
    """
    Run the payment verification lifecycle (token extraction, verify, hooks).

    Returns a tuple of (error_result, verified_payment). Exactly one will be
    non-None: either an error dict to return immediately, or a _VerifiedPayment
    containing everything needed for execution and settlement.
    """
    # Build payment_required first -- needed for x402-compliant error responses
    payment_required = _build_payment_required_for_plans(
        plan_ids=config.plan_ids,
        endpoint=func.__name__,
        agent_id=config.agent_id,
        network=config.network,
    )

    token = _extract_payment_token(kwargs)
    if not token:
        msg = "Payment required: missing payment_token in invocation_state or kwargs"
        return (
            _handle_payment_error(
                Exception(msg), config.on_payment_error, payment_required
            ),
            None,
        )

    credits_to_charge = _resolve_credits(config.credits, kwargs)

    if config.on_before_verify:
        config.on_before_verify(payment_required)

    verification = config.payments.facilitator.verify_permissions(
        payment_required=payment_required,
        x402_access_token=token,
        max_amount=str(credits_to_charge),
    )

    if not verification.is_valid:
        reason = verification.invalid_reason or "Payment verification failed"
        msg = f"Payment verification failed: {reason}"
        return (
            _handle_payment_error(
                Exception(msg), config.on_payment_error, payment_required
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
    _set_invocation_state(kwargs, "payment_context", payment_context)

    return None, _VerifiedPayment(
        token=token,
        payment_required=payment_required,
        credits_to_charge=credits_to_charge,
        payment_context=payment_context,
    )


def _settle_payment(
    verified: _VerifiedPayment,
    result: Any,
    kwargs: dict,
    payments: Any,
    on_after_settle: Optional[AfterSettleHook],
) -> None:
    """Settle credits after successful tool execution (skips on error results).

    On success, stores the settlement response in
    ``tool_context.invocation_state["payment_settlement"]`` so clients can
    inspect credits redeemed, remaining balance, and transaction details.
    """
    if _is_error_result(result):
        return

    try:
        settlement = payments.facilitator.settle_permissions(
            payment_required=verified.payment_required,
            x402_access_token=verified.token,
            max_amount=str(verified.credits_to_charge),
            agent_request_id=verified.payment_context.agent_request_id,
        )

        _set_invocation_state(kwargs, "payment_settlement", settlement)

        if on_after_settle:
            on_after_settle(verified.credits_to_charge, settlement)

    except Exception as settle_error:
        logger.warning("Payment settlement failed: %s", settle_error)


def requires_payment(
    payments: Any,
    plan_id: Optional[str] = None,
    plan_ids: Optional[list[str]] = None,
    credits: Union[int, CreditsCallable] = 1,
    agent_id: Optional[str] = None,
    network: str = "eip155:84532",
    on_before_verify: Optional[BeforeVerifyHook] = None,
    on_after_verify: Optional[AfterVerifyHook] = None,
    on_after_settle: Optional[AfterSettleHook] = None,
    on_payment_error: Optional[PaymentErrorHook] = None,
) -> Callable:
    """
    Decorator that protects a Strands agent tool with x402 payment verification.

    Requires ``@tool(context=True)`` so Strands injects ``tool_context``.

    The payment token is extracted from
    ``tool_context.invocation_state["payment_token"]``, set by calling
    ``agent(prompt, invocation_state={"payment_token": token})``.

    After verification, a ``PaymentContext`` is stored in
    ``tool_context.invocation_state["payment_context"]``.
    After settlement, the result is stored in
    ``tool_context.invocation_state["payment_settlement"]``.

    Args:
        payments: The Payments instance (with payments.facilitator)
        plan_id: Single plan ID to accept (convenience alias for plan_ids)
        plan_ids: List of plan IDs to accept (creates multiple X402Scheme entries)
        credits: Static int or callable that returns credits to charge
        agent_id: Optional agent identifier
        network: Blockchain network in CAIP-2 format (default: Base Sepolia)
        on_before_verify: Hook called before verification
        on_after_verify: Hook called after successful verification
        on_after_settle: Hook called after successful settlement
        on_payment_error: Hook called on payment errors, can return custom error dict

    Returns:
        Decorated function with payment protection

    Example:
        ```python
        @tool(context=True)
        @requires_payment(
            payments=payments,
            plan_ids=["plan-basic", "plan-premium"],
            credits=1,
        )
        def my_tool(query: str, tool_context=None) -> dict:
            return {"status": "success", "content": [{"text": "result"}]}
        ```
    """
    resolved_plan_ids = plan_ids or ([plan_id] if plan_id else None)
    if not resolved_plan_ids:
        raise ValueError("Either plan_id or plan_ids must be provided")

    config = _PaymentConfig(
        payments=payments,
        plan_ids=resolved_plan_ids,
        credits=credits,
        agent_id=agent_id,
        network=network,
        on_before_verify=on_before_verify,
        on_after_verify=on_after_verify,
        on_after_settle=on_after_settle,
        on_payment_error=on_payment_error,
    )

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            return _execute_with_payment(func, args, kwargs, config)

        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            return await _execute_with_payment_async(func, args, kwargs, config)

        if inspect.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


def _execute_with_payment(
    func: Callable,
    args: tuple,
    kwargs: dict,
    config: _PaymentConfig,
) -> dict:
    """Synchronous payment verification, execution, and settlement."""
    try:
        error, verified = _verify_payment(func, kwargs, config)
        if error is not None:
            return error

        result = func(*args, **_clean_kwargs(kwargs))
        _settle_payment(
            verified, result, kwargs, config.payments, config.on_after_settle
        )
        return result

    except Exception as exc:
        return _handle_payment_error(exc, config.on_payment_error)


async def _execute_with_payment_async(
    func: Callable,
    args: tuple,
    kwargs: dict,
    config: _PaymentConfig,
) -> dict:
    """Async payment verification, execution, and settlement."""
    try:
        error, verified = _verify_payment(func, kwargs, config)
        if error is not None:
            return error

        result = await func(*args, **_clean_kwargs(kwargs))
        _settle_payment(
            verified, result, kwargs, config.payments, config.on_after_settle
        )
        return result

    except Exception as exc:
        return _handle_payment_error(exc, config.on_payment_error)
