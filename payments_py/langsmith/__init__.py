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
"""

from payments_py.langsmith.spans import (
    abbreviate_token,
    active_run_tree,
    add_metadata,
    build_settle_metadata,
    build_verify_metadata,
    settlement_span,
    verify_span,
)

__all__ = [
    "abbreviate_token",
    "active_run_tree",
    "add_metadata",
    "build_settle_metadata",
    "build_verify_metadata",
    "settlement_span",
    "verify_span",
]
