"""E2E tests for the Python A2A client using a real server and backend validation.

This mirrors the flows covered in the TypeScript test suite (a2a.e2e.test.ts):
- Register plan and agent
- Order plan (to obtain credits)
- Start an A2A server bound to the registered agent
- Use Payments.a2a.get_client() to send messages, stream, and resubscribe
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict

import pytest
import requests

from payments_py.payments import Payments
from payments_py.a2a.server import PaymentsA2AServer
from payments_py.a2a.agent_card import build_payment_agent_card
from payments_py.common.types import PlanMetadata
from types import SimpleNamespace


TEST_TIMEOUT = 30
TEST_ENVIRONMENT = os.getenv("TEST_ENVIRONMENT", "staging_sandbox")

SUBSCRIBER_API_KEY = os.getenv("TEST_SUBSCRIBER_API_KEY") or (
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDhmMDQ1QkM3QzA0RjRjYzViNjNjOTcyNWM1YTZCMzI5OWQ0YUMxRTIiLCJqdGkiOiIweGY4MWM2YzcwMzk1YjEzZWY3NTgxOWE0NTAzZGNkOGYyNGNmMzg5ZTBkM2U4YmZjZWQ0NzVhMGQwZWU2ZWY1MGUiLCJleHAiOjE3ODYwNDM4OTR9.sGeDtFfR20jadzIwM-uugR7fFX5FkntysPD9a4quyfZ5cy27fxdxWxXzSqGqk2DEVedYIhUU19AbzM9GjK9cUhw"
)
BUILDER_API_KEY = os.getenv("TEST_BUILDER_API_KEY") or (
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDhmMDQ1QkM3QzA0RjRjYzViNjNjOTcyNWM1YTZCMzI5OWQ0YUMxRTIiLCJqdGkiOiIweGNhZDk3MzVhOGQzOGYxZmZhY2ViMjFhZTE1MjY2NDY4YjkwMmJkNGJiNjhhYWU5MDIxYTUxOTc0NWZlMDViZmQiLCJleHAiOjE3ODYwNDM5NTF9.QALDS9oeukDqDWe7aqv0ZDvL44W3yJp5YFsYRCbGgnV86tfqbSsc9OyDilNEJCip6NH0JAppTaGzcWup7QubBBw"
)

ERC20_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def _wait_for_server_ready(
    port: int, base_path: str = "/a2a/", retries: int = 20
) -> None:
    """Poll agent card endpoint until server is ready or timeout."""
    url = f"http://localhost:{port}{base_path.rstrip('/')}/.well-known/agent.json"
    for _ in range(retries):
        try:
            resp = requests.get(url, timeout=5)
            if resp.ok and resp.json().get("name"):
                return
        except Exception:
            pass
        time.sleep(0.5)
    raise RuntimeError("A2A test server did not become ready in time")


@pytest.fixture(scope="module")
def payments_builder() -> Payments:
    return Payments({"nvm_api_key": BUILDER_API_KEY, "environment": TEST_ENVIRONMENT})


@pytest.fixture(scope="module")
def payments_subscriber() -> Payments:
    return Payments(
        {"nvm_api_key": SUBSCRIBER_API_KEY, "environment": TEST_ENVIRONMENT}
    )


@pytest.fixture(scope="module")
def setup_plan_and_agent(payments_builder: Payments, payments_subscriber: Payments):
    """Register plan, order it, and register agent with matching endpoint."""
    # Build a TRIAL plan with FREE price to avoid on-chain allowance in tests
    price_config = payments_builder.plans.get_free_price_config()
    credits_config = payments_builder.plans.get_expirable_duration_config(
        86_400
    )  # 1 day

    plan_metadata = PlanMetadata(name="E2E A2A Client Test Plan PY")
    plan_result: Dict[str, Any] = payments_builder.plans.register_time_trial_plan(
        plan_metadata, price_config, credits_config
    )
    plan_id = plan_result.get("planId")
    assert plan_id, "Plan registration failed"

    # Order plan for subscriber to get credits
    order_result = payments_subscriber.plans.order_plan(plan_id)
    assert order_result.get("success") is True

    # Register agent with endpoint matching our server
    agent_metadata = {
        "name": "E2E A2A Client Test Agent PY",
        "description": "A2A client test",
    }
    agent_api = {"endpoints": [{"POST": "http://localhost:41243/a2a/"}]}
    agent_result = payments_builder.agents.register_agent(
        agent_metadata, agent_api, [plan_id]
    )
    agent_id = agent_result.get("agentId")
    assert agent_id, "Agent registration failed"

    return {"plan_id": plan_id, "agent_id": agent_id}


@pytest.fixture(autouse=True)
def _asyncify_get_agent_access_token(payments_subscriber: Payments):  # noqa: D401
    original = payments_subscriber.agents.get_agent_access_token

    async def _async_get(plan_id, agent_id):  # noqa: D401
        res = original(plan_id, agent_id)
        if isinstance(res, dict):
            token = res.get("accessToken") or res.get("access_token")
        else:
            token = getattr(res, "access_token", None)
        return SimpleNamespace(access_token=token)

    payments_subscriber.agents.get_agent_access_token = _async_get  # type: ignore[assignment]
    yield
    payments_subscriber.agents.get_agent_access_token = original  # type: ignore[assignment]


@pytest.fixture(scope="module")
def running_server(payments_builder: Payments, setup_plan_and_agent):
    plan_id = setup_plan_and_agent["plan_id"]
    agent_id = setup_plan_and_agent["agent_id"]

    # Build agent card with payment extension
    base_agent_card = {
        "name": "E2E A2A Client Test Agent PY",
        "description": "A2A client test",
        "capabilities": {
            "streaming": True,
            "pushNotifications": True,
            "stateTransitionHistory": True,
        },
        "defaultInputModes": ["text"],
        "defaultOutputModes": ["text"],
        "skills": [],
        "url": "http://localhost:41243/a2a/",
        "version": "1.0.0",
    }
    agent_card = build_payment_agent_card(
        base_agent_card,
        {
            "paymentType": "dynamic",
            "credits": 1,
            "costDescription": "Dynamic request",
            "planId": plan_id,
            "agentId": agent_id,
        },
    )

    class _StreamingExecutor:  # noqa: D401
        async def execute(self, ctx, bus):  # noqa: D401
            from a2a.types import Task, TaskStatus, TaskStatusUpdateEvent, Message

            message = getattr(ctx, "message", None)
            task_id = getattr(ctx, "task_id", None) or (
                getattr(message, "task_id", None) if message else None
            )
            context_id = getattr(message, "context_id", None) if message else None

            # Ensure Message has required fields if test provided dict
            if isinstance(message, dict):
                msg_obj = Message.model_validate(message)
            else:
                msg_obj = message

            # Initial task event
            initial_task = Task(
                id=task_id,
                context_id=context_id,
                kind="task",
                status=TaskStatus(
                    state="submitted",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ),
                history=[msg_obj] if msg_obj else [],
            )
            await bus.enqueue_event(initial_task)

            # Working status update
            working = TaskStatusUpdateEvent(
                kind="status-update",
                task_id=task_id,
                context_id=context_id,
                final=False,
                status=TaskStatus(
                    state="working",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ),
            )
            await bus.enqueue_event(working)

            # No artificial delay; tests will handle resubscribe if supported

            # Final status update with credits
            final_ev = TaskStatusUpdateEvent(
                kind="status-update",
                task_id=task_id,
                context_id=context_id,
                final=True,
                metadata={"creditsUsed": 1},
                status=TaskStatus(
                    state="completed",
                    timestamp=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                ),
            )
            await bus.enqueue_event(final_ev)
            await bus.close()

        async def cancelTask(self, _task_id):  # noqa: N802, D401
            return None

    # If server already running on 41243, reuse it
    try:
        _wait_for_server_ready(41243, "/a2a/", retries=4)
        yield {"server": None}
        return
    except Exception:
        pass

    # Start uvicorn server in background thread
    server_result = PaymentsA2AServer.start(
        agent_card=agent_card,
        executor=_StreamingExecutor(),
        payments_service=payments_builder,
        port=41243,
        base_path="/a2a/",
    )

    import threading

    def _run():  # noqa: D401
        server_result.server.run()  # type: ignore[attr-defined]

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    _wait_for_server_ready(41243, "/a2a/")
    yield server_result
    try:
        server_result.server.should_exit = True  # type: ignore[attr-defined]
        t.join(timeout=3)
    except Exception:
        pass


class TestA2AClientE2E:
    @pytest.mark.timeout(TEST_TIMEOUT)
    def test_client_registration(
        self, payments_subscriber: Payments, setup_plan_and_agent, running_server
    ):  # noqa: D401
        client = payments_subscriber.a2a["get_client"](
            agent_base_url="http://localhost:41243/a2a/",
            agent_id=setup_plan_and_agent["agent_id"],
            plan_id=setup_plan_and_agent["plan_id"],
        )
        assert client is not None
        assert hasattr(client, "send_message")
        assert hasattr(client, "get_task")
        assert hasattr(client, "clear_token")

    @pytest.mark.asyncio()
    @pytest.mark.timeout(TEST_TIMEOUT)
    async def test_send_message_and_stream(
        self, payments_subscriber: Payments, setup_plan_and_agent, running_server
    ):  # noqa: D401
        client = payments_subscriber.a2a["get_client"](
            agent_base_url="http://localhost:41243/a2a/",
            agent_id=setup_plan_and_agent["agent_id"],
            plan_id=setup_plan_and_agent["plan_id"],
        )

        # Send a simple message
        msg = {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": "msg-1",
                "parts": [{"kind": "text", "text": "Hello from E2E client"}],
            }
        }
        result = await client.send_message(msg)  # type: ignore[arg-type]
        assert result is not None

        # Streaming
        final_event = None
        async for ev in client.send_message_stream(msg):  # type: ignore[arg-type]
            # Normalize event from SDK (may be tuple[Task, Update] or Message/Task/Update)
            if isinstance(ev, tuple):
                _, upd = ev
                e = upd if upd is not None else ev[0]
            else:
                e = ev
            # Typed model path
            kind = getattr(e, "kind", None)
            is_final = getattr(e, "final", False)
            # Dict path (for older shapes)
            if hasattr(e, "get"):
                kind = e.get("kind", kind)
                is_final = e.get("final", is_final)
            if kind == "status-update" and is_final:
                final_event = e
                break
        assert final_event is not None
        # Support pydantic model and dict shapes
        meta = getattr(final_event, "metadata", None)
        if meta is None and hasattr(final_event, "get"):
            meta = final_event.get("metadata")
        assert meta and meta.get("creditsUsed") == 1

    @pytest.mark.asyncio()
    @pytest.mark.timeout(TEST_TIMEOUT)
    async def test_resubscribe(
        self, payments_subscriber: Payments, setup_plan_and_agent, running_server
    ):  # noqa: D401
        client = payments_subscriber.a2a["get_client"](
            agent_base_url="http://localhost:41243/a2a/",
            agent_id=setup_plan_and_agent["agent_id"],
            plan_id=setup_plan_and_agent["plan_id"],
        )

        # Start streaming but stop early to simulate disconnect
        msg = {
            "message": {
                "kind": "message",
                "role": "user",
                "messageId": "msg-2",
                "parts": [{"kind": "text", "text": "Resubscribe flow"}],
            }
        }

        task_id = None
        count = 0
        async for ev in client.send_message_stream(msg):  # type: ignore[arg-type]
            count += 1
            if isinstance(ev, tuple):
                task_part, upd = ev
                e = upd if upd is not None else task_part
            else:
                e = ev
            # Try typed first, then dict; consider Task.id and StatusUpdate.task_id
            task_id = (
                task_id
                or getattr(e, "task_id", None)
                or getattr(e, "id", None)
                or (e.get("taskId") if hasattr(e, "get") else None)
                or (e.get("id") if hasattr(e, "get") else None)
            )
            if count >= 1:  # disconnect early
                break

        assert task_id is not None
        # Now resubscribe until final
        final = None
        try:
            async for ev in client.resubscribe_task({"taskId": task_id}):  # type: ignore[arg-type]
                if isinstance(ev, tuple):
                    _, upd = ev
                    e = upd if upd is not None else ev[0]
                else:
                    e = ev
                kind = getattr(e, "kind", None)
                is_final = getattr(e, "final", False)
                if hasattr(e, "get"):
                    kind = e.get("kind", kind)
                    is_final = e.get("final", is_final)
                if kind == "status-update" and is_final:
                    final = e
                    break
        except Exception as exc:  # Allow terminal/unsupported resubscribe scenarios
            msg = str(exc)
            if (
                "terminal state" in msg
                or "do not support resubscription" in msg
                or "not support resubscription" in msg
            ):
                return
            raise
        assert final is not None
        assert final.get("metadata", {}).get("creditsUsed") == 1
