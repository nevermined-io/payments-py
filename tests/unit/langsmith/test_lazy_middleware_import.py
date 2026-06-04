"""Unit tests for the lazy (PEP 562) middleware import in ``payments_py.langsmith``.

The ``@requires_payment`` decorator imports ``payments_py.langsmith.spans`` for
its ``nvm:verify``/``nvm:settlement`` spans, which resolves the
``payments_py.langsmith`` package. Historically the package ``__init__`` eagerly
re-exported the FastAPI-based middleware, so importing it (and therefore using
``@requires_payment`` at tool time) required the ``[langsmith]`` extra even when
no HTTP app was in play (issue #1825).

These tests pin the fixed behaviour:

* importing the package and ``requires_payment`` does NOT import the
  FastAPI-dependent middleware module;
* the package imports even when ``fastapi`` is unavailable;
* referencing a middleware re-export triggers the lazy import (and would raise
  ``ImportError`` if ``fastapi`` were missing);
* introspection (``__all__``/``dir``) still lists every public symbol.
"""

import builtins
import importlib
import sys

import pytest


def _fresh_import(monkeypatch, blocked=()):
    """Re-import ``payments_py.langsmith`` (and its submodules) from scratch.

    Any module name listed in ``blocked`` raises ``ModuleNotFoundError`` on
    import, simulating an environment where that dependency is not installed.
    Returns the freshly imported ``payments_py.langsmith`` module.
    """
    for name in list(sys.modules):
        if name == "payments_py.langsmith" or name.startswith("payments_py.langsmith."):
            monkeypatch.delitem(sys.modules, name, raising=False)

    if blocked:
        real_import = builtins.__import__

        def _guarded_import(name, *args, **kwargs):
            top = name.split(".")[0]
            if name in blocked or top in blocked:
                raise ModuleNotFoundError(f"No module named {top!r}")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _guarded_import)
        # Hide any already-imported copies so the guard is actually exercised.
        for name in list(sys.modules):
            if name in blocked or name.split(".")[0] in blocked:
                monkeypatch.delitem(sys.modules, name, raising=False)

    return importlib.import_module("payments_py.langsmith")


def test_importing_package_does_not_import_middleware(monkeypatch):
    """Importing the package must not pull in the FastAPI middleware module."""
    _fresh_import(monkeypatch)
    assert "payments_py.langsmith.middleware" not in sys.modules


def test_requires_payment_imports_without_middleware(monkeypatch):
    """``from payments_py.x402.langchain import requires_payment`` is light."""
    for name in list(sys.modules):
        if name.startswith("payments_py.langsmith") or name.startswith(
            "payments_py.x402.langchain"
        ):
            monkeypatch.delitem(sys.modules, name, raising=False)

    from payments_py.x402.langchain import requires_payment  # noqa: F401

    assert "payments_py.langsmith.middleware" not in sys.modules


def test_package_imports_without_fastapi(monkeypatch):
    """The package must import even when ``fastapi`` is not installed."""
    module = _fresh_import(monkeypatch, blocked={"fastapi"})

    # Spans helpers are eagerly available and FastAPI-free.
    assert callable(module.settlement_span)
    assert callable(module.verify_span)
    assert "payments_py.langsmith.middleware" not in sys.modules


def test_requires_payment_imports_without_fastapi(monkeypatch):
    """The langchain decorator path imports without ``fastapi`` present."""
    _fresh_import(monkeypatch, blocked={"fastapi"})
    for name in list(sys.modules):
        if name.startswith("payments_py.x402.langchain"):
            monkeypatch.delitem(sys.modules, name, raising=False)

    langchain = importlib.import_module("payments_py.x402.langchain")

    assert hasattr(langchain, "requires_payment")
    assert "payments_py.langsmith.middleware" not in sys.modules


def test_referencing_middleware_symbol_without_fastapi_raises(monkeypatch):
    """Touching a middleware re-export with no ``fastapi`` raises ImportError."""
    module = _fresh_import(monkeypatch, blocked={"fastapi"})

    with pytest.raises(ImportError):
        _ = module.PaymentMiddleware


@pytest.mark.parametrize(
    "symbol",
    ["PaymentMiddleware", "RouteConfig", "X402_HEADERS", "build_payment_app"],
)
def test_middleware_symbols_resolve_lazily(monkeypatch, symbol):
    """Each middleware re-export resolves via the lazy import when available."""
    module = _fresh_import(monkeypatch)
    assert "payments_py.langsmith.middleware" not in sys.modules

    resolved = getattr(module, symbol)

    from payments_py.langsmith import middleware

    assert resolved is getattr(middleware, symbol)
    assert "payments_py.langsmith.middleware" in sys.modules


def test_unknown_attribute_raises_attribute_error(monkeypatch):
    """``__getattr__`` only handles known exports; others raise AttributeError."""
    module = _fresh_import(monkeypatch)

    with pytest.raises(AttributeError):
        _ = module.DefinitelyNotAThing


def test_all_lists_every_public_symbol(monkeypatch):
    """``__all__`` and ``dir`` still advertise the full public surface."""
    module = _fresh_import(monkeypatch)

    expected = {
        "PaymentMiddleware",
        "RouteConfig",
        "X402_HEADERS",
        "build_payment_app",
        "abbreviate_token",
        "active_run_tree",
        "add_metadata",
        "attach_metadata_safely",
        "build_settle_metadata",
        "build_verify_metadata",
        "redact_metadata_keys",
        "settlement_span",
        "verify_span",
    }
    assert set(module.__all__) == expected
    assert expected.issubset(set(dir(module)))
