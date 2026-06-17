"""
Paywall decorator for MCP handlers (tools, resources, prompts).
"""

import logging
from typing import Any, Awaitable, Callable, Dict, Optional

from ..utils.errors import ERROR_CODES, create_rpc_error, SettlementFailedError
from ..utils.extra import build_extra_from_fastmcp_context
from ..utils.meta import (
    X402_PAYMENT_RESPONSE_META_KEY,
    NEVERMINED_CREDITS_META_KEY,
)
from ..types import PaywallOptions, PaywallContext
from payments_py.x402.helpers import (
    build_payment_required,
    build_payment_required_for_plans,
)

logger = logging.getLogger(__name__)


class PaywallDecorator:
    """
    Create paywall-protected MCP handlers.
    """

    def __init__(self, payments: Any, authenticator: Any, credits_context: Any) -> None:
        """Initialize the decorator.

        Args:
            payments: Payments client used to call backend APIs.
            authenticator: Component responsible for authenticating requests.
            credits_context: Component that computes credits to be redeemed.
        """
        self._payments = payments
        self._auth = authenticator
        self._credits = credits_context
        self.config: Dict[str, Any] = {"agentId": "", "serverName": "mcp-server"}

    def configure(self, options: Dict[str, Any]) -> None:
        """Configure decorator defaults.

        Recognized keys:
        - agentId: string agent identifier
        - serverName: string logical server name
        - getContext: callable resolving the current FastMCP Context (invoked per-request)
        - getExtra: callable resolving an MCP-compatible extra dict (invoked per-request)
        - fastmcp: optional FastMCP instance (fallback if getContext not provided)
        """
        # Preserve existing values unless overridden and allow passing extra keys
        merged: Dict[str, Any] = dict(self.config or {})
        merged.update(
            {
                "agentId": options.get("agentId", merged.get("agentId", "")),
                "serverName": options.get(
                    "serverName", merged.get("serverName", "mcp-server")
                ),
            }
        )
        # Carry any additional configuration keys (e.g., getContext, fastmcp)
        for k, v in options.items():
            if k not in ("agentId", "serverName"):
                merged[k] = v
        self.config = merged

    def protect(
        self, handler: Callable[..., Any], options: PaywallOptions
    ) -> Callable[..., Awaitable[Any]]:
        """Wrap a handler with paywall logic.

        The returned function authenticates the request, invokes the handler,
        and redeems credits after completion. It supports tools, resources and
        prompts, as well as async iterables for streaming responses.

        Args:
            handler: Original handler function to protect.
            options: Paywall options including kind, name and optional credits.

        Returns:
            An awaitable callable suitable for MCP servers.
        """

        async def wrapped(*all_args: Any) -> Any:
            if not self.config.get("agentId"):
                raise create_rpc_error(
                    ERROR_CODES["Misconfiguration"],
                    "Server misconfiguration: missing agentId",
                )

            kind = options.get("kind", "tool")
            name = options.get("name", "unnamed")

            is_resource = len(all_args) >= 2 and isinstance(
                all_args[0], type(object.__new__(type("URL", (), {})))
            )
            # Above isinstance check is unreliable; we treat resource by arity: (url, vars, extra)
            is_resource = len(all_args) >= 3
            extra_raw = (
                all_args[2]
                if is_resource
                else (all_args[1] if len(all_args) > 1 else None)
            )
            # Build extra from provided context or dict if present
            if extra_raw is not None and not isinstance(extra_raw, dict):
                try:
                    extra = build_extra_from_fastmcp_context(extra_raw)
                except Exception:
                    extra = None
            else:
                extra = extra_raw

            # If no explicit extra, resolve a provider (configured globally or per-handler)
            if extra is None or (isinstance(extra, dict) and not extra):
                get_ctx = (options or {}).get("getContext") or self.config.get(
                    "getContext"
                )
                get_extra = (options or {}).get("getExtra") or self.config.get(
                    "getExtra"
                )
                fastmcp_inst = (options or {}).get("fastmcp") or self.config.get(
                    "fastmcp"
                )
                ctx_candidate = None
                if callable(get_ctx):
                    try:
                        ctx_candidate = get_ctx()
                    except Exception:
                        ctx_candidate = None
                elif fastmcp_inst is not None:
                    try:
                        ctx_candidate = fastmcp_inst.get_context()
                    except Exception:
                        ctx_candidate = None
                if ctx_candidate is not None:
                    try:
                        extra = build_extra_from_fastmcp_context(ctx_candidate)
                    except Exception:
                        # Keep as empty dict if building fails
                        extra = {}
                elif callable(get_extra):
                    try:
                        cand = get_extra()
                        extra = cand if isinstance(cand, dict) else {}
                    except Exception:
                        extra = {}
                elif extra is None:
                    extra = {}
            args_or_vars = (
                all_args[1]
                if is_resource
                else (all_args[0] if len(all_args) > 0 else None)
            )

            auth_result = await self._auth.authenticate(
                extra,
                options,
                self.config["agentId"],
                self.config["serverName"],
                name,
                kind,
                args_or_vars,
            )

            # Resolve initial credits for context
            initial_credits = self._credits.resolve(
                options.get("credits"), args_or_vars, None, auth_result
            )

            # Create paywall context
            paywall_context: PaywallContext = {
                "auth_result": auth_result,
                "credits": initial_credits,
                "plan_id": auth_result.get("plan_id"),
                "subscriber_address": auth_result.get("subscriber_address"),
                "agent_request": auth_result.get("agent_request"),
                "agent_request_id": auth_result.get("agent_request_id"),
            }

            # Call handler with a compatible signature across tool/resource/prompt
            try:
                result = handler(*all_args, paywall_context)
            except TypeError:
                try:
                    # Fallback: without context
                    result = handler(*all_args)
                except TypeError:
                    try:
                        # For tools/prompts, fall back to (args,) when extra is not accepted
                        if not is_resource:
                            result = handler(all_args[0])
                        else:
                            # For resources, fall back to (uri, variables)
                            result = handler(all_args[0], all_args[1])
                    except TypeError:
                        # Re-raise original error when signature incompatible
                        raise
            if hasattr(result, "__await__"):
                result = await result  # type: ignore[assignment]

            credits = self._credits.resolve(
                options.get("credits"), args_or_vars, result, auth_result
            )

            # Streaming support: async iterable
            if hasattr(result, "__aiter__"):
                return _RedeemOnCloseAsyncIterator(
                    result,
                    lambda: self._redeem(
                        auth_result.get("plan_id"),
                        auth_result["token"],
                        credits,
                        options,
                        agent_id=auth_result.get("agent_id"),
                        endpoint=auth_result.get("logical_url"),
                        fallback_endpoint=auth_result.get("http_url"),
                        http_verb="POST",
                        agent_request_id=auth_result.get("agent_request_id"),
                    ),
                )

            # Non-streaming: redeem immediately and always add metadata
            credits_result = await self._redeem(
                auth_result.get("plan_id"),
                auth_result["token"],
                credits,
                options,
                agent_id=auth_result.get("agent_id"),
                endpoint=auth_result.get("logical_url"),
                fallback_endpoint=auth_result.get("http_url"),
                http_verb="POST",
                agent_request_id=auth_result.get("agent_request_id"),
            )

            # Settlement failed AFTER the tool executed: per the x402 v2 MCP
            # transport spec, do NOT return the tool's content — surface only
            # the payment error so a paid result is never delivered without
            # payment landing. The tool dispatcher converts this into a
            # CallToolResult(isError=True) carrying the PaymentRequired object.
            if not credits_result.get("success", False):
                logger.error(
                    "x402 settlement failed after tool execution; suppressing "
                    "tool content. reason=%s",
                    credits_result.get("errorReason"),
                )
                raise SettlementFailedError(
                    self._build_payment_required(auth_result),
                    "Settlement failed after tool execution",
                )

            # Ensure a dict _meta to attach receipts to.
            if not isinstance(result.get("_meta"), dict):
                result["_meta"] = {}

            # Spec-defined settlement receipt (x402 v2 MCP transport). Absent for
            # free/no-credit calls where no settlement occurred.
            settlement = credits_result.get("settlement")
            if settlement is not None:
                result["_meta"][X402_PAYMENT_RESPONSE_META_KEY] = settlement

            # Nevermined-namespaced observability (NOT part of the x402 spec).
            nvm_meta = {
                "txHash": credits_result.get("txHash"),
                "creditsRedeemed": credits_result.get("creditsRedeemed", "0"),
                "remainingBalance": credits_result.get("remainingBalance"),
                "planId": auth_result.get("plan_id"),
                "subscriberAddress": auth_result.get("subscriber_address"),
                "success": credits_result.get("success", False),
            }
            if credits_result.get("errorReason"):
                nvm_meta["errorReason"] = credits_result["errorReason"]
            result["_meta"][NEVERMINED_CREDITS_META_KEY] = nvm_meta

            return result

        return wrapped

    def _build_payment_required(self, auth_result: Dict[str, Any]) -> Dict[str, Any]:
        """Build a spec-shaped ``PaymentRequired`` dict for a settlement failure.

        Used when settlement fails after a tool has executed: the dispatcher
        surfaces this object in the in-band payment error.

        Args:
            auth_result: The authenticated request context (plan id, urls, …).

        Returns:
            The ``PaymentRequired`` object as a plain dict.
        """
        plan_id = auth_result.get("plan_id") or ""
        payment_required = build_payment_required_for_plans(
            [plan_id] if plan_id else [""],
            endpoint=auth_result.get("logical_url") or auth_result.get("http_url"),
            agent_id=auth_result.get("agent_id"),
            http_verb="POST",
            environment=getattr(self._payments, "environment_name", None),
        )
        pr_dict = payment_required.model_dump(by_alias=True)
        pr_dict["error"] = "settlement failed"
        return pr_dict

    async def _redeem(
        self,
        plan_id: str,
        token: str,
        credits: int,
        options: PaywallOptions,
        agent_id: Optional[str] = None,
        endpoint: Optional[str] = None,
        fallback_endpoint: Optional[str] = None,
        http_verb: Optional[str] = None,
        agent_request_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Settle credits for a processed request using x402 settle_permissions.

        Tries the primary endpoint first. If it fails and a fallback_endpoint
        is available, retries with the fallback.

        Args:
            plan_id: The plan identifier from the token.
            token: X402 access token used for the request.
            credits: Number of credits to settle.
            options: Paywall options to control error propagation.
            agent_id: Optional agent identifier.
            endpoint: Optional primary endpoint URL (logical URL).
            fallback_endpoint: Optional fallback endpoint URL (HTTP URL).
            http_verb: Optional HTTP method.

        Returns:
            Dictionary containing success status, transaction hash, credits redeemed,
            and errorReason if applicable.
        """
        try:
            if credits and int(credits) > 0 and plan_id:
                payment_required = build_payment_required(
                    plan_id=plan_id,
                    endpoint=endpoint,
                    agent_id=agent_id,
                    http_verb=http_verb,
                    environment=getattr(self._payments, "environment_name", None),
                )

                settle_result = await self._maybe_await(
                    self._payments.facilitator.settle_permissions(
                        payment_required=payment_required,
                        x402_access_token=token,
                        max_amount=str(int(credits)),
                        agent_request_id=agent_request_id,
                    )
                )
                settle_success = settle_result.success
                credits_burned = (
                    settle_result.credits_redeemed or str(credits)
                    if settle_success
                    else "0"
                )
                return {
                    "success": settle_success,
                    "txHash": settle_result.transaction if settle_success else None,
                    "creditsRedeemed": credits_burned,
                    "remainingBalance": (
                        settle_result.remaining_balance if settle_success else None
                    ),
                    "settlement": (
                        settle_result.model_dump(by_alias=True, exclude_none=True)
                        if settle_success and hasattr(settle_result, "model_dump")
                        else None
                    ),
                }
            else:
                return {
                    "success": True,
                    "txHash": None,
                    "creditsRedeemed": "0",
                }
        except Exception as primary_error:
            logger.error("x402 settle failed (primary endpoint): %s", primary_error)
            # If primary endpoint fails and we have a fallback, retry with it
            if fallback_endpoint:
                try:
                    payment_required = build_payment_required(
                        plan_id=plan_id,
                        endpoint=fallback_endpoint,
                        agent_id=agent_id,
                        http_verb=http_verb,
                        environment=getattr(self._payments, "environment_name", None),
                    )

                    settle_result = await self._maybe_await(
                        self._payments.facilitator.settle_permissions(
                            payment_required=payment_required,
                            x402_access_token=token,
                            max_amount=str(int(credits)),
                            agent_request_id=agent_request_id,
                        )
                    )
                    settle_success = settle_result.success
                    credits_burned = (
                        settle_result.credits_redeemed or str(credits)
                        if settle_success
                        else "0"
                    )
                    return {
                        "success": settle_success,
                        "txHash": settle_result.transaction if settle_success else None,
                        "creditsRedeemed": credits_burned,
                        "remainingBalance": (
                            settle_result.remaining_balance if settle_success else None
                        ),
                        "settlement": (
                            settle_result.model_dump(by_alias=True, exclude_none=True)
                            if settle_success and hasattr(settle_result, "model_dump")
                            else None
                        ),
                    }
                except Exception as fallback_error:
                    logger.error(
                        "x402 settle failed (fallback endpoint): %s", fallback_error
                    )
                    primary_error = fallback_error

            if options.get("onRedeemError") == "propagate":
                error_msg = str(primary_error)
                raise create_rpc_error(
                    ERROR_CODES["Misconfiguration"],
                    f"Failed to redeem credits: {error_msg}",
                )
            return {
                "success": False,
                "txHash": None,
                "creditsRedeemed": "0",
                "errorReason": str(primary_error),
            }

    async def _maybe_await(self, maybe_awaitable: Any) -> Any:
        """Await a value if it is awaitable; otherwise return it directly."""
        return (
            await maybe_awaitable
            if hasattr(maybe_awaitable, "__await__")
            else maybe_awaitable
        )


class _RedeemOnCloseAsyncIterator:
    """Wrap an async-iterable to ensure a callback runs on completion or early close.

    Settlement runs on completion and the result is stored in ``_credits_result``,
    but it is currently NOT surfaced to the consumer: unlike the non-streaming
    path (and the TS SDK's final ``_meta`` chunk), streamed results have no
    ``_meta`` channel here — the MCP tool-result dispatch yields content chunks,
    not a trailing metadata frame, so a streaming settlement failure is invisible
    to the client. Streaming-observability parity is a tracked follow-up
    (aaitor review on PR #228); revisit if/when the dispatch grows a final
    metadata frame.
    """

    def __init__(
        self, async_iterable: Any, on_finally: Callable[[], Awaitable[Dict[str, Any]]]
    ):
        """Initialize the wrapper for an async-iterable.

        Args:
            async_iterable: The original async-iterable to wrap.
            on_finally: Callback executed when iteration finishes or closes, returns credits result.
        """
        self._async_iterable = async_iterable
        self._on_finally = on_finally
        self._ait = None
        self._credits_result = None

    def __aiter__(self):  # noqa: D401
        # Create a fresh async iterator
        self._ait = self._async_iterable.__aiter__()
        return self

    async def __anext__(self):  # noqa: D401
        assert self._ait is not None
        try:
            return await self._ait.__anext__()
        except StopAsyncIteration:
            # Natural completion - execute callback and get credits result
            self._credits_result = await self._on_finally()
            raise

    async def aclose(self):  # Ensure redeem on early cancellation/break
        """Close the iterator and execute the finalization callback."""
        try:
            if self._credits_result is None:
                self._credits_result = await self._on_finally()
        finally:
            if self._ait is not None and hasattr(self._ait, "aclose"):
                try:
                    await self._ait.aclose()  # type: ignore[attr-defined]
                except Exception:
                    pass
