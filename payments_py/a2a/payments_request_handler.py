"""PaymentsRequestHandler adds payments validation & credit burning on top of DefaultRequestHandler."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Dict

import httpx
from a2a.server.events.event_consumer import EventConsumer
from a2a.server.events.event_queue import EventQueue
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.result_aggregator import ResultAggregator
from a2a.types import (
    Message,
    MessageSendParams,
    Task,
    TaskIdParams,
    TaskStatusUpdateEvent,
)
from payments_py.common.payments_error import PaymentsError
from payments_py.payments import Payments

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

    def delete_http_ctx_for_task(self, task_id: str) -> None:  # noqa: D401
        self._http_ctx_by_task.pop(task_id, None)

    def delete_http_ctx_for_message(self, message_id: str) -> None:  # noqa: D401
        self._http_ctx_by_message.pop(message_id, None)

    def migrate_http_ctx_from_message_to_task(
        self, message_id: str, task_id: str
    ) -> None:  # noqa: D401
        self._migrate_http_ctx_from_message_to_task(message_id, task_id)

    async def validate_request(
        self,
        agent_id: str,
        bearer_token: str,
        url_requested: str,
        http_method_requested: str,
    ) -> Any:
        """
        Validates a request using the payments service.
        This method is used by the middleware to validate credits before processing requests.

        Args:
            agent_id: The agent ID to validate
            bearer_token: The bearer token for authentication
            url_requested: The URL being requested
            http_method_requested: The HTTP method being used

        Returns:
            The validation result containing agentRequestId and other validation data

        Raises:
            PaymentsError: If validation fails
        """
        # Use run_in_executor since start_processing_request is synchronous
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._payments.requests.start_processing_request(  # type: ignore[attr-defined]
                agent_id,
                bearer_token,
                url_requested,
                http_method_requested,
            ),
        )

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
        prev_task_id = params.message.task_id
        http_ctx = None
        if prev_task_id:
            http_ctx = self._get_http_ctx(prev_task_id, None)
        else:
            http_ctx = self._get_http_ctx(None, params.message.message_id)

        if http_ctx is None:
            raise PaymentsError.unauthorized(
                "HTTP context missing for request; bearer token not found."
            )

        # Get agentId from agent card (like TypeScript)
        agent_card = await self.get_agent_card()

        # Extract agentId from payment extension (handle both dict and SimpleNamespace)
        agent_id = None
        if hasattr(agent_card, "get"):
            # Dictionary-style access
            extensions = agent_card.get("capabilities", {}).get("extensions", [])
        else:
            # Object-style access (SimpleNamespace)
            capabilities = getattr(agent_card, "capabilities", None)
            extensions = getattr(capabilities, "extensions", []) if capabilities else []

        for ext in extensions:
            if (hasattr(ext, "get") and ext.get("uri") == "urn:nevermined:payment") or (
                hasattr(ext, "uri") and ext.uri == "urn:nevermined:payment"
            ):
                # Handle both dict and SimpleNamespace for params
                if hasattr(ext, "get"):
                    agent_id = ext.get("params", {}).get("agentId")
                else:
                    ext_params = getattr(ext, "params", None)
                    agent_id = (
                        getattr(ext_params, "agentId", None) if ext_params else None
                    )
                break

        if not agent_id:
            raise PaymentsError.internal("Agent ID not found in payment extension.")

        # Setup message execution (equivalent to TS setup)
        (
            task_manager,
            task_id,
            queue,
            result_aggregator,
            producer_task,
        ) = await self._setup_message_execution(params, context)

        # migrate HTTP context from message to task
        if not prev_task_id:
            self._migrate_http_ctx_from_message_to_task(
                params.message.message_id, task_id
            )
            # Update the message with the new taskId
            params.message.task_id = task_id

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
            # Both blocking and non-blocking use the same method, but with different
            # early return behavior
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
            logging.getLogger(__name__).error(f"Agent execution failed. Error: {e}")
            raise
        finally:
            # Cleanup like parent implementation
            if interrupted_or_non_blocking:
                # For non-blocking mode, schedule background cleanup (like parent SDK
                # does)
                asyncio.create_task(self._cleanup_producer(producer_task, task_id))
            else:
                await self._cleanup_producer(producer_task, task_id)

    async def _monitor_for_final_events(
        self,
        task_id: str,
        http_ctx: HttpRequestContext,
        producer_task: "asyncio.Task[None]",
        queue: "EventQueue",
    ) -> None:
        """Monitor for final events with credit burning in non-blocking mode."""
        try:
            print(f"[DEBUG] Starting monitor for final events for {task_id}")

            # Wait for the producer task to complete (this publishes the final event)
            await producer_task
            print(f"[DEBUG] Producer task completed for {task_id}")

            # Create a new consumer to check for any remaining events in the queue
            final_consumer = EventConsumer(queue)

            print(
                f"[DEBUG] Created final consumer for {task_id}, checking for final events"
            )

            # Check for any remaining events (with timeout)
            try:
                async for event in final_consumer.consume_all():
                    print(
                        f"[DEBUG] monitor_for_final_events got event: {type(event)} - {getattr(event, 'kind', 'no-kind')} - final: {getattr(event, 'final', 'no-final')}"
                    )

                    if (
                        isinstance(event, TaskStatusUpdateEvent)
                        and event.final is True
                        and hasattr(event, "metadata")
                        and event.metadata
                        and event.metadata.get("creditsUsed") is not None
                        and http_ctx.bearer_token
                    ):
                        print(
                            f"[DEBUG] Found final event with creditsUsed: {event.metadata.get('creditsUsed')}"
                        )
                        await self._handle_task_finalization_from_event(event, http_ctx)
                        break

            except Exception as e:
                print(f"[DEBUG] Error consuming final events: {e}")

            # Give a bit more time for any delayed events
            await asyncio.sleep(0.2)

        except asyncio.CancelledError:
            print(f"[DEBUG] Monitor task cancelled for {task_id}")
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Monitor task failed for {task_id}: {e}"
            )
            print(f"[DEBUG] Monitor task exception: {e}")
        finally:
            # Clean up HTTP context
            self.delete_http_ctx_for_task(task_id)
            print(f"[DEBUG] Monitor cleanup completed for {task_id}")

    async def _delayed_cleanup_for_non_blocking(
        self,
        producer_task: "asyncio.Task[None]",
        task_id: str,
        http_ctx: HttpRequestContext,
        result_aggregator: ResultAggregator,
    ) -> None:
        """Wait for task completion in non-blocking mode, then cleanup."""
        try:
            # Wait for the producer task to complete naturally (don't cancel it)
            await producer_task

            # After producer completes, ensure we've processed all events
            # Give some time for final events to be processed
            await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            # If cancelled, that's expected behavior
            pass
        except Exception as e:
            logging.getLogger(__name__).warning(
                f"Producer task failed for {task_id}: {e}"
            )
        finally:
            # Clean up HTTP context
            self.delete_http_ctx_for_task(task_id)

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
        """Process events with credit burning (like TypeScript processEventsWithFinalization).

        This mirrors TypeScript processEventsWithFinalization with:
        - Credit burning on final events with creditsUsed metadata
        - Background processing continuation when interrupted (via SDK's _continue_consuming)
        """
        # Store the original consume_all method before replacing it
        original_consume_all = consumer.consume_all

        # Create a custom event processor that intercepts events for credit burning
        async def credit_burning_event_processor():
            async for event in original_consume_all():
                print(
                    f"[DEBUG] credit_burning_event_processor got event: {type(event)} - {getattr(event, 'kind', 'no-kind')} - final: {getattr(event, 'final', 'no-final')} - metadata: {getattr(event, 'metadata', 'no-metadata')}"
                )

                # Handle credit burning on TaskStatusUpdateEvent (like TypeScript
                # handleTaskFinalization)
                if (
                    isinstance(event, TaskStatusUpdateEvent)
                    and event.final is True
                    and hasattr(event, "metadata")
                    and event.metadata
                    and event.metadata.get("creditsUsed") is not None
                    and http_ctx.bearer_token
                ):
                    print(
                        f"[DEBUG] Processing credit burning for final event: {event.metadata.get('creditsUsed')} credits"
                    )
                    await self._handle_task_finalization_from_event(event, http_ctx)

                yield event

        # Replace consumer's consume_all with our credit burning processor
        consumer.consume_all = credit_burning_event_processor

        try:
            if blocking:
                # Blocking mode: intercept events in main flow (current working
                # approach)
                return await result_aggregator.consume_and_break_on_interrupt(
                    consumer, blocking=blocking
                )
            else:
                # Non-blocking mode: don't intercept main flow, but intercept background processing
                # First, restore original consumer to avoid interfering with SDK's early
                # return logic
                consumer.consume_all = original_consume_all

                # Intercept the _continue_consuming method for background credit burning
                original_continue_consuming = result_aggregator._continue_consuming

                async def background_credit_burning_processor(
                    event_stream, event_callback=None
                ):
                    """Process background events with credit burning."""
                    async for event in event_stream:
                        print(
                            f"[DEBUG] background_credit_burning_processor got event: {type(event)} - {getattr(event, 'kind', 'no-kind')} - final: {getattr(event, 'final', 'no-final')}"
                        )

                        # Process the event normally (like original _continue_consuming)
                        await result_aggregator.task_manager.process(event)

                        # Call the event callback if provided (to match SDK signature)
                        if event_callback:
                            await event_callback(event)

                        # Check for credit burning on final events
                        if (
                            isinstance(event, TaskStatusUpdateEvent)
                            and event.final is True
                            and hasattr(event, "metadata")
                            and event.metadata
                            and event.metadata.get("creditsUsed") is not None
                            and http_ctx.bearer_token
                        ):
                            print(
                                f"[DEBUG] Background credit burning for: {event.metadata.get('creditsUsed')} credits"
                            )
                            await self._handle_task_finalization_from_event(
                                event, http_ctx
                            )

                # Replace _continue_consuming temporarily
                result_aggregator._continue_consuming = (
                    background_credit_burning_processor
                )

                try:
                    # Let SDK do its normal non-blocking flow
                    result = await result_aggregator.consume_and_break_on_interrupt(
                        consumer, blocking=blocking
                    )
                    return result
                finally:
                    # Restore original _continue_consuming
                    result_aggregator._continue_consuming = original_continue_consuming
        finally:
            # Restore original consume_all if it wasn't already restored
            if consumer.consume_all != original_consume_all:
                consumer.consume_all = original_consume_all

    async def _handle_task_finalization_from_event(
        self, event: TaskStatusUpdateEvent, http_ctx: HttpRequestContext
    ) -> None:
        """Handle credit burning from TaskStatusUpdateEvent (like TypeScript handleTaskFinalization)."""
        if not event.metadata or not event.metadata.get("creditsUsed"):
            return

        print(f"[DEBUG] Handling task finalization from event: {event}")

        credits_used = event.metadata["creditsUsed"]
        try:
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
        # type: ignore[arg-type]
        async for event in super().on_message_send_stream(params, context):
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

    async def _send_push_notification_if_needed(
        self, task_id: str, result_aggregator: Any
    ) -> None:
        """Send push notification if needed for completed task."""
        try:
            # Get the final result to check if task is completed
            task = await result_aggregator.task_manager.get_task()
            if task and task.status.state in _TERMINAL_STATES:
                # Get push notification config
                push_cfg = await self.on_get_task_push_notification_config(
                    TaskIdParams(id=task_id)
                )
                if push_cfg and "pushNotificationConfig" in push_cfg:
                    await self._send_push_notification(
                        task_id,
                        task.status.state,
                        push_cfg["pushNotificationConfig"],
                    )
        except Exception:  # noqa: BLE001
            # Swallow push notification errors (non-blocking)
            pass

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
        headers: Dict[str, str] = {"Content-Type": "application/json"}
        if auth := push_notification_config.get("authentication"):
            schemes = auth.get("schemes", [])
            creds = auth.get("credentials")
            if "basic" in schemes:
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
