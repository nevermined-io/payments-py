"""
LangChain tool decorator for Nevermined payment protection using the x402 protocol.

Wraps a LangChain ``@tool`` function to:

1. Extract the x402 payment token from ``config["configurable"]["payment_token"]``
2. Verify the subscriber has sufficient credits
3. Execute the wrapped tool function
4. Settle (burn) credits after successful execution

Payment errors raise ``PaymentRequiredError`` so LangChain agents can catch and
surface them to the user. The exception carries the full ``X402PaymentRequired``
object for programmatic token acquisition.

The ``credits`` parameter accepts three forms:
  - **Static int**: ``credits=1`` — always charges 1 credit
  - **Lambda**: ``credits=lambda ctx: len(ctx["result"]) // 100`` — dynamic
  - **Named function**: ``credits=my_fn`` where ``my_fn(ctx) -> int``

When ``credits`` is a callable, it receives a dict with:
  - ``ctx["args"]``: the tool's keyword arguments
  - ``ctx["result"]``: the tool's return value (resolved post-execution)

Server-side example::

    from langchain_core.tools import tool
    from payments_py import Payments, PaymentOptions
    from payments_py.x402.langchain import requires_payment

    payments = Payments.get_instance(
        PaymentOptions(nvm_api_key="...", environment="sandbox")
    )

    @tool
    @requires_payment(payments=payments, plan_id="plan-123", credits=1)
    def search(query: str, config: RunnableConfig) -> str:
        \"\"\"Search with fixed cost.\"\"\"
        return f"Results for: {query}"

    @tool
    @requires_payment(
        payments=payments, plan_id="plan-123",
        credits=lambda ctx: max(1, len(ctx["result"]) // 100),
    )
    def summarize(text: str, config: RunnableConfig) -> str:
        \"\"\"Summarize with dynamic cost based on output length.\"\"\"
        return f"Summary of: {text}"

Client-side flow::

    from payments_py.x402.langchain import PaymentRequiredError

    try:
        result = agent.invoke(
            {"input": "Analyze data"},
            config={"configurable": {"payment_token": token}},
        )
    except PaymentRequiredError as e:
        plan_id = e.payment_required.accepts[0].plan_id
        # Acquire token for plan_id, then retry
"""

import functools
import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Union

from payments_py.x402.helpers import build_payment_required_for_plans
from payments_py.x402.resolve_scheme import resolve_scheme
from payments_py.x402.types import (
    PaymentContext,
    X402PaymentRequired,
)

logger = logging.getLogger(__name__)

CreditsCallable = Callable[..., int]


class PaymentRequiredError(Exception):
    """Raised when payment verification fails.

    Carries the ``X402PaymentRequired`` object so callers can inspect
    accepted plans and acquire the correct payment token.
    """

    def __init__(
        self, message: str, payment_required: Optional[X402PaymentRequired] = None
    ):
        super().__init__(message)
        self.payment_required = payment_required


@dataclass
class _PaymentConfig:
    """Bundles all payment configuration passed through the decorator lifecycle."""

    payments: Any
    plan_ids: list[str]
    credits: Union[int, CreditsCallable]
    agent_id: Optional[str]
    network: Optional[str]
    scheme: Optional[str]


@dataclass
class _VerifiedPayment:
    """Internal container for verified payment state passed between lifecycle phases."""

    token: str
    payment_required: X402PaymentRequired
    credits_to_charge: int
    payment_context: PaymentContext


def _resolve_credits_pre(
    credits: Union[int, CreditsCallable], kwargs: dict
) -> Optional[int]:
    """Resolve credits value pre-execution.

    Returns the int directly for static credits, or None if credits is a callable
    (deferred to post-execution when the result is available).
    """
    if isinstance(credits, int):
        return credits
    return None


def _resolve_credits_post(
    credits: Union[int, CreditsCallable], kwargs: dict, result: Any
) -> int:
    """Resolve credits value post-execution -- always returns an int."""
    if isinstance(credits, int):
        return credits
    return credits({"args": kwargs, "result": result})


def _extract_payment_token(config: Any) -> Optional[str]:
    """Extract payment token from RunnableConfig.configurable."""
    if config is None:
        return None
    configurable = None
    if isinstance(config, dict):
        configurable = config.get("configurable")
    else:
        configurable = getattr(config, "configurable", None)
    if isinstance(configurable, dict):
        return configurable.get("payment_token")
    return None


def _store_in_configurable(config: Any, key: str, value: Any) -> None:
    """Store a value in config["configurable"] if available."""
    if config is None:
        return
    configurable = None
    if isinstance(config, dict):
        configurable = config.get("configurable")
    else:
        configurable = getattr(config, "configurable", None)
    if isinstance(configurable, dict):
        configurable[key] = value


