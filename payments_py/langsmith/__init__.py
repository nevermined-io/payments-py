"""LangSmith observability bridge for Nevermined payments.

When the optional ``[langsmith]`` extra is installed and a LangSmith run is
active in the calling context (typically because ``LANGSMITH_TRACING=true``
is set and the agent is invoked through a traced runnable), the
``@requires_payment`` decorator automatically emits dedicated ``nvm:verify``
and ``nvm:settlement`` child spans nested under the active tool span. Both
spans carry diagnostic ``nvm.*`` metadata for audit and reconciliation, and
the same metadata is also attached to the parent tool span so cmd-F searches
in the LangSmith UI land on either span.

This module is import-safe even without ``langsmith`` installed; all helpers
become no-ops in that case. Failures in observability never propagate out
into the payment flow.

Manual use is supported for non-LangChain code paths (e.g. the FastAPI
middleware) that still want to surface Nevermined-flavored spans into
LangSmith traces::

    from payments_py.langsmith import settlement_span, build_settle_metadata

    with settlement_span(plan_ids=["plan-1"]) as span:
        settlement = payments.facilitator.settle_permissions(...)
        if span is not None:
            span.add_metadata(build_settle_metadata(settlement, ["plan-1"]))

Lazy middleware imports. The ``spans`` helpers are pure-Python and import
eagerly, but the ASGI middleware in ``payments_py.langsmith.middleware``
depends on ``fastapi``/``starlette``, which only ship with the ``[langsmith]``
extra. The ``@requires_payment`` decorator pulls in this package solely for
the span helpers, so eagerly importing the middleware here would force
``fastapi`` on every tool-time user. To avoid that, the middleware re-exports
(``PaymentMiddleware``, ``RouteConfig``, ``X402_HEADERS``, ``build_payment_app``)
are resolved lazily via a module-level ``__getattr__`` (PEP 562) and only
import ``fastapi`` when first referenced.

Caveat: ``from payments_py.langsmith import *`` still imports ``fastapi``,
because a star-import iterates ``__all__`` (which lists the four middleware
names) and so references each one. Plain ``import payments_py.langsmith`` and
the ``@requires_payment`` decorator path -- the case this lazy import exists to
serve -- are unaffected.
"""

from typing import TYPE_CHECKING, Any

from payments_py.langsmith.spans import (
    abbreviate_token,
    active_run_tree,
    add_metadata,
    attach_metadata_safely,
    build_settle_metadata,
    build_verify_metadata,
    redact_metadata_keys,
    settlement_span,
    verify_span,
)

if TYPE_CHECKING:
    # Static-analysis / IDE only: lets Pyright resolve the four lazily
    # re-exported middleware names (and silences reportUnsupportedDunderAll)
    # without importing fastapi. This block is never executed at runtime, so
    # the lazy, fastapi-free import path below is unaffected.
    from payments_py.langsmith.middleware import (
        PaymentMiddleware,
        RouteConfig,
        X402_HEADERS,
        build_payment_app,
    )

# Symbols re-exported from the FastAPI-dependent middleware module. Loaded
# lazily by __getattr__ below so that importing this package (e.g. via the
# @requires_payment decorator) does not require the [langsmith] extra.
_MIDDLEWARE_EXPORTS = frozenset(
    {
        "PaymentMiddleware",
        "RouteConfig",
        "X402_HEADERS",
        "build_payment_app",
    }
)


def __getattr__(name: str) -> Any:
    """Lazily resolve middleware re-exports (PEP 562).

    Importing ``payments_py.langsmith.middleware`` pulls in ``fastapi``, so we
    defer it until one of its symbols is actually referenced. A missing
    ``fastapi`` therefore surfaces as an ``ImportError`` at first reference of a
    middleware symbol, not at package import time.
    """
    if name in _MIDDLEWARE_EXPORTS:
        from payments_py.langsmith import middleware

        value = getattr(middleware, name)
        # Cache into the module namespace so subsequent lookups resolve
        # directly and skip __getattr__ entirely (canonical PEP 562 idiom).
        globals()[name] = value
        return value
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    # __all__ is defined below this function; it is read at call time (not at
    # definition time), so referencing it here is safe.
    return sorted(__all__)


__all__ = [
    "PaymentMiddleware",
    "RouteConfig",
    "X402_HEADERS",
    "abbreviate_token",
    "active_run_tree",
    "add_metadata",
    "attach_metadata_safely",
    "build_payment_app",
    "build_settle_metadata",
    "build_verify_metadata",
    "redact_metadata_keys",
    "settlement_span",
    "verify_span",
]
