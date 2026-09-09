"""Registry that caches PaymentsClient instances keyed by agent_base_url, agent_id and plan_id."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict, Optional

from .payments_client import PaymentsClient

if TYPE_CHECKING:  # pragma: no cover
    from payments_py.payments import Payments
    from payments_py.x402.types import DelegationConfig, X402TokenVersion


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
        delegation_config: Optional["DelegationConfig"] = None,
        token_version: Optional["X402TokenVersion"] = None,
    ) -> PaymentsClient:
        """Return a cached or newly created PaymentsClient instance.

        ``token_version`` is the access-token version the client REQUESTS
        (``3`` for the single-use, seller/resource-bound token of
        nvm-monorepo#2646), and it IS part of the cache key.

        It has to be. Clients are only constructed on a miss, so with the key
        blind to it the first caller for a triple would win for the registry's
        lifetime: a later ``get_client(..., token_version=3)`` would be handed
        back a client that mints reusable v2 tokens, caches them, and replays
        them on every paid call — the replay protection asked for, dropped with
        no error, no warning and nothing on the returned object to inspect.
        Re-reading the version off a minted token governs how it is HANDLED,
        not which version is REQUESTED, and the registry never re-mints.
        """
        if not agent_base_url or not agent_id or not plan_id:
            raise ValueError("agent_base_url, agent_id and plan_id are required")
        key = f"{agent_base_url}::{agent_id}::{plan_id}::{token_version}"
        if key not in self._clients:
            self._clients[key] = PaymentsClient(
                agent_base_url=agent_base_url,
                payments=self._payments,
                agent_id=agent_id,
                plan_id=plan_id,
                delegation_config=delegation_config,
                token_version=token_version,
            )
        return self._clients[key]
