"""Compatibility tests: `@requires_payment` under the Deep Agents harness.

The contract these tests pin down is narrow but load-bearing:

    main agent  --task()-->  subagent  -->  paid tool

A buyer supplies the x402 access token once, on the run, at
``config["configurable"]["payment_token"]``. The supervisor never handles
it — it delegates through Deep Agents' built-in ``task`` tool, and
LangGraph copies ``configurable`` down into the subagent's own tool
calls. ``requires_payment`` therefore works **unchanged one delegation
hop away** from where the token was supplied.

That property is what makes the harness usable for monetized
capabilities at all: a deep agent's premise is that the supervisor hands
work to subagents, so if payment context did not survive the hop, every
paid tool would have to sit on the main agent.

No network and no LLM: a scripted fake chat model drives the graph
through a fixed tool-call sequence, and `Payments` is mocked. The tests
assert on the SDK's own behaviour, not on a model's willingness to
delegate.

.. note::

   ``deepagents`` requires Python >=3.11 and the LangChain v1 stack
   (``langchain>=1.3.18``, ``langgraph>=1.2.11``). The default
   ``unit_integration`` CI job pins Python 3.10 — the floor this package
   declares — and the test group pins ``langgraph = "^0.6.0"``, which is
   disjoint from what deepagents needs. So these tests ``importorskip``
   and are skipped there.

   They are **not** unguarded: the ``deepagents_compat`` job in
   ``.github/workflows/test.yaml`` runs them on Python 3.11 with a pip
   install of the v1 stack. To reproduce that locally::

       python3.11 -m venv .venv-deepagents
       .venv-deepagents/bin/pip install -e ".[langchain,langsmith]"
       .venv-deepagents/bin/pip install deepagents pytest
       .venv-deepagents/bin/pytest tests/unit/x402/test_deepagents_compat.py
"""

from typing import Any, Sequence
from unittest.mock import MagicMock

import pytest
from langchain_core.language_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from payments_py.x402.langchain import (
    PaymentRequiredError,
    last_settlement,
    requires_payment,
)
from payments_py.x402.types import SettleResponse, VerifyResponse

create_deep_agent = pytest.importorskip(
    "deepagents",
    reason="deepagents requires the LangChain v1 stack; install it to run these",
).create_deep_agent


SENTINEL_TOKEN = "x402-token-sentinel"


class ScriptedModel(FakeMessagesListChatModel):
    """Fake chat model that replays a fixed message script.

    ``FakeMessagesListChatModel`` raises ``NotImplementedError`` from
    ``bind_tools``, which the agent factory calls unconditionally. We
    accept the tools and ignore them — the script already encodes which
    tool calls to emit.
    """

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedModel":
        return self


@pytest.fixture
def mock_payments():
    """A Payments-like mock with verify + settle stubbed."""
    payments = MagicMock()
    payments.facilitator.verify_permissions.return_value = VerifyResponse(
        is_valid=True,
        invalid_reason=None,
        payer="0x1234567890abcdef",
        agent_request_id="test-request-id-123",
    )
    payments.facilitator.settle_permissions.return_value = SettleResponse(
        success=True,
        error_reason=None,
        payer="0x1234567890abcdef",
        transaction="0xabc123",
        network="eip155:84532",
        credits_redeemed="5",
        remaining_balance="95",
    )
    return payments


def _delegating_script() -> list[AIMessage]:
    """Supervisor delegates, subagent calls the paid tool, both finish.

    The models are invoked sequentially (the ``task`` tool blocks until
    the subagent returns), so a single scripted model serves both.
    """
    return [
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "task",
                    "args": {
                        "description": "research the EV market",
                        "subagent_type": "research-sub",
                    },
                    "id": "call-task-1",
                }
            ],
        ),
        AIMessage(
            content="",
            tool_calls=[
                {
                    "name": "market_research",
                    "args": {"topic": "EV market"},
                    "id": "call-tool-1",
                }
            ],
        ),
        AIMessage(content="subagent done"),
        AIMessage(content="supervisor done"),
    ]


def _build_agent(mock_payments, seen: dict):
    """Deep agent whose ONLY paid tool lives on a subagent."""

    @tool
    def market_research(topic: str, config: RunnableConfig) -> str:
        """Paid market research on a topic."""
        seen["config_received"] = config is not None
        try:
            return _paid_inner(topic, config=config)
        except PaymentRequiredError as error:
            seen["payment_required"] = str(error)
            return "PAYMENT_REQUIRED"

    @requires_payment(payments=mock_payments, plan_id="plan-123", credits=5)
    def _paid_inner(topic: str, config: RunnableConfig) -> str:
        seen["tool_body_ran"] = True
        return f"insight for {topic}"

    return create_deep_agent(
        model=ScriptedModel(responses=_delegating_script()),
        tools=[],
        subagents=[
            {
                "name": "research-sub",
                "description": "Performs paid market research.",
                "system_prompt": "Call market_research once.",
                "tools": [market_research],
            }
        ],
        system_prompt="Delegate research to research-sub.",
    )


def test_payment_token_reaches_a_subagent_tool(mock_payments):
    """The token survives the `task()` delegation hop."""
    seen: dict = {}
    agent = _build_agent(mock_payments, seen)

    agent.invoke(
        {"messages": [{"role": "user", "content": "research the EV market"}]},
        config={"configurable": {"payment_token": SENTINEL_TOKEN}},
    )

    assert seen.get("config_received") is True
    assert seen.get("tool_body_ran") is True

    # The decorator verified against the token the buyer put on the run,
    # one delegation hop above.
    mock_payments.facilitator.verify_permissions.assert_called_once()
    verify_args = mock_payments.facilitator.verify_permissions.call_args
    assert SENTINEL_TOKEN in str(verify_args)


def test_settlement_completes_from_inside_a_subagent(mock_payments):
    """verify -> body -> settle runs to completion below a delegation."""
    seen: dict = {}
    agent = _build_agent(mock_payments, seen)

    agent.invoke(
        {"messages": [{"role": "user", "content": "research the EV market"}]},
        config={"configurable": {"payment_token": SENTINEL_TOKEN}},
    )

    mock_payments.facilitator.settle_permissions.assert_called_once()

    settlement = last_settlement()
    assert settlement is not None
    assert settlement.success is True
    assert settlement.credits_redeemed == "5"
    assert settlement.remaining_balance == "95"


def test_missing_token_raises_payment_required_in_a_subagent(mock_payments):
    """Without a token the paid body never runs, and nothing settles."""
    seen: dict = {}
    agent = _build_agent(mock_payments, seen)

    agent.invoke(
        {"messages": [{"role": "user", "content": "research the EV market"}]},
        # No `payment_token` on the run.
        config={"configurable": {}},
    )

    assert "payment_required" in seen
    assert seen.get("tool_body_ran") is not True
    mock_payments.facilitator.verify_permissions.assert_not_called()
    mock_payments.facilitator.settle_permissions.assert_not_called()
