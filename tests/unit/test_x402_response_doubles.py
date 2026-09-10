"""Guards for the x402 response factories, and against the drift they replaced.

payments-py#273: every one of the suite's 12 settle/verify test doubles was a
hand-rolled attribute bag carrying only the fields the production code happened
to read the day it was written. Adding two fields to ``SettleResponse`` turned
28 unrelated tests red with ``AttributeError``, and a double missing ``network``
could never have caught a regression in anything reading ``network``.

The fix was to build the real Pydantic models (``tests/x402_responses.py``).
These tests pin the two properties that keeps it fixed.
"""

import ast
import pathlib

import pytest

from payments_py.x402.types import SettleResponse, VerifyResponse
from tests.x402_responses import make_settle_response, make_verify_response

TESTS_ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestFactories:
    def test_settle_factory_carries_every_model_field(self):
        response = make_settle_response()
        assert isinstance(response, SettleResponse)
        for field in SettleResponse.model_fields:
            # Not a tautology about Pydantic: the point is that a *new* field on
            # the model is present on every double the day it is added, rather
            # than raising AttributeError in whichever test first reads it.
            assert hasattr(response, field)

    def test_verify_factory_carries_every_model_field(self):
        response = make_verify_response()
        assert isinstance(response, VerifyResponse)
        for field in VerifyResponse.model_fields:
            assert hasattr(response, field)

    def test_overrides_win_over_defaults(self):
        assert make_settle_response(transaction="0xfeed").transaction == "0xfeed"
        assert make_verify_response(is_valid=False).is_valid is False

    @pytest.mark.parametrize(
        "factory",
        [make_settle_response, make_verify_response],
        ids=["settle", "verify"],
    )
    def test_unknown_override_is_rejected(self, factory):
        # Both models use Pydantic's default extra="ignore", so constructing them
        # directly would silently DROP a typo'd or since-removed field name. The
        # factory has to supply that half of the guarantee itself.
        with pytest.raises(TypeError, match="has no field"):
            factory(no_such_field="x")

    def test_alias_spelling_is_rejected(self):
        # Call sites use the Python names; the camelCase wire alias would be
        # silently ignored by the model, so reject it loudly.
        with pytest.raises(TypeError, match="has no field"):
            make_settle_response(creditsRedeemed="5")


def _self_assigned_attrs(node: ast.ClassDef) -> set[str]:
    """Attribute names a class sets on instances (class body + ``__init__``)."""
    attrs: set[str] = set()
    for stmt in node.body:
        if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
            attrs.add(stmt.target.id)
        elif isinstance(stmt, ast.Assign):
            attrs.update(t.id for t in stmt.targets if isinstance(t, ast.Name))
        elif isinstance(stmt, ast.FunctionDef) and stmt.name == "__init__":
            for sub in ast.walk(stmt):
                targets = (
                    sub.targets
                    if isinstance(sub, ast.Assign)
                    else [sub.target] if isinstance(sub, ast.AnnAssign) else []
                )
                attrs.update(
                    t.attr
                    for t in targets
                    if isinstance(t, ast.Attribute)
                    and isinstance(t.value, ast.Name)
                    and t.value.id == "self"
                )
    return attrs


def test_no_hand_rolled_settle_or_verify_doubles():
    """No test class may stand in for a settle/verify response by hand.

    This is the regression guard for the whole class of defect, not for the 12
    instances that existed when it was written: a new attribute bag is caught on
    the PR that adds it rather than by the next person to touch either model.

    If this fails, use ``make_settle_response`` / ``make_verify_response`` from
    ``tests/x402_responses.py`` instead of declaring a class.
    """
    settle_fields = set(SettleResponse.model_fields)
    offenders = []

    for path in sorted(TESTS_ROOT.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ClassDef):
                continue
            attrs = _self_assigned_attrs(node)
            # "success" alone is far too common to key on; require it to look
            # like a settle response. "is_valid" is specific enough on its own.
            if ("success" in attrs and len(attrs & settle_fields) >= 2) or (
                "is_valid" in attrs
            ):
                rel = path.relative_to(TESTS_ROOT.parent)
                offenders.append(f"{rel}:{node.lineno} {node.name} {sorted(attrs)}")

    assert not offenders, (
        "Hand-rolled settle/verify response double(s) found; build the real "
        "model with tests.x402_responses instead (payments-py#273):\n  "
        + "\n  ".join(offenders)
    )
