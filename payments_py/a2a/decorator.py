"""Decorator to turn a simple async function into a payment-protected A2A agent."""

from __future__ import annotations

import asyncio
import datetime
import functools
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Optional
from uuid import uuid4

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.events.event_queue import EventQueue
from a2a.types import (
    Message,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)

from payments_py.a2a.types import AgentCard

if TYPE_CHECKING:
    from payments_py.payments import Payments

logger = logging.getLogger(__name__)


@dataclass
class AgentResponse:
    """Simple return type for decorated agent functions.

    Attributes:
        text: The text response from the agent.
        credits_used: Number of credits consumed. Falls back to the decorator's
            ``default_credits`` when *None*.
        metadata: Optional extra metadata to include in the final event.
    """

    text: str
    credits_used: Optional[int] = None
    metadata: Optional[dict] = field(default_factory=lambda: None)


# ---------------------------------------------------------------------------
# Internal executor that wraps the user function
# ---------------------------------------------------------------------------
class _DecoratorExecutor(AgentExecutor):
    """AgentExecutor that delegates to a user-provided async function."""

    def __init__(
        self,
        handler: Callable[..., Awaitable[AgentResponse]],
        default_credits: int,
    ) -> None:
        self._handler = handler
        self._default_credits = default_credits

    async def execute(
        self, context: Any, event_queue: EventQueue
    ) -> None:  # noqa: D401
        task_id = context.task_id or str(uuid4())
        context_id = context.context_id or str(uuid4())

        # Publish initial Task (submitted)
        if not (hasattr(context, "current_task") and context.current_task):
            initial_task = Task(
                id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.submitted,
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
                history=[],
            )
            await event_queue.enqueue_event(initial_task)

        # Publish working status
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.working,
                    message=Message(
                        message_id=str(uuid4()),
                        role=Role.agent,
                        parts=[{"kind": "text", "text": "Processing…"}],
                        task_id=task_id,
                        context_id=context_id,
                    ),
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
                final=False,
            )
        )

        # Call the user function
        try:
            response: AgentResponse = await self._handler(context)
        except Exception as exc:
            # Publish failed status
            await event_queue.enqueue_event(
                TaskStatusUpdateEvent(
                    task_id=task_id,
                    context_id=context_id,
                    status=TaskStatus(
                        state=TaskState.failed,
                        message=Message(
                            message_id=str(uuid4()),
                            role=Role.agent,
                            parts=[{"kind": "text", "text": f"Error: {exc}"}],
                            task_id=task_id,
                            context_id=context_id,
                        ),
                        timestamp=datetime.datetime.now(
                            datetime.timezone.utc
                        ).isoformat(),
                    ),
                    metadata={"creditsUsed": 0},
                    final=True,
                )
            )
            return

        credits_used = (
            response.credits_used
            if response.credits_used is not None
            else self._default_credits
        )

        event_metadata: dict[str, Any] = {"creditsUsed": credits_used}
        if response.metadata:
            event_metadata.update(response.metadata)

        # Publish completed status with creditsUsed metadata
        agent_message = Message(
            message_id=str(uuid4()),
            role=Role.agent,
            parts=[{"kind": "text", "text": response.text}],
            task_id=task_id,
            context_id=context_id,
        )

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.completed,
                    message=agent_message,
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
                metadata=event_metadata,
                final=True,
            )
        )

    async def cancel(self, context: Any, event_queue: EventQueue) -> None:  # noqa: D401
        task_id = getattr(context, "task_id", None) or str(uuid4())
        context_id = getattr(context, "context_id", None) or str(uuid4())

        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=task_id,
                context_id=context_id,
                status=TaskStatus(
                    state=TaskState.canceled,
                    message=Message(
                        message_id=str(uuid4()),
                        role=Role.agent,
                        parts=[{"kind": "text", "text": "Task cancelled."}],
                        task_id=task_id,
                        context_id=context_id,
                    ),
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                ),
                metadata={"creditsUsed": 0},
                final=True,
            )
        )


# ---------------------------------------------------------------------------
# Public decorator
# ---------------------------------------------------------------------------
def a2a_requires_payment(
    *,
    payments: Payments,
    agent_card: AgentCard,
    default_credits: int = 1,
    async_execution: bool = False,
) -> Callable[
    [Callable[..., Awaitable[AgentResponse]]],
    Callable[..., Awaitable[AgentResponse]],
]:
    """Decorator that turns an async function into a payment-protected A2A agent.

    The decorated function receives a ``RequestContext`` (from the a2a SDK) and
    must return an :class:`AgentResponse`.  The decorator wires up all the
    Nevermined payment middleware (verify / settle) automatically.

    Usage::

        @a2a_requires_payment(
            payments=payments,
            agent_card=agent_card,
            default_credits=1,
        )
        async def my_agent(context: RequestContext) -> AgentResponse:
            text = context.get_user_input()
            return AgentResponse(text=f"Echo: {text}", credits_used=1)

        # Start serving
        my_agent.serve(port=8080)

    Args:
        payments: A :class:`Payments` instance configured for the publisher.
        agent_card: An agent card dict enriched with the ``urn:nevermined:payment``
            extension (see :func:`build_payment_agent_card`).
        default_credits: Credits to burn when ``AgentResponse.credits_used`` is
            *None*.  Defaults to ``1``.
        async_execution: When *True*, the server returns immediately and the
            agent executes in the background (non-blocking mode).

    Returns:
        A decorated async callable with an added ``.serve(port)`` method.
    """

    def decorator(
        fn: Callable[..., Awaitable[AgentResponse]],
    ) -> Callable[..., Awaitable[AgentResponse]]:
        executor = _DecoratorExecutor(fn, default_credits)

        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> AgentResponse:
            return await fn(*args, **kwargs)

        # Attach the executor so tests can inspect it
        wrapper.executor = executor  # type: ignore[attr-defined]
        wrapper.agent_card = agent_card  # type: ignore[attr-defined]
        wrapper.payments = payments  # type: ignore[attr-defined]

        def serve(
            *,
            port: int = 8080,
            base_path: str = "/",
            expose_agent_card: bool = True,
            hooks: dict[str, Any] | None = None,
            app: Any | None = None,
        ) -> None:
            """Start the A2A server (blocking)."""
            from payments_py.a2a.server import PaymentsA2AServer

            result = PaymentsA2AServer.start(
                agent_card=agent_card,
                executor=executor,
                payments_service=payments,
                port=port,
                base_path=base_path,
                expose_agent_card=expose_agent_card,
                hooks=hooks,
                async_execution=async_execution,
                app=app,
            )
            asyncio.run(result.server.serve())

        def create_server(
            *,
            port: int = 8080,
            base_path: str = "/",
            expose_agent_card: bool = True,
            hooks: dict[str, Any] | None = None,
            app: Any | None = None,
        ) -> Any:
            """Create (but don't start) the A2A server.

            Returns:
                A :class:`PaymentsA2AServerResult` with ``app``, ``server``,
                and ``handler`` attributes.
            """
            from payments_py.a2a.server import PaymentsA2AServer

            return PaymentsA2AServer.start(
                agent_card=agent_card,
                executor=executor,
                payments_service=payments,
                port=port,
                base_path=base_path,
                expose_agent_card=expose_agent_card,
                hooks=hooks,
                async_execution=async_execution,
                app=app,
            )

        wrapper.serve = serve  # type: ignore[attr-defined]
        wrapper.create_server = create_server  # type: ignore[attr-defined]

        return wrapper

    return decorator
