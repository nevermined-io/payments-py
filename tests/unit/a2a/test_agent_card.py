"""Unit tests for build_payment_agent_card utility."""

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


import pytest


# noqa: WPS437
@pytest.mark.parametrize(  # type: ignore[arg-type]
    "meta,err",
    [
        ({"credits": 0, "agentId": "x"}, "paymentType is required"),
        (
            {"paymentType": "fixed", "credits": -1, "agentId": "x"},
            "credits cannot be negative",
        ),
        (
            {"paymentType": "fixed", "credits": 0, "agentId": "x"},
            "credits must be a positive number",
        ),
        ({"paymentType": "fixed", "credits": 1}, "agentId is required"),
    ],
)
def test_build_payment_agent_card_validation_errors(meta, err):  # noqa: D401
    base_card = {"capabilities": {}}
    with pytest.raises(ValueError) as exc:
        build_payment_agent_card(base_card, meta)  # type: ignore[arg-type]
    assert err.split(" ")[0] in str(exc.value)
