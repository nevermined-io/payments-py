"""Utilities for setting up agents and plans for A2A E2E tests."""

import random
from typing import Dict
from payments_py.payments import Payments
from payments_py.common.types import AgentMetadata, PlanMetadata
from payments_py.plans import get_erc20_price_config, get_fixed_credits_config
from tests.e2e.utils import retry_with_backoff

ERC20_ADDRESS = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"


def _get_random_int(min_val: int, max_val: int) -> int:
    """Generate a random integer between min_val and max_val (inclusive)."""
    return random.randint(min_val, max_val)


def create_a2a_test_agent_and_plan(
    payments_builder: Payments,
    port: int,
    base_path: str = "/a2a/",
    credits_per_request: int = 1,
) -> Dict[str, str]:
    """
    Create an agent and plan for A2A E2E tests.

    Args:
        payments_builder: Payments instance with builder permissions
        port: Port where the A2A server will run
        base_path: Base path for the A2A server (default: "/a2a/")
        credits_per_request: Credits per request (default: 1)

    Returns:
        Dictionary containing agentId, planId, and serverBaseUrl
    """
    import time

    timestamp = time.strftime("%Y%m%d_%H%M%S")

    # Create plan metadata
    plan_metadata = PlanMetadata(
        name=f"A2A E2E Test Plan {timestamp}",
        description=f"Payment plan for A2A E2E tests {timestamp}",
    )

    # Create agent metadata
    agent_metadata = AgentMetadata(
        name=f"A2A E2E Test Agent {timestamp}",
        description=f"Agent for A2A E2E tests {timestamp}",
        tags=["a2a", "e2e", "test"],
    )

    # Create agent API with A2A endpoint
    server_base_url = f"http://localhost:{port}{base_path}"
    agent_definition_url = f"{server_base_url}.well-known/agent.json"
    agent_api = {
        "endpoints": [{"POST": server_base_url}],
        "agentDefinitionUrl": agent_definition_url,
    }

    builder_address = payments_builder.get_account_address()

    # Use random price and credits for tests (random between 1 and 1000)
    price = _get_random_int(1, 1000)
    credits_granted = _get_random_int(1, 1000)

    price_config = get_erc20_price_config(price, ERC20_ADDRESS, builder_address)

    # Create credits config
    credits_config = get_fixed_credits_config(credits_granted, credits_per_request)

    # First, register the plan
    response = retry_with_backoff(
        lambda: payments_builder.plans.register_credits_plan(
            plan_metadata=plan_metadata,
            price_config=price_config,
            credits_config=credits_config,
        ),
        label="A2A Credits Plan Registration",
        attempts=3,
    )
    plan_id = response["planId"]

    # Then, register the agent with the created plan
    agent_result = retry_with_backoff(
        lambda: payments_builder.agents.register_agent(
            agent_metadata=agent_metadata,
            agent_api=agent_api,
            payment_plans=[plan_id],
        ),
        label="A2A Agent Registration",
        attempts=3,
    )

    agent_id = agent_result["agentId"]

    print(
        f"✅ Created A2A test agent and plan - Agent ID: {agent_id}, Plan ID: {plan_id}"
    )

    return {
        "agentId": agent_id,
        "planId": plan_id,
        "serverBaseUrl": server_base_url,
    }
