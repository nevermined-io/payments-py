"""
Authentication handler for MCP paywall.
"""

from typing import Any, Dict

from ..utils.request import extract_auth_header, strip_bearer
from ..utils.logical_url import build_logical_url, build_logical_meta_url
from ..utils.errors import create_rpc_error, ERROR_CODES


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
            start = self._payments.requests.start_processing_request(
                agent_id,
                token,
                logical_url,
                "POST",
            )
            # support sync or async clients
            if hasattr(start, "__await__"):
                start = await start

            if not start or not start.get("balance", {}).get("isSubscriber", False):
                raise ValueError("Not a subscriber")

            return {
                "requestId": start.get("agentRequestId"),
                "token": token,
                "agentId": agent_id,
                "logicalUrl": logical_url,
                "agentRequest": start,
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
            start = self._payments.requests.start_processing_request(
                agent_id,
                token,
                logical_url,
                "POST",
            )
            if hasattr(start, "__await__"):
                start = await start
            if not start or not start.get("balance", {}).get("isSubscriber", False):
                raise ValueError("Not a subscriber")
            return {
                "requestId": start.get("agentRequestId"),
                "token": token,
                "agentId": agent_id,
                "logicalUrl": logical_url,
                "agentRequest": start,
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
