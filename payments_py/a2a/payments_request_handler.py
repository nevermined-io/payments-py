"""PaymentsRequestHandler adds payments validation & credit burning on top of DefaultRequestHandler."""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Dict

from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.events.event_queue import EventQueue
from a2a.server.events.event_consumer import EventConsumer
from a2a.server.tasks.result_aggregator import ResultAggregator
from a2a.server.tasks.task_manager import TaskManager
from a2a.types import (
    MessageSendParams,
    Task,
    Message,
    TaskStatusUpdateEvent,
    TaskIdParams,
    TaskStatus,
    TaskState,
    Part,
)
from payments_py.payments import Payments
from payments_py.common.payments_error import PaymentsError

from .types import HttpRequestContext


_TERMINAL_STATES = {
    "completed",
    "failed",
    "canceled",
    "rejected",
}


class PaymentsRequestHandler(DefaultRequestHandler):  # noqa: D101
    """Extend DefaultRequestHandler adding credit validation & burning."""

    # ------------------------------------------------------------------
    # Lifecycle --------------------------------------------------------
    # ------------------------------------------------------------------
    def __init__(
        self,
        *,
        agent_card: Any,  # a2a.types.AgentCard
        task_store: Any,
        agent_executor: Any,
        payments_service: Payments,
        queue_manager: Any | None = None,
        push_config_store: Any | None = None,
        push_sender: Any | None = None,
        request_context_builder: Any | None = None,
        async_execution: bool = False,
    ) -> None:
        super().__init__(
            agent_executor=agent_executor,
            task_store=task_store,
            queue_manager=queue_manager,
            push_config_store=push_config_store,
            push_sender=push_sender,
            request_context_builder=request_context_builder,
        )
        self._agent_card = agent_card
        self._payments = payments_service
        self._async_execution = async_execution
        self._http_ctx_by_task: Dict[str, HttpRequestContext] = {}
        self._http_ctx_by_message: Dict[str, HttpRequestContext] = {}

    # ------------------------------------------------------------------
    # Context helpers (called by middleware) ---------------------------
    # ------------------------------------------------------------------
    def set_http_ctx_for_task(
        self, task_id: str, ctx: HttpRequestContext
    ) -> None:  # noqa: D401
        self._http_ctx_by_task[task_id] = ctx

    def set_http_ctx_for_message(
        self, message_id: str, ctx: HttpRequestContext
    ) -> None:  # noqa: D401
        self._http_ctx_by_message[message_id] = ctx

    # ------------------------------------------------------------------
    def _get_http_ctx(
        self, task_id: str | None, message_id: str | None
    ) -> HttpRequestContext | None:  # noqa: D401
        if task_id and task_id in self._http_ctx_by_task:
            return self._http_ctx_by_task[task_id]
        if message_id and message_id in self._http_ctx_by_message:
            return self._http_ctx_by_message[message_id]
        return None

    def _migrate_http_ctx_from_message_to_task(
        self, message_id: str, task_id: str
    ) -> None:  # noqa: D401
        """Migrate HTTP context from messageId to taskId when task is created."""
        if message_id in self._http_ctx_by_message:
            ctx = self._http_ctx_by_message.pop(message_id)
            self._http_ctx_by_task[task_id] = ctx

    # ------------------------------------------------------------------
    # Validation helper called by middleware ---------------------------
    # ------------------------------------------------------------------
    async def validate_request(
        self, bearer_token: str, url_requested: str, http_method_requested: str
    ) -> Dict[str, Any]:  # noqa: D401
        """Validate payments for incoming request."""
        import asyncio  # noqa: WPS433

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._payments.requests.start_processing_request(  # type: ignore[attr-defined]
                bearer_token, url_requested, http_method_requested
            ),
        )

    def delete_http_ctx_for_task(self, task_id: str) -> None:  # noqa: D401
        self._http_ctx_by_task.pop(task_id, None)

    def delete_http_ctx_for_message(self, message_id: str) -> None:  # noqa: D401
        self._http_ctx_by_message.pop(message_id, None)

    def migrate_http_ctx_from_message_to_task(
        self, message_id: str, task_id: str
    ) -> None:  # noqa: D401
        self._migrate_http_ctx_from_message_to_task(message_id, task_id)

    # ------------------------------------------------------------------
    # Overrides --------------------------------------------------------
    # ------------------------------------------------------------------
    async def on_message_send(
        self,
        params: MessageSendParams,
        context: Any | None = None,
    ) -> Task | Message:  # noqa: D401
        """Override sendMessage to add payments validation & credit burning like TypeScript."""
        # Validate required parameters
        if not params.message:
            raise PaymentsError.bad_request("message is required.")
        if not params.message.message_id:
            raise PaymentsError.bad_request("message.messageId is required.")

        # Get HTTP context for the task or message
        task_id = params.message.task_id
        http_ctx = None
        if task_id:
            http_ctx = self._get_http_ctx(task_id, None)
        else:
            http_ctx = self._get_http_ctx(None, params.message.message_id)

        if http_ctx is None:
            raise PaymentsError.unauthorized(
                "HTTP context missing for request; bearer token not found."
            )

        # Get agentId from agent card (like TypeScript)
        agent_card = await self.get_agent_card()
        agent_id = None
        if (
            hasattr(agent_card, "capabilities")
            and agent_card.capabilities
            and hasattr(agent_card.capabilities, "extensions")
            and agent_card.capabilities.extensions
        ):
            for ext in agent_card.capabilities.extensions:
                if hasattr(ext, "uri") and ext.uri == "urn:nevermined:payment":
                    if hasattr(ext, "params") and hasattr(ext.params, "agentId"):
                        agent_id = ext.params.agentId
                        break

        if not agent_id:
            raise PaymentsError.internal("Agent ID not found in payment extension.")

        # Generate taskId if not present and migrate HTTP context
        if not task_id:
            from uuid import uuid4

            task_id = str(uuid4())
            self._migrate_http_ctx_from_message_to_task(
                params.message.message_id, task_id
            )
            # Update the message with the new taskId
            params.message.task_id = task_id

        # Setup message execution (equivalent to TS setup)
        (
            task_manager,
            task_id,
            queue,
            result_aggregator,
            producer_task,
        ) = await self._setup_message_execution(params, context)

        consumer = EventConsumer(queue)
        producer_task.add_done_callback(consumer.agent_task_callback)

        # Determine if execution should be blocking
        blocking = True
        if (
            hasattr(params, "configuration")
            and params.configuration
            and params.configuration.blocking is False
        ):
            blocking = False

        interrupted_or_non_blocking = False
        try:
            # Process events with credit burning (like TypeScript processEventsWithFinalization)
            (result, interrupted_or_non_blocking) = (
                await self._consume_and_burn_credits(
                    result_aggregator, consumer, http_ctx, blocking
                )
            )

            if not result:
                raise PaymentsError.internal(
                    "Agent execution finished without a result, and no task context found."
                )

            if isinstance(result, Task):
                self._validate_task_id_match(task_id, result.id)

            await self._send_push_notification_if_needed(task_id, result_aggregator)

            return result

        except Exception as e:
            import logging

            logging.getLogger(__name__).error(f"Agent execution failed. Error: {e}")
            raise
        finally:
            # Cleanup like parent implementation
            if interrupted_or_non_blocking:
                asyncio.create_task(self._cleanup_producer(producer_task, task_id))
            else:
                await self._cleanup_producer(producer_task, task_id)

    async def _cleanup_producer(self, producer_task, task_id: str) -> None:
        """Cleanup producer task (from parent implementation)."""
        if not producer_task.done():
            producer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass

    async def _consume_and_burn_credits(
        self,
        result_aggregator: ResultAggregator,
        consumer: EventConsumer,
        http_ctx: HttpRequestContext,
        blocking: bool = True,
    ) -> tuple[Task | Message, bool]:
        """Process events with credit burning, mimicking parent's consume_and_break_on_interrupt."""

        # Create a custom event processor that intercepts events for credit burning
        async def credit_burning_event_processor():
            async for event in consumer.consume_all():
                # Handle credit burning on TaskStatusUpdateEvent (like TypeScript handleTaskFinalization)
                if (
                    isinstance(event, TaskStatusUpdateEvent)
                    and event.final is True
                    and hasattr(event, "metadata")
                    and event.metadata
                    and event.metadata.get("creditsUsed") is not None
                    and http_ctx.bearer_token
                ):
                    await self._handle_task_finalization_from_event(event, http_ctx)

                yield event

        # Replace consumer's consume_all with our credit burning processor
        original_consume_all = consumer.consume_all
        consumer.consume_all = credit_burning_event_processor

        try:
            # Use parent's logic for event processing
            return await result_aggregator.consume_and_break_on_interrupt(
                consumer, blocking=blocking
            )
        finally:
            # Restore original consume_all
            consumer.consume_all = original_consume_all

    async def _handle_task_finalization_from_event(
        self, event: TaskStatusUpdateEvent, http_ctx: HttpRequestContext
    ) -> None:
        """Handle credit burning from TaskStatusUpdateEvent (like TypeScript handleTaskFinalization)."""
        if not event.metadata or not event.metadata.get("creditsUsed"):
            return

        credits_used = event.metadata["creditsUsed"]
        try:
            import asyncio  # noqa: WPS433

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self._payments.requests.redeem_credits_from_request(  # type: ignore[attr-defined]
                    http_ctx.validation["agentRequestId"],
                    http_ctx.bearer_token,
                    int(credits_used),
                ),
            )
        except Exception:  # noqa: BLE001
            # Swallow redeem errors (non-blocking)
            pass

    # ------------------------------------------------------------------
    # Streaming override ------------------------------------------------
    # ------------------------------------------------------------------
    async def on_message_send_stream(
        self,
        params: MessageSendParams,
        context: Any | None = None,
    ) -> Any:  # noqa: D401
        """Override streaming to handle credit burning when TaskStatusUpdateEvent arrives."""
        # Retrieve HTTP context
        http_ctx = self._get_http_ctx(
            params.message.task_id if params.message else None,
            params.message.message_id if params.message else None,
        )
        if http_ctx is None:
            raise PaymentsError.unauthorized(
                "HTTP context missing for request; bearer token not found."
            )

        # Call parent streaming method and process events
        async for event in super().on_message_send_stream(params, context):  # type: ignore[arg-type]
            # Handle credit burning on final status updates
            if (
                isinstance(event, dict)
                and event.get("kind") == "status-update"
                and event.get("final") is True
                and event.get("metadata", {}).get("creditsUsed") is not None
                and http_ctx.bearer_token
            ):
                credits_used = event["metadata"]["creditsUsed"]
                try:
                    import asyncio  # noqa: WPS433

                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: self._payments.requests.redeem_credits_from_request(  # type: ignore[attr-defined]
                            http_ctx.validation["agentRequestId"],
                            http_ctx.bearer_token,
                            int(credits_used),
                        ),
                    )
                except Exception:  # noqa: BLE001
                    # Swallow redeem errors (non-blocking)
                    pass

            # Handle push notifications on final status updates
            if (
                isinstance(event, dict)
                and event.get("kind") == "status-update"
                and event.get("final") is True
                and event.get("status", {}).get("state") in _TERMINAL_STATES
            ):
                try:
                    task_id = event.get("taskId")
                    state = event["status"]["state"]
                    push_cfg = await self.on_get_task_push_notification_config(
                        TaskIdParams(id=task_id)
                    )
                    if push_cfg:
                        await self._send_push_notification(
                            task_id,
                            state,
                            push_cfg["pushNotificationConfig"],
                        )
                except Exception:  # noqa: BLE001
                    # Swallow push notification errors (non-blocking)
                    pass

            yield event

    # ------------------------------------------------------------------
    # Push notification helper -----------------------------------------
    # ------------------------------------------------------------------
    async def _send_push_notification(
        self,
        task_id: str,
        state: str,
        push_notification_config: Dict[str, Any],
        payload: Dict[str, Any] | None = None,
    ) -> None:
        """Send HTTP push notification (best-effort)."""
        import httpx  # noqa: WPS433

        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth := push_notification_config.get("authentication"):
            schemes = auth.get("schemes", [])
            creds = auth.get("credentials")
            if "basic" in schemes:
                import base64

                headers["Authorization"] = (
                    "Basic " + base64.b64encode(creds.encode()).decode()
                )
            elif "bearer" in schemes:
                headers["Authorization"] = f"Bearer {creds}"
            elif "custom" in schemes and isinstance(creds, dict):
                headers.update(creds)

        data = {
            "taskId": task_id,
            "state": state,
            "payload": payload or {},
        }

        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    push_notification_config["url"],
                    json=data,
                    headers=headers,
                    timeout=5.0,
                )
        except Exception:  # noqa: BLE001
            pass  # ignore push errors

    # ------------------------------------------------------------------
    # Agent card accessor -----------------------------------------------
    # ------------------------------------------------------------------
    async def get_agent_card(self) -> Any:  # noqa: D401
        return self._agent_card
