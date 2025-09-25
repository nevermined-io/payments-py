"""
Paywall decorator for MCP handlers (tools, resources, prompts).
"""

from typing import Any, Awaitable, Callable, Dict

from ..utils.errors import ERROR_CODES, create_rpc_error
from ..utils.extra import build_extra_from_fastmcp_context
from ..types import PaywallOptions, PaywallContext


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
                "agent_request": auth_result["agentRequest"],
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
                        auth_result["requestId"], auth_result["token"], credits, options
                    ),
                )

            # Non-streaming: redeem immediately and add metadata
            credits_result = await self._redeem(
                auth_result["requestId"], auth_result["token"], credits, options
            )

            # Add metadata to result if redemption was successful
            if credits_result["success"]:
                # Add metadata as a key
                if "metadata" not in result or result["metadata"] is None:
                    result["metadata"] = {}
                if not isinstance(result["metadata"], dict):
                    result["metadata"] = {}

                result["metadata"].update(
                    {
                        "txHash": credits_result["txHash"],
                        "requestId": credits_result["requestId"],
                        "creditsRedeemed": credits_result["creditsRedeemed"],
                        "success": True,
                    }
                )

            return result

        return wrapped

    async def _redeem(
        self, request_id: str, token: str, credits: int, options: PaywallOptions
    ) -> Dict[str, Any]:
        """Redeem credits for a processed request.

        Args:
            request_id: Agent request identifier.
            token: Authorization token used for the request.
            credits: Number of credits to redeem.
            options: Paywall options to control error propagation.

        Returns:
            Dictionary containing success status and transaction hash if successful.
        """
        try:
            if credits and int(credits) > 0:
                redeem_result = await self._maybe_await(
                    self._payments.requests.redeem_credits_from_request(
                        request_id, token, int(credits)
                    )
                )
                # Check if the redeem operation was successful
                redeem_success = redeem_result.get(
                    "success", True
                )  # Default to True for backward compatibility
                return {
                    "success": redeem_success,
                    "txHash": redeem_result.get("txHash") if redeem_success else None,
                    "requestId": request_id,
                    "creditsRedeemed": str(credits),
                }
            else:
                return {
                    "success": True,
                    "txHash": None,
                    "requestId": request_id,
                    "creditsRedeemed": "0",
                }
        except Exception:
            if options.get("onRedeemError") == "propagate":
                raise create_rpc_error(
                    ERROR_CODES["Misconfiguration"], "Failed to redeem credits"
                )
            return {
                "success": False,
                "txHash": None,
                "requestId": request_id,
                "creditsRedeemed": "0",
            }

    async def _maybe_await(self, maybe_awaitable: Any) -> Any:
        """Await a value if it is awaitable; otherwise return it directly."""
        return (
            await maybe_awaitable
            if hasattr(maybe_awaitable, "__await__")
            else maybe_awaitable
        )


class _RedeemOnCloseAsyncIterator:
    """Wrap an async-iterable to ensure a callback runs on completion or early close."""

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
