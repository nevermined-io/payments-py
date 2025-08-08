"""Registry that caches PaymentsClient instances keyed by agent_base_url, agent_id and plan_id."""

from __future__ import annotations

from typing import Dict

from typing import TYPE_CHECKING

from .payments_client import PaymentsClient

if TYPE_CHECKING:  # pragma: no cover
    from payments_py.payments import Payments


class ClientRegistry:  # noqa: D101
    def __init__(self, payments: "Payments") -> None:  # type: ignore[name-defined]
        # Delayed import keeps runtime free from circular dependency issues.
        self._payments = payments
        self._clients: Dict[str, PaymentsClient] = {}

    # ------------------------------------------------------------------
    # Public helpers
    # ------------------------------------------------------------------
    def get_client(
        self,
        *,
        agent_base_url: str,
        agent_id: str,
        plan_id: str,
    ) -> PaymentsClient:
        """Return a cached or newly created PaymentsClient instance."""
        if not agent_base_url or not agent_id or not plan_id:
            raise ValueError("agent_base_url, agent_id and plan_id are required")
        key = f"{agent_base_url}::{agent_id}::{plan_id}"
        if key not in self._clients:
            self._clients[key] = PaymentsClient(
                agent_base_url=agent_base_url,
                payments=self._payments,
                agent_id=agent_id,
                plan_id=plan_id,
            )
        return self._clients[key]
