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
from payments_py.x402.token import decode_access_token
from payments_py.x402.helpers import (
    build_payment_required,
    build_payment_required_for_plans,
)
from payments_py.x402.schemes import is_valid_scheme

from .types import HttpRequestContext

logger = logging.getLogger(__name__)

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
        self.latest_agent_request: Any = None
        self.latest_agent_request_id: str | None = None

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

    def _get_payment_extension_params(self, agent_card: Any = None) -> dict:
        """Extract params from the urn:nevermined:payment extension on the agent card.

        Args:
            agent_card: Optional agent card to use. Falls back to self._agent_card.

        Returns an empty dict if the extension is not found.
        """
        card = agent_card if agent_card is not None else self._agent_card
        capabilities = (
            card.get("capabilities", {})
            if isinstance(card, dict)
            else getattr(card, "capabilities", {})
        )
        extensions = (
            capabilities.get("extensions", [])
            if isinstance(capabilities, dict)
            else getattr(capabilities, "extensions", [])
        )
        for ext in extensions:
            ext_dict = ext if isinstance(ext, dict) else ext.__dict__
            if ext_dict.get("uri") == "urn:nevermined:payment":
                params = ext_dict.get("params", {})
                # Normalize SimpleNamespace to dict for uniform .get() access
                if not isinstance(params, dict):
                    params = vars(params) if hasattr(params, "__dict__") else {}
                return params
        return {}

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
        Validates a request using the x402 payments service.
        This method is used by the middleware to validate credits before processing requests.

        Args:
            agent_id: The agent ID to validate
            bearer_token: The bearer token for authentication (x402 access token)
            url_requested: The URL being requested
            http_method_requested: The HTTP method being used

        Returns:
            The validation result containing plan_id, subscriber_address, and verification status

        Raises:
            PaymentsError: If validation fails
        """
        # Try to get plan_id / plan_ids from agent card's payment extension first
        params = self._get_payment_extension_params()
        plan_id = params.get("planId") or params.get("plan_id")
        plan_ids = params.get("planIds") or params.get("plan_ids")

        # Normalize to list
        resolved_plan_ids: list[str] = (
            plan_ids
            if isinstance(plan_ids, list) and plan_ids
            else ([plan_id] if plan_id else [])
        )

        # Decode x402 token to extract subscriber_address (and fallback plan_id if not in agent card)
        decoded = decode_access_token(bearer_token)
        logging.getLogger(__name__).debug(
            f"[validate_request] plan_ids from agent card: {resolved_plan_ids}"
        )
        logging.getLogger(__name__).debug(
            f"[validate_request] decoded token keys: {list(decoded.keys()) if decoded else 'None'}"
        )
        if not decoded:
            raise PaymentsError.unauthorized("Invalid access token")

        # If no plan_ids found in agent card, try token
        if not resolved_plan_ids:
            decoded_plan_id = decoded.get("planId") or decoded.get("plan_id")
            if decoded_plan_id:
                resolved_plan_ids = [decoded_plan_id]

        # Extract subscriber_address from x402 token (payload.authorization.from per x402 spec)
        payload = decoded.get("payload", {})
        authorization = (
            payload.get("authorization", {}) if isinstance(payload, dict) else {}
        )
        subscriber_address = (
            authorization.get("from") if isinstance(authorization, dict) else None
        )

        if not resolved_plan_ids or not subscriber_address:
            logging.getLogger(__name__).error(
                f"[validate_request] FAILED - plan_ids: {resolved_plan_ids}, subscriber_address: {subscriber_address}"
            )
            raise PaymentsError.unauthorized(
                "Cannot determine plan_id or subscriber_address from token (expected payload.authorization.from)"
            )

        # Extract scheme from decoded token if available
        accepted = decoded.get("accepted", {})
        token_scheme = (
            accepted.get("scheme", "nvm:erc4337")
            if isinstance(accepted, dict)
            else "nvm:erc4337"
        )
        scheme = token_scheme if is_valid_scheme(token_scheme) else "nvm:erc4337"

        # Build paymentRequired using the helper
        payment_required = build_payment_required_for_plans(
            plan_ids=resolved_plan_ids,
            endpoint=url_requested,
            agent_id=agent_id,
            http_verb=http_method_requested,
            scheme=scheme,
        )

        # Use run_in_executor since verify_permissions is synchronous
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: self._payments.facilitator.verify_permissions(
                payment_required=payment_required,
                x402_access_token=bearer_token,
                max_amount="1",  # Verify at least 1 credit
            ),
        )

        if not result.is_valid:
            raise PaymentsError.payment_required(
                result.invalid_reason or "Permission verification failed"
            )

        # Capture observability data from the verify result
        self.latest_agent_request = getattr(result, "agent_request", None)
        self.latest_agent_request_id = getattr(result, "agent_request_id", None)

        # Return validation data with plan_id and subscriber_address for later use
        return {
            "success": True,
            "plan_id": resolved_plan_ids[0],
            "plan_ids": resolved_plan_ids,
            "subscriber_address": subscriber_address,
            "scheme": scheme,
            "balance": {"isSubscriber": True},  # Compatibility with existing checks
            "agent_request_id": self.latest_agent_request_id,
            "agent_request": self.latest_agent_request,
        }

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

        # Get agentId from agent card payment extension
        agent_card = await self.get_agent_card()
        ext_params = self._get_payment_extension_params(agent_card)
        agent_id = ext_params.get("agentId") or ext_params.get("agent_id")

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
            result, interrupted_or_non_blocking = await self._consume_and_burn_credits(
                result_aggregator, consumer, http_ctx, blocking
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
            await producer_task

            final_consumer = EventConsumer(queue)

            try:
                async for event in final_consumer.consume_all():
                    if (
                        isinstance(event, TaskStatusUpdateEvent)
                        and event.final is True
                        and hasattr(event, "metadata")
                        and event.metadata
                        and event.metadata.get("creditsUsed") is not None
                        and http_ctx.bearer_token
                    ):
                        await self._handle_task_finalization_from_event(event, http_ctx)
                        break

            except Exception as e:
                logger.warning(
                    "Error consuming final events for task %s: %s", task_id, e
                )

            await asyncio.sleep(0.2)

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("Monitor task failed for %s: %s", task_id, e)
        finally:
            self.delete_http_ctx_for_task(task_id)

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

    async def _cleanup_producer(
        self, producer_task: "asyncio.Task[None]", task_id: str
    ) -> None:
        """Wait for producer to finish naturally (no cancellation) and clean up.

        Unlike the parent SDK implementation, this does NOT cancel the producer
        task.  In non-blocking mode the producer must run to completion so the
        background consumer can observe the final event and settle credits.
        """
        try:
            await producer_task
        except Exception:  # noqa: BLE001
            pass
        try:
            await self._queue_manager.close(task_id)
        except Exception:  # noqa: BLE001
            pass
        async with self._running_agents_lock:
            self._running_agents.pop(task_id, None)

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
                        await result_aggregator.task_manager.process(event)

                        if event_callback:
                            await event_callback(event)

                        if (
                            isinstance(event, TaskStatusUpdateEvent)
                            and event.final is True
                            and hasattr(event, "metadata")
                            and event.metadata
                            and event.metadata.get("creditsUsed") is not None
                            and http_ctx.bearer_token
                        ):
                            await self._handle_task_finalization_from_event(
                                event, http_ctx
                            )

                # Replace _continue_consuming — the result_aggregator is
                # per-request so no restore is needed.  The background task
                # created by consume_and_break_on_interrupt resolves
                # _continue_consuming AFTER this method returns, so restoring
                # it in a finally block would undo the replacement before the
                # background task ever runs.
                result_aggregator._continue_consuming = (
                    background_credit_burning_processor
                )

                # Let SDK do its normal non-blocking flow
                result = await result_aggregator.consume_and_break_on_interrupt(
                    consumer, blocking=blocking
                )
                return result
        finally:
            # Restore original consume_all if it wasn't already restored
            if consumer.consume_all != original_consume_all:
                consumer.consume_all = original_consume_all

    def _resolve_agent_request_id(
        self, http_ctx: HttpRequestContext, event_metadata: dict | None
    ) -> str | None:
        """Resolve agent_request_id from validation context, falling back to event metadata."""
        return http_ctx.validation.get("agent_request_id") or (
            event_metadata.get("agentRequestId") if event_metadata else None
        )

    async def _handle_task_finalization_from_event(
        self, event: TaskStatusUpdateEvent, http_ctx: HttpRequestContext
    ) -> None:
        """Handle credit burning from TaskStatusUpdateEvent using x402 settle_permissions."""
        if not event.metadata or not event.metadata.get("creditsUsed"):
            return

        credits_used = event.metadata["creditsUsed"]
        plan_id = http_ctx.validation.get("plan_id")
        scheme = http_ctx.validation.get("scheme", "nvm:erc4337")

        if not plan_id:
            return  # Cannot settle without plan_id

        agent_request_id = self._resolve_agent_request_id(http_ctx, event.metadata)

        # Get agentId from agent card
        ext_params = self._get_payment_extension_params()
        agent_id = ext_params.get("agentId") or ext_params.get("agent_id")

        # Build paymentRequired using the helper
        payment_required = build_payment_required(
            plan_id=plan_id,
            endpoint=http_ctx.url_requested,
            agent_id=agent_id,
            http_verb=http_ctx.http_method_requested,
            scheme=scheme,
        )

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: self._payments.facilitator.settle_permissions(
                    payment_required=payment_required,
                    x402_access_token=http_ctx.bearer_token,
                    max_amount=str(int(credits_used)),
                    agent_request_id=agent_request_id,
                ),
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "Failed to settle %s credits during task finalization",
                credits_used,
                exc_info=True,
            )

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

        # Get agentId from agent card for settle operations
        ext_params = self._get_payment_extension_params()
        agent_id = ext_params.get("agentId") or ext_params.get("agent_id")

        # Call parent streaming method and process events
        async for event in super().on_message_send_stream(params, context):
            # Handle credit burning on final TaskStatusUpdateEvent using x402 settle_permissions
            if (
                isinstance(event, TaskStatusUpdateEvent)
                and event.final is True
                and event.metadata
                and event.metadata.get("creditsUsed") is not None
                and http_ctx.bearer_token
            ):
                credits_used = event.metadata["creditsUsed"]
                plan_id = http_ctx.validation.get("plan_id")

                if plan_id:
                    agent_request_id = self._resolve_agent_request_id(
                        http_ctx, event.metadata
                    )
                    scheme = http_ctx.validation.get("scheme", "nvm:erc4337")
                    payment_required = build_payment_required(
                        plan_id=plan_id,
                        endpoint=http_ctx.url_requested,
                        agent_id=agent_id,
                        http_verb=http_ctx.http_method_requested,
                        scheme=scheme,
                    )

                    try:
                        loop = asyncio.get_running_loop()
                        await loop.run_in_executor(
                            None,
                            lambda: self._payments.facilitator.settle_permissions(
                                payment_required=payment_required,
                                x402_access_token=http_ctx.bearer_token,
                                max_amount=str(int(credits_used)),
                                agent_request_id=agent_request_id,
                            ),
                        )
                    except Exception:  # noqa: BLE001
                        logger.warning(
                            "Failed to settle credits for task %s",
                            getattr(event, "task_id", "?"),
                            exc_info=True,
                        )

            # Handle push notifications on final status updates
            if (
                isinstance(event, TaskStatusUpdateEvent)
                and event.final is True
                and event.status
                and event.status.state in _TERMINAL_STATES
            ):
                try:
                    task_id = event.task_id
                    state = event.status.state
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
