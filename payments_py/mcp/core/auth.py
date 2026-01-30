"""
Authentication handler for MCP paywall using x402 tokens.
"""

from typing import Any, Dict, Optional

from ..utils.request import extract_auth_header, strip_bearer
from ..utils.logical_url import build_logical_url, build_logical_meta_url
from ..utils.errors import create_rpc_error, ERROR_CODES
from payments_py.x402.token import decode_access_token


class PaywallAuthenticator:
    """
    Handles authentication and authorization for MCP requests using payments-py APIs.
    """

    def __init__(self, payments: Any) -> None:
        """Initialize the authenticator.

        Args:
            payments: Payments client used to call backend APIs.
        """
        self._payments = payments

    async def _verify_with_endpoint(
        self,
        access_token: str,
        endpoint: str,
        agent_id: str,
        max_amount: int,
        plan_id_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verify permissions against a single endpoint URL.

        Resolves planId from the override, token, or agent's plans as fallback.

        Returns:
            Dictionary with plan_id, subscriber_address, and optional agent_request.

        Raises:
            ValueError: When token is invalid or plan/subscriber cannot be determined.
        """
        decoded = decode_access_token(access_token)
        if not decoded:
            raise ValueError("Invalid access token")

        plan_id = plan_id_override
        if not plan_id:
            accepted = decoded.get("accepted", {})
            plan_id = accepted.get("planId") if isinstance(accepted, dict) else None

        # Extract subscriber_address from x402 token
        payload = decoded.get("payload", {})
        authorization = (
            payload.get("authorization", {}) if isinstance(payload, dict) else {}
        )
        subscriber_address = (
            authorization.get("from") if isinstance(authorization, dict) else None
        )

        # If planId is not available, try to get it from the agent's plans
        if not plan_id:
            try:
                agent_plans = self._payments.agents.get_agent_plans(agent_id)
                if hasattr(agent_plans, "__await__"):
                    agent_plans = await agent_plans
                items = (agent_plans or {}).get("plans", [])
                if isinstance(items, list) and items:
                    p = items[0]
                    plan_id = p.get("planId") or p.get("id")
            except Exception:
                pass

        if not plan_id or not subscriber_address:
            raise ValueError(
                "Cannot determine plan_id or subscriber_address from token "
                "(expected accepted.planId and payload.authorization.from)"
            )

        from payments_py.x402.helpers import build_payment_required

        payment_required = build_payment_required(
            plan_id=plan_id,
            endpoint=endpoint,
            agent_id=agent_id,
        )
        result = self._payments.facilitator.verify_permissions(
            payment_required=payment_required,
            max_amount=str(max_amount),
            x402_access_token=access_token,
        )
        if hasattr(result, "__await__"):
            result = await result

        if not result or not result.is_valid:
            raise ValueError("Permission verification failed")

        return {
            "plan_id": plan_id,
            "subscriber_address": subscriber_address,
        }

    async def _verify_with_fallback(
        self,
        access_token: str,
        logical_url: str,
        http_url: Optional[str],
        max_amount: int,
        agent_id: str,
        plan_id_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Core verification logic shared by authenticate and authenticate_meta.

        Tries logical URL first, falls back to HTTP URL if available.

        Returns:
            AuthResult dictionary.

        Raises:
            Exception: PaymentRequired error when both attempts fail.
        """
        # Try logical URL first
        try:
            result = await self._verify_with_endpoint(
                access_token, logical_url, agent_id, max_amount, plan_id_override
            )
            return {
                "token": access_token,
                "agent_id": agent_id,
                "logical_url": logical_url,
                "http_url": http_url,
                "plan_id": result["plan_id"],
                "subscriber_address": result["subscriber_address"],
            }
        except Exception:
            pass

        # Fallback to HTTP URL
        if http_url:
            try:
                result = await self._verify_with_endpoint(
                    access_token, http_url, agent_id, max_amount, plan_id_override
                )
                return {
                    "token": access_token,
                    "agent_id": agent_id,
                    "logical_url": logical_url,
                    "http_url": http_url,
                    "plan_id": result["plan_id"],
                    "subscriber_address": result["subscriber_address"],
                }
            except Exception:
                pass

        # Both attempts failed — enrich denial with suggested plans (best-effort)
        plans_msg = ""
        try:
            plans = self._payments.agents.get_agent_plans(agent_id)
            if hasattr(plans, "__await__"):
                plans = await plans
            items = (plans or {}).get("plans", [])
            if isinstance(items, list) and items:
                names = []
                for p in items:
                    meta_main = ((p or {}).get("metadata") or {}).get("main") or {}
                    pname = meta_main.get("name")
                    if isinstance(pname, str) and pname:
                        names.append(pname)
                    else:
                        pid = p.get("planId") or p.get("id") or "plan"
                        pn = p.get("name")
                        label = f"{pid} ({pn})" if pn else pid
                        names.append(label)
                if names:
                    summary = ", ".join(names[:3])
                    plans_msg = f" Available plans: {summary}..."
        except Exception:
            pass

        raise create_rpc_error(
            ERROR_CODES["PaymentRequired"],
            f"Payment required.{plans_msg}",
            {"reason": "invalid"},
        )

    async def authenticate(
        self,
        extra: Any,
        options: Dict[str, Any],
        agent_id: str,
        server_name: str,
        name: str,
        kind: str,
        args_or_vars: Any,
    ) -> Dict[str, Any]:
        """Authenticate a tool/resource/prompt request.

        Args:
            extra: Extra request metadata containing headers.
            options: Paywall options used for the current handler.
            agent_id: Agent identifier configured in the server.
            server_name: Logical server name.
            name: Tool/resource/prompt name.
            kind: Handler kind (e.g. "tool", "resource", "prompt").
            args_or_vars: Arguments (tools/prompts) or variables (resources) for the request.

        Returns:
            A dictionary containing token, agent_id, logical_url, http_url, plan_id and subscriber_address.

        Raises:
            Exception: When authorization is missing or the user is not a subscriber.
        """
        auth_header = extract_auth_header(extra)
        if not auth_header:
            raise create_rpc_error(
                ERROR_CODES["PaymentRequired"],
                "Authorization required",
                {"reason": "missing"},
            )

        return await self._verify_with_fallback(
            access_token=strip_bearer(auth_header),
            logical_url=build_logical_url(
                {
                    "kind": kind,
                    "serverName": server_name,
                    "name": name,
                    "argsOrVars": args_or_vars,
                }
            ),
            http_url=None,  # No HTTP context available in Python SDK yet
            max_amount=options.get("maxAmount", 1),
            agent_id=agent_id,
            plan_id_override=options.get("planId"),
        )

    async def authenticate_meta(
        self,
        extra: Any,
        options: Dict[str, Any],
        agent_id: str,
        server_name: str,
        method: str,
    ) -> Dict[str, Any]:
        """Authenticate a meta operation (initialize/list/etc.).

        Args:
            extra: Extra request metadata containing headers.
            options: Paywall options (may contain planId, maxAmount).
            agent_id: Agent identifier configured in the server.
            server_name: Logical server name.
            method: Meta method name.

        Returns:
            A dictionary containing token, agent_id, logical_url, http_url, plan_id and subscriber_address.

        Raises:
            Exception: When authorization is missing or the user is not a subscriber.
        """
        auth_header = extract_auth_header(extra)
        if not auth_header:
            raise create_rpc_error(
                ERROR_CODES["PaymentRequired"],
                "Authorization required",
                {"reason": "missing"},
            )

        return await self._verify_with_fallback(
            access_token=strip_bearer(auth_header),
            logical_url=build_logical_meta_url(server_name, method),
            http_url=None,  # No HTTP context available in Python SDK yet
            max_amount=options.get("maxAmount", 1),
            agent_id=agent_id,
            plan_id_override=options.get("planId"),
        )
