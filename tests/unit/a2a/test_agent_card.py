"""Unit tests for build_payment_agent_card utility."""

import pytest

from payments_py.a2a.agent_card import build_payment_agent_card


def test_build_payment_agent_card_success():  # noqa: D401
    base_card = {"name": "Agent", "capabilities": {}}
    metadata = {
        "paymentType": "fixed",
        "credits": 5,
        "agentId": "agent-1",
        "planId": "plan-1",
        "costDescription": "5 credits per call",
    }
    card = build_payment_agent_card(base_card, metadata)  # type: ignore[arg-type]
    ext = card["capabilities"]["extensions"][-1]
    assert ext["uri"] == "urn:nevermined:payment"
    assert ext["params"]["agentId"] == "agent-1"


def test_build_payment_agent_card_with_plan_ids():  # noqa: D401
    """planIds (list) builds card correctly with multiple plans."""
    base_card = {"name": "Agent", "capabilities": {}}
    metadata = {
        "paymentType": "fixed",
        "credits": 5,
        "agentId": "agent-1",
        "planIds": ["plan-1", "plan-2"],
    }
    card = build_payment_agent_card(base_card, metadata)  # type: ignore[arg-type]
    ext = card["capabilities"]["extensions"][-1]
    assert ext["uri"] == "urn:nevermined:payment"
    assert ext["params"]["planIds"] == ["plan-1", "plan-2"]
    assert "planId" not in ext["params"]


# noqa: WPS437
@pytest.mark.parametrize(  # type: ignore[arg-type]
    "meta,err",
    [
        ({"credits": 0, "agentId": "x", "planId": "p"}, "paymentType is required"),
        (
            {"paymentType": "fixed", "credits": -1, "agentId": "x", "planId": "p"},
            "credits cannot be negative",
        ),
        (
            {"paymentType": "fixed", "credits": 0, "agentId": "x", "planId": "p"},
            "credits must be a positive number",
        ),
        (
            {"paymentType": "fixed", "credits": 1, "planId": "p"},
            "agentId is required",
        ),
    ],
)
def test_build_payment_agent_card_validation_errors(meta, err):  # noqa: D401
    base_card = {"capabilities": {}}
    with pytest.raises(ValueError) as exc:
        build_payment_agent_card(base_card, meta)  # type: ignore[arg-type]
    assert err.split(" ")[0] in str(exc.value)


def test_build_payment_agent_card_both_plan_id_and_plan_ids_raises():  # noqa: D401
    """Providing both planId and planIds should raise ValueError."""
    base_card = {"capabilities": {}}
    metadata = {
        "paymentType": "fixed",
        "credits": 1,
        "agentId": "agent-1",
        "planId": "plan-1",
        "planIds": ["plan-2"],
    }
    with pytest.raises(ValueError, match="Provide either planId or planIds, not both"):
        build_payment_agent_card(base_card, metadata)  # type: ignore[arg-type]


def test_build_payment_agent_card_empty_plan_ids_raises():  # noqa: D401
    """Empty planIds list should raise ValueError."""
    base_card = {"capabilities": {}}
    metadata = {
        "paymentType": "fixed",
        "credits": 1,
        "agentId": "agent-1",
        "planIds": [],
    }
    with pytest.raises(ValueError, match="planIds must be a non-empty list"):
        build_payment_agent_card(base_card, metadata)  # type: ignore[arg-type]


def test_build_payment_agent_card_no_plan_raises():  # noqa: D401
    """Neither planId nor planIds should raise ValueError."""
    base_card = {"capabilities": {}}
    metadata = {
        "paymentType": "fixed",
        "credits": 1,
        "agentId": "agent-1",
    }
    with pytest.raises(ValueError, match="Either planId or planIds is required"):
        build_payment_agent_card(base_card, metadata)  # type: ignore[arg-type]
