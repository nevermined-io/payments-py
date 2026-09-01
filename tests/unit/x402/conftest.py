"""Shared fixtures for the x402 unit tests."""

import pytest


@pytest.fixture(autouse=True)
def reset_last_settlement():
    """Clear the decorator's module-level settlement holder between tests.

    ``requires_payment`` stashes the most recent ``SettleResponse`` in a
    module-level slot because LangGraph runs tools in worker contexts that
    do not propagate ContextVar mutations back to the caller (see
    ``payments_py.x402.langchain.decorator``). That slot is process-wide,
    so without this reset one test's settlement leaks into the next.

    The private ``_LAST_SETTLEMENT`` holder is reached directly because
    ``last_settlement()`` is read-only and the SDK exposes no public
    reset. Keeping that coupling in **one** place means a change to how
    the value is stored breaks a single fixture rather than every test
    module that needs a clean slate.

    Imported lazily so this conftest stays importable — and the rest of
    the x402 tests stay collectable — in environments without the
    optional ``langchain-core`` dependency.
    """
    try:
        from payments_py.x402.langchain import decorator as decorator_module
    except ImportError:
        yield
        return

    decorator_module._LAST_SETTLEMENT["value"] = None
    yield
    decorator_module._LAST_SETTLEMENT["value"] = None