def _verify_payment(
    func: Callable,
    kwargs: dict,
    config: _PaymentConfig,
    runnable_config: Any,
) -> _VerifiedPayment:
    """Run the payment verification lifecycle.

    Returns a _VerifiedPayment on success, or raises PaymentRequiredError.
    """
    resolved_scheme = resolve_scheme(config.payments, config.plan_ids[0], config.scheme)

    payment_required = build_payment_required_for_plans(
        plan_ids=config.plan_ids,
        endpoint=func.__name__,
        agent_id=config.agent_id,
        network=config.network,
        scheme=resolved_scheme,
    )

    token = _extract_payment_token(runnable_config)
    if not token:
        raise PaymentRequiredError(
            "Payment required: missing payment_token in config['configurable']",
            payment_required,
        )

    credits_pre = _resolve_credits_pre(config.credits, kwargs)
    # For verification, use pre-resolved credits or default to 1
    credits_to_charge = credits_pre if credits_pre is not None else 1

    verification = config.payments.facilitator.verify_permissions(
        payment_required=payment_required,
        x402_access_token=token,
        max_amount=str(credits_to_charge),
    )

    if not verification.is_valid:
        reason = verification.invalid_reason or "Payment verification failed"
        raise PaymentRequiredError(
            f"Payment verification failed: {reason}",
            payment_required,
        )

    payment_context = PaymentContext(
        token=token,
        payment_required=payment_required,
        credits_to_settle=credits_to_charge,
        verified=True,
        agent_request_id=verification.agent_request_id,
        agent_request=verification.agent_request,
    )
    _store_in_configurable(runnable_config, "payment_context", payment_context)

    return _VerifiedPayment(
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
    credits_cfg: Union[int, CreditsCallable],
    runnable_config: Any,
) -> None:
    """Settle credits after successful tool execution.

    Resolves dynamic credits post-execution (if callable) and stores
    the settlement response in ``config["configurable"]["payment_settlement"]``.
    """
    final_credits = _resolve_credits_post(credits_cfg, kwargs, result)

    try:
        settlement = payments.facilitator.settle_permissions(
            payment_required=verified.payment_required,
            x402_access_token=verified.token,
            max_amount=str(final_credits),
            agent_request_id=verified.payment_context.agent_request_id,
        )

        _store_in_configurable(runnable_config, "payment_settlement", settlement)

    except Exception as settle_error:
        logger.warning("Payment settlement failed: %s", settle_error)


def requires_payment(
    payments: Any,
    plan_id: Optional[str] = None,
    plan_ids: Optional[list[str]] = None,
    credits: Union[int, CreditsCallable] = 1,
    agent_id: Optional[str] = None,
    network: Optional[str] = None,
    scheme: Optional[str] = None,
) -> Callable:
    """
    Decorator that protects a LangChain tool with x402 payment verification.

    The payment token is extracted from
    ``config["configurable"]["payment_token"]``, passed via::

        agent.invoke({"input": "..."}, config={"configurable": {"payment_token": token}})

    After verification, a ``PaymentContext`` is stored in
    ``config["configurable"]["payment_context"]``.
    After settlement, the result is stored in
    ``config["configurable"]["payment_settlement"]``.

    Args:
        payments: The Payments instance (with payments.facilitator)
        plan_id: Single plan ID to accept (convenience alias for plan_ids)
        plan_ids: List of plan IDs to accept
        credits: How many credits to charge. Accepts three forms:

            - **int**: fixed cost, e.g. ``credits=1``
            - **lambda**: ``credits=lambda ctx: max(1, len(ctx["result"]) // 100)``
            - **function**: ``credits=my_fn`` where ``my_fn(ctx) -> int``

            When callable, ``ctx`` is ``{"args": <tool kwargs>, "result": <tool return>}``.
            Credits are resolved **after** execution so the result is available.
        agent_id: Optional agent identifier
        network: Blockchain network in CAIP-2 format (default: Base Sepolia)
        scheme: x402 payment scheme (auto-detected from plan if None)

    Returns:
        Decorated function with payment protection

    Raises:
        PaymentRequiredError: When payment token is missing or verification fails

    Examples::

        # Static int
        @tool
        @requires_payment(payments=payments, plan_id="plan-123", credits=1)
        def search(query: str, config: RunnableConfig) -> str: ...

        # Lambda — charge based on output length
        @tool
        @requires_payment(
            payments=payments, plan_id="plan-123",
            credits=lambda ctx: max(1, len(ctx["result"]) // 100),
        )
        def summarize(text: str, config: RunnableConfig) -> str: ...

        # Named function — complex logic
        def calc_credits(ctx: dict) -> int:
            words = len(ctx["args"].get("query", "").split())
            return max(1, min(words, 10))

        @tool
        @requires_payment(payments=payments, plan_id="plan-123", credits=calc_credits)
        def research(query: str, config: RunnableConfig) -> str: ...
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
        scheme=scheme,
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


def _extract_runnable_config(kwargs: dict) -> Any:
    """Extract the RunnableConfig from kwargs.

    LangChain injects ``config`` into tool calls when using agents.
    We also check for ``run_manager`` which carries config in some paths.
    """
    rc = kwargs.get("config")
    if rc is not None:
        return rc

    run_manager = kwargs.get("run_manager")
    if run_manager is not None:
        rc = getattr(run_manager, "config", None)
        if rc is not None:
            return rc

    return None


def _execute_with_payment(
    func: Callable,
    args: tuple,
    kwargs: dict,
    config: _PaymentConfig,
) -> Any:
    """Synchronous payment verification, execution, and settlement."""
    runnable_config = _extract_runnable_config(kwargs)
    verified = _verify_payment(func, kwargs, config, runnable_config)
    result = func(*args, **kwargs)
    _settle_payment(
        verified,
        result,
        kwargs,
        config.payments,
        config.credits,
        runnable_config,
    )
    return result


async def _execute_with_payment_async(
    func: Callable,
    args: tuple,
    kwargs: dict,
    config: _PaymentConfig,
) -> Any:
    """Async payment verification, execution, and settlement."""
    runnable_config = _extract_runnable_config(kwargs)
    verified = _verify_payment(func, kwargs, config, runnable_config)
    result = await func(*args, **kwargs)
    _settle_payment(
        verified,
        result,
        kwargs,
        config.payments,
        config.credits,
        runnable_config,
    )
    return result
