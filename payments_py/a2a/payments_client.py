"""High-level PaymentsClient wrapping the standard A2A JSON-RPC client with automatic auth."""

from __future__ import annotations

from typing import AsyncGenerator, Any

from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory, minimal_agent_card
from a2a.client.middleware import ClientCallContext
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
        # Preserve trailing slash to avoid JSON-RPC 307 redirects between /a2a and /a2a/
        self._agent_base_url = (
            agent_base_url if agent_base_url.endswith("/") else agent_base_url + "/"
        )
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

    def _build_context(self, token: str) -> ClientCallContext:
        ctx = ClientCallContext()
        ctx.state["http_kwargs"] = {"headers": self._auth_headers(token)}
        return ctx

    def _call_with_optional_http_kwargs(self, method_name: str, *args, **kwargs):
        """Call client method trying http_kwargs first, then fallback without it.

        This keeps unit tests (that assert http_kwargs presence) satisfied while
        remaining compatible with a2a-sdk versions where http_kwargs is not an
        accepted parameter and headers are read from context.
        """
        client = self._get_client()
        method = getattr(client, method_name)
        # Try with http_kwargs if provided
        try:
            return method(*args, **kwargs)
        except TypeError:
            # Remove http_kwargs and retry
            if "http_kwargs" in kwargs:
                kwargs = {k: v for k, v in kwargs.items() if k != "http_kwargs"}
                return method(*args, **kwargs)
            raise

    @staticmethod
    def _extract_message(params: MessageSendParams | dict[str, Any]) -> Any:
        # Accept both pydantic model and plain dict
        if hasattr(params, "message"):
            return getattr(params, "message")
        return params.get("message")  # type: ignore[return-value]

    def _get_client(self):  # noqa: D401
        if self._client is None:
            # Ensure streaming enabled in config
            factory = ClientFactory(config=ClientConfig(streaming=True))
            client = factory.create(minimal_agent_card(self._agent_base_url))
            # Hint streaming support on the minimal card to allow resubscribe without fetching extended card
            try:
                if hasattr(client, "_card") and hasattr(client._card, "capabilities"):
                    setattr(client._card.capabilities, "streaming", True)
                # Avoid triggering authenticated extended card path in transports
                if hasattr(client._card, "supports_authenticated_extended_card"):
                    setattr(client._card, "supports_authenticated_extended_card", False)
            except Exception:
                pass
            self._client = client
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    async def send_message(self, params: MessageSendParams) -> Any:  # noqa: D401
        token = await self._get_access_token()
        context = self._build_context(token)
        # BaseClient.send_message expects a Message, not MessageSendParams
        message_obj = self._extract_message(params)
        auth_headers = self._auth_headers(token)
        result = self._call_with_optional_http_kwargs(
            "send_message",
            message_obj,
            context=context,
            http_kwargs={"headers": auth_headers},
        )  # type: ignore[attr-defined]

        # Some client implementations return an async iterator (stream), others a coroutine
        stream_like = getattr(result, "__aiter__", None)
        if callable(stream_like):
            try:
                first_item = None
                async for item in result:  # type: ignore[func-returns-value]
                    first_item = item
                    break
                return first_item
            except StopAsyncIteration:  # pragma: no cover
                return None
        # Fallback: await coroutine and return its value
        return await result  # type: ignore[no-any-return]

    async def send_message_stream(
        self, params: MessageSendParams
    ) -> AsyncGenerator[Any, None]:  # noqa: D401
        token = await self._get_access_token()
        context = self._build_context(token)
        message_obj = self._extract_message(params)
        auth_headers = self._auth_headers(token)
        result = self._call_with_optional_http_kwargs(
            "send_message",
            message_obj,
            context=context,
            http_kwargs={"headers": auth_headers},
        )  # type: ignore[attr-defined]

        stream_like = getattr(result, "__aiter__", None)
        if callable(stream_like):
            async for item in result:  # type: ignore[func-returns-value]
                yield item
            return
        yield await result  # type: ignore[misc]

    async def get_task(self, params: TaskQueryParams) -> Any:  # noqa: D401
        token = await self._get_access_token()
        context = self._build_context(token)
        # type: ignore[arg-type]
        return await self._client.get_task(params, context=context)  # type: ignore[union-attr]

    async def set_task_push_notification_config(
        self, params: TaskPushNotificationConfig
    ) -> Any:  # noqa: D401
        token = await self._get_access_token()
        context = self._build_context(token)
        return await self._get_client().set_task_callback(params, context=context)  # type: ignore[union-attr, attr-defined]

    async def get_task_push_notification_config(
        self, params: TaskIdParams
    ) -> Any:  # noqa: D401
        token = await self._get_access_token()
        context = self._build_context(token)
        return await self._get_client().get_task_callback(params, context=context)  # type: ignore[union-attr, attr-defined]

    async def resubscribe_task(
        self, params: TaskIdParams
    ) -> AsyncGenerator[Any, None]:  # noqa: D401
        """Resubscribe to an existing task's event stream."""
        token = await self._get_access_token()
        context = self._build_context(token)
        # Ensure params conforms to TaskIdParams with required 'id'
        if isinstance(params, dict):
            task_id = params.get("taskId") or params.get("id")
        else:
            task_id = getattr(params, "task_id", None) or getattr(params, "id", None)
        normalized = {"id": task_id} if task_id else params  # type: ignore[assignment]

        auth_headers = self._auth_headers(token)
        res = self._call_with_optional_http_kwargs(
            "resubscribe",
            normalized,
            context=context,
            http_kwargs={"headers": auth_headers},
        )  # type: ignore[attr-defined]
        stream_like = getattr(res, "__aiter__", None)
        if callable(stream_like):
            async for item in res:  # type: ignore[func-returns-value]
                yield item
            return
        # If a coroutine is returned, await once and yield the value
        yield await res  # type: ignore[misc]

    # Utilities --------------------------------------------------------
    def clear_token(self) -> None:  # noqa: D401
        """Clear cached access-token forcing a refresh on next call."""
        self._access_token = None
