"""High-level PaymentsClient wrapping the standard A2A JSON-RPC client with automatic auth."""

from __future__ import annotations

from typing import AsyncGenerator, Any

from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory, minimal_agent_card
from a2a.types import (
    MessageSendParams,
    TaskQueryParams,
    TaskPushNotificationConfig,
    TaskIdParams,
)

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from payments_py.payments import Payments


class PaymentsClient:  # noqa: D101
    def __init__(
        self, *, agent_base_url: str, payments: "Payments", agent_id: str, plan_id: str
    ) -> None:
        self._agent_base_url = agent_base_url.rstrip("/")
        self._payments = payments
        self._agent_id = agent_id
        self._plan_id = plan_id
        self._access_token: str | None = None
        self._client = None  # Lazily created to ease unit testing

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    async def _get_access_token(self) -> str:
        if self._access_token is None:
            token_resp = await self._payments.agents.get_agent_access_token(
                self._plan_id, self._agent_id
            )
            self._access_token = token_resp.access_token  # type: ignore[attr-defined]
        return self._access_token

    def _auth_headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def _get_client(self):  # noqa: D401
        if self._client is None:
            factory = ClientFactory(config=ClientConfig())
            self._client = factory.create(minimal_agent_card(self._agent_base_url))
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def send_message(self, params: MessageSendParams) -> Any:  # noqa: D401
        token = await self._get_access_token()
        client = self._get_client()
        # type: ignore[arg-type]
        return await client.send_message(
            params, http_kwargs={"headers": self._auth_headers(token)}
        )

    async def send_message_stream(
        self, params: MessageSendParams
    ) -> AsyncGenerator[Any, None]:  # noqa: D401
        token = await self._get_access_token()
        client = self._get_client()
        async for item in client.send_message_streaming(  # type: ignore[attr-defined]
            params,
            http_kwargs={"headers": self._auth_headers(token)},
        ):
            yield item

    async def get_task(self, params: TaskQueryParams) -> Any:  # noqa: D401
        token = await self._get_access_token()
        client = self._get_client()
        # type: ignore[arg-type]
        return await client.get_task(
            params, http_kwargs={"headers": self._auth_headers(token)}
        )

    async def set_task_push_notification_config(
        self, params: TaskPushNotificationConfig
    ) -> Any:  # noqa: D401
        token = await self._get_access_token()
        client = self._get_client()
        return await client.set_task_callback(  # type: ignore[attr-defined]
            params,
            http_kwargs={"headers": self._auth_headers(token)},
        )

    async def get_task_push_notification_config(
        self, params: TaskIdParams
    ) -> Any:  # noqa: D401
        token = await self._get_access_token()
        client = self._get_client()
        return await client.get_task_callback(  # type: ignore[attr-defined]
            params,
            http_kwargs={"headers": self._auth_headers(token)},
        )

    async def resubscribe_task(
        self, params: TaskIdParams
    ) -> AsyncGenerator[Any, None]:  # noqa: D401
        """Resubscribe to an existing task's event stream."""
        token = await self._get_access_token()
        client = self._get_client()
        async for item in client.resubscribe(  # type: ignore[attr-defined]
            params,
            http_kwargs={"headers": self._auth_headers(token)},
        ):
            yield item

    # Utilities --------------------------------------------------------
    def clear_token(self) -> None:  # noqa: D401
        """Clear cached access-token forcing a refresh on next call."""
        self._access_token = None
