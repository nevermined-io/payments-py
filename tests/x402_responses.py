"""Factories for the x402 facilitator response models used across the suite.

Tests that stub ``facilitator.verify_permissions`` / ``settle_permissions`` need
something to hand back. Historically every such test hand-rolled an attribute
bag::

    class SettleResult:
        def __init__(self, success=True, transaction="0x123"):
            self.success = success
            self.transaction = transaction

Those bags drift. They only ever carry the fields the production code happened
to read on the day they were written, so the first code path to read a field the
bag never had blows up with ``AttributeError`` — and adding a field to
:class:`~payments_py.x402.types.SettleResponse` turns a wall of unrelated tests
red for a reason that has nothing to do with the change (payments-py#273, where
all 12 doubles in the suite had drifted).

Building the *real* Pydantic model instead removes the failure mode: every field
the model declares exists on the double, populated by the model's own defaults,
so a new field is inert in tests that do not care about it. The factories below
keep call sites as short as the bags were.

Note the model itself cannot supply the other half of the guarantee: both
response models use Pydantic's default ``extra="ignore"``, so a typo'd or
removed field would be silently dropped rather than raised. ``_build`` therefore
validates override names against ``model_fields`` — a stale keyword is a
``TypeError`` at the call site, which is where it can be understood.
"""

from typing import Any, Dict, Type, TypeVar

from pydantic import BaseModel

from payments_py.x402.types import SettleResponse, VerifyResponse

__all__ = [
    "DEFAULT_NETWORK",
    "DEFAULT_PAYER",
    "SETTLE_DEFAULTS",
    "VERIFY_DEFAULTS",
    "make_settle_response",
    "make_verify_response",
]

#: CAIP-2 network the rest of the suite's fixture tokens are minted against.
DEFAULT_NETWORK = "eip155:84532"
#: Subscriber address the fixture tokens are issued to.
DEFAULT_PAYER = "0xTestSubscriber"

#: A settle response shaped the way the facilitator really answers a successful
#: burn: every field the backend populates is populated here too, so a test that
#: reads one gets a value rather than an attribute error.
SETTLE_DEFAULTS: Dict[str, Any] = {
    "success": True,
    "transaction": "0x123",
    "network": DEFAULT_NETWORK,
    "payer": DEFAULT_PAYER,
    "credits_redeemed": "1",
    "remaining_balance": "100",
}

#: Likewise for a successful verify. ``agent_request`` / ``agent_request_id`` /
#: ``url_matching`` stay unset because the backend only returns them when
#: observability is configured; tests that assert on them pass them explicitly.
VERIFY_DEFAULTS: Dict[str, Any] = {
    "is_valid": True,
    "network": DEFAULT_NETWORK,
    "payer": DEFAULT_PAYER,
}

_M = TypeVar("_M", bound=BaseModel)


def _build(model: Type[_M], defaults: Dict[str, Any], overrides: Dict[str, Any]) -> _M:
    unknown = sorted(set(overrides) - set(model.model_fields))
    if unknown:
        raise TypeError(
            f"{model.__name__} has no field(s) {unknown}. "
            f"Known fields: {sorted(model.model_fields)}"
        )
    return model(**{**defaults, **overrides})


def make_settle_response(**overrides: Any) -> SettleResponse:
    """Build a real :class:`SettleResponse`, overriding any subset of fields.

    Field names are the Python (snake_case) ones, not the wire aliases.
    """
    return _build(SettleResponse, SETTLE_DEFAULTS, overrides)


def make_verify_response(**overrides: Any) -> VerifyResponse:
    """Build a real :class:`VerifyResponse`, overriding any subset of fields.

    Field names are the Python (snake_case) ones, not the wire aliases.
    """
    return _build(VerifyResponse, VERIFY_DEFAULTS, overrides)
