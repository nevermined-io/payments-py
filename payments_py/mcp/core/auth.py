"""
Authentication handler for MCP paywall using x402 tokens.
"""

from typing import Any, Dict

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
            A dictionary containing requestId, token, agentId and logicalUrl.

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
        token = strip_bearer(auth_header)
        logical_url = build_logical_url(
            {
                "kind": kind,
                "serverName": server_name,
                "name": name,
                "argsOrVars": args_or_vars,
            }
        )
        try:
            # Decode token to extract plan_id and subscriber_address
            decoded = decode_access_token(token)
            if not decoded:
                raise ValueError("Invalid access token")

            # plan_id must come from options (x402 tokens don't contain planId)
            plan_id = options.get("planId")

            # Extract subscriber_address from x402 token (payload.authorization.from per x402 spec)
            payload = decoded.get("payload", {})
            authorization = (
                payload.get("authorization", {}) if isinstance(payload, dict) else {}
            )
            subscriber_address = (
                authorization.get("from") if isinstance(authorization, dict) else None
            )

            if not plan_id or not subscriber_address:
                raise ValueError(
                    "Cannot determine plan_id or subscriber_address from token (expected payload.authorization.from)"
                )

            # Import build_payment_required here to avoid circular imports
            from payments_py.x402.helpers import build_payment_required

            # Use x402 verify_permissions with paymentRequired
            payment_required = build_payment_required(
                plan_id=plan_id,
                endpoint=logical_url,
                agent_id=agent_id,
            )
            result = self._payments.facilitator.verify_permissions(
                payment_required=payment_required,
                max_amount="1",  # Verify at least 1 credit
                x402_access_token=token,
            )
            # support sync or async clients
            if hasattr(result, "__await__"):
                result = await result

            if not result or not result.is_valid:
                raise ValueError("Permission verification failed")

            return {
                "token": token,
                "agentId": agent_id,
                "logicalUrl": logical_url,
                "plan_id": plan_id,
                "subscriber_address": subscriber_address,
            }
        except Exception:
            plans_msg = ""
            try:
                plans = self._payments.agents.get_agent_plans(agent_id)
                items = (plans or {}).get("plans", [])
                if isinstance(items, list) and items:
                    # Prefer human-readable names from metadata.main.name
                    names = []
                    for p in items:
                        meta_main = ((p or {}).get("metadata") or {}).get("main") or {}
                        pname = meta_main.get("name")
                        if isinstance(pname, str) and pname:
                            names.append(pname)
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

    async def authenticate_meta(
        self, extra: Any, agent_id: str, server_name: str, method: str
    ):
        """Authenticate a meta operation (initialize/list/etc.).

        Args:
            extra: Extra request metadata containing headers.
            agent_id: Agent identifier configured in the server.
            server_name: Logical server name.
            method: Meta method name.

        Returns:
            A dictionary containing requestId, token, agentId and logicalUrl.

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
        token = strip_bearer(auth_header)
        logical_url = build_logical_meta_url(server_name, method)

        try:
            # Decode token to extract plan_id and subscriber_address
            decoded = decode_access_token(token)
            if not decoded:
                raise ValueError("Invalid access token")

            # Try to get plan_id from token (accepted.planId per x402 spec)
            accepted = decoded.get("accepted", {})
            plan_id = accepted.get("planId") if isinstance(accepted, dict) else None

            # Extract subscriber_address from x402 token (payload.authorization.from per x402 spec)
            payload = decoded.get("payload", {})
            authorization = (
                payload.get("authorization", {}) if isinstance(payload, dict) else {}
            )
            subscriber_address = (
                authorization.get("from") if isinstance(authorization, dict) else None
            )

            if not plan_id or not subscriber_address:
                raise ValueError(
                    "Cannot determine plan_id or subscriber_address from token (expected accepted.planId and payload.authorization.from)"
                )

            # Import build_payment_required here to avoid circular imports
            from payments_py.x402.helpers import build_payment_required

            # Use x402 verify_permissions with paymentRequired
            payment_required = build_payment_required(
                plan_id=plan_id,
                endpoint=logical_url,
                agent_id=agent_id,
            )
            result = self._payments.facilitator.verify_permissions(
                payment_required=payment_required,
                max_amount="1",  # Verify at least 1 credit
                x402_access_token=token,
            )
            if hasattr(result, "__await__"):
                result = await result
            if not result or not result.is_valid:
                raise ValueError("Permission verification failed")
            return {
                "token": token,
                "agentId": agent_id,
                "logicalUrl": logical_url,
                "plan_id": plan_id,
                "subscriber_address": subscriber_address,
            }
        except Exception:
            plans_msg = ""
            try:
                plans = self._payments.agents.get_agent_plans(agent_id)
                if hasattr(plans, "__await__"):
                    plans = await plans
                items = (plans or {}).get("plans", [])
                if isinstance(items, list) and items:
                    top = items[:3]
                    summary = ", ".join(
                        f"{p.get('planId') or p.get('id') or 'plan'}"
                        + (f" ({p.get('name')})" if p.get("name") else "")
                        for p in top
                    )
                    plans_msg = f" Available plans: {summary}..." if summary else ""
            except Exception:
                pass
            raise create_rpc_error(
                ERROR_CODES["PaymentRequired"],
                f"Payment required.{plans_msg}",
                {"reason": "invalid"},
            )
