"""
LangGraph ReAct agent helper that surfaces ``PaymentRequiredError`` intact.

By default ``langgraph.prebuilt.create_react_agent`` constructs a ``ToolNode``
with ``handle_tool_errors=True`` — tool exceptions are caught and rendered into
a ``ToolMessage`` for the LLM. That is convenient for prompt-engineered recovery,
but it stringifies the exception and loses the ``X402PaymentRequired`` payload
attached to :class:`PaymentRequiredError`. Without that payload the caller
cannot run the x402 discovery flow (probe → read scheme/network/plan_id →
acquire token → retry).

:func:`create_paid_react_agent` builds the same agent but with a ``ToolNode``
configured to **re-raise** exceptions, so ``PaymentRequiredError`` propagates
all the way back to ``agent.invoke()``'s caller with ``.payment_required``
populated.

This module imports ``langgraph`` lazily so the optional ``[langchain]`` extra
need not pull in LangGraph for users who only use the ``@requires_payment``
decorator. Install LangGraph yourself (``pip install langgraph``) to use this
helper.

Example::

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI
    from payments_py.x402.langchain import (
        PaymentRequiredError,
        create_paid_react_agent,
        requires_payment,
        last_settlement,
    )

    @tool
    @requires_payment(payments=payments, plan_id=PLAN_ID, credits=1)
    def get_market_insight(topic: str, config=None) -> str:
        return f"Market insight for {topic} ..."

    agent = create_paid_react_agent(
        ChatOpenAI(model="gpt-4o-mini", temperature=0),
        [get_market_insight],
        prompt="...",
    )

    # Discovery: invoke without a token to learn what to pay for.
    try:
        agent.invoke({"messages": [...]}, config={"configurable": {}})
    except PaymentRequiredError as err:
        accept = err.payment_required.accepts[0]

    # ... acquire token using accept.plan_id / accept.scheme / accept.network ...

    result = agent.invoke({"messages": [...]}, config={"configurable": {"payment_token": token}})
    receipt = last_settlement()
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from langgraph.graph.state import CompiledStateGraph


def create_paid_react_agent(
    model: Any,
    tools: Sequence[Any],
    **kwargs: Any,
) -> "CompiledStateGraph":
    """Build a LangGraph ReAct agent that lets ``PaymentRequiredError`` propagate.

    Wraps :func:`langgraph.prebuilt.create_react_agent` with a
    ``ToolNode(tools, handle_tool_errors=False)``. All other keyword arguments
    (``prompt``, ``state_schema``, ``checkpointer``, …) are forwarded.

    Args:
        model: The chat model (or any value accepted by ``create_react_agent``'s
            ``model`` argument).
        tools: Sequence of LangChain tools, typically functions decorated with
            ``@tool`` and ``@requires_payment``.
        **kwargs: Forwarded verbatim to ``create_react_agent``. Unknown kwargs
            raise ``TypeError`` from LangGraph at call time.

    Raises:
        ImportError: If ``langgraph`` is not installed. Install it with
            ``pip install langgraph``.

    Returns:
        The compiled ReAct agent graph, ready to be invoked with
        ``agent.invoke(...)``.
    """
    try:
        from langgraph.prebuilt import ToolNode, create_react_agent
    except ImportError as err:  # pragma: no cover - import-time guard
        raise ImportError(
            "create_paid_react_agent requires langgraph. "
            "Install it with `pip install langgraph`."
        ) from err

    tool_node = ToolNode(list(tools), handle_tool_errors=False)
    return create_react_agent(model, tool_node, **kwargs)


__all__ = ["create_paid_react_agent"]
