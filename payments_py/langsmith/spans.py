"""LangSmith span helpers for Nevermined payment events.

All helpers in this module silently no-op when:
  - the ``langsmith`` package is not installed; or
  - no LangSmith run tree is active in the current context
    (e.g. ``LANGSMITH_TRACING`` is unset, or the call is not inside a traced
    runnable).

Failures inside this module never propagate out -- observability is
best-effort and must not interfere with the payment flow.
"""

from __future__ import annotations

import logging
from contextlib import ExitStack, contextmanager
from typing import Any, Callable, Iterator, Optional

from payments_py.x402.types import SettleResponse, VerifyResponse

logger = logging.getLogger(__name__)

try:
    import langsmith as _ls
    from langsmith.run_helpers import get_current_run_tree as _get_current_run_tree

    _LANGSMITH_AVAILABLE = True
except ImportError:
    _ls = None  # type: ignore[assignment]
    _get_current_run_tree = None  # type: ignore[assignment]
    _LANGSMITH_AVAILABLE = False


def active_run_tree() -> Optional[Any]:
    """Return the current LangSmith ``RunTree``, or ``None`` if no run is active.

    Safe to call regardless of whether ``langsmith`` is installed.
    """
    if not _LANGSMITH_AVAILABLE:
        return None
    try:
        return _get_current_run_tree()
    except Exception:
        return None


def add_metadata(run_tree: Optional[Any], metadata: dict) -> None:
    """Attach ``metadata`` to ``run_tree``, swallowing any error.

    No-op if ``run_tree`` is ``None`` or ``metadata`` is empty.
    """
    if run_tree is None or not metadata:
        return
    try:
        run_tree.add_metadata(metadata)
    except Exception:
        logger.debug("LangSmith add_metadata failed (ignored)", exc_info=True)


def attach_metadata_safely(
    span: Optional[Any],
    parent_rt: Optional[Any],
    builder: Callable[..., dict],
    label: str,
    **builder_kwargs: Any,
) -> None:
    """Build metadata via ``builder`` and attach it to ``span`` + ``parent_rt``.

    Wraps the build+attach sequence in a single try/except so observability
    failures (a builder bug, an ``add_metadata`` exception) are logged at
    debug and swallowed — they must never block the payment flow or mask a
    downstream ``PaymentRequiredError``. Critically: a builder exception is
    NOT allowed to abort the surrounding lifecycle, so a failure in
    ``build_settle_metadata`` cannot prevent the ``payment-response``
    settlement header from being attached to the response.

    Pre-abbreviates any ``token`` kwarg before calling ``builder`` so the
    raw x402 access token never reaches the frame locals visible to
    exception enrichers (Sentry's ``logging`` integration, structlog's
    ``ExceptionRenderer``, etc.). ``exc_info`` is deliberately omitted
    from the log call for the same reason.
    """
    if "token" in builder_kwargs:
        builder_kwargs["token"] = abbreviate_token(builder_kwargs["token"])
    try:
        md = builder(**builder_kwargs)
        add_metadata(span, md)
        add_metadata(parent_rt, md)
    except Exception:
        logger.debug("LangSmith %s metadata attach failed (ignored)", label)


def redact_metadata_keys(run_tree: Optional[Any], *keys: str) -> None:
    """Remove ``keys`` from ``run_tree``'s metadata in place.

    LangSmith inherits a parent run's metadata to child runs created via
    ``ls.trace(...)``, so call this on the parent run BEFORE opening any
    child spans whose metadata should not carry the keys. The most common
    use is stripping ``payment_token`` from the parent tool span's
    metadata, since LangChain auto-captures every entry in
    ``config["configurable"]`` and the access token grants access to the
    protected tool until it expires.

    No-op when ``run_tree`` is ``None`` or no keys are provided. All
    errors are swallowed -- observability hygiene must never disrupt the
    payment flow.
    """
    if run_tree is None or not keys:
        return
    try:
        extra = getattr(run_tree, "extra", None)
        if isinstance(extra, dict):
            metadata = extra.get("metadata")
            if isinstance(metadata, dict):
                for key in keys:
                    metadata.pop(key, None)
    except Exception:
        logger.debug("LangSmith redact_metadata_keys failed (ignored)", exc_info=True)


def abbreviate_token(token: Optional[str]) -> Optional[str]:
    """Return a short ``<first 16>…<last 4>`` form of a payment token.

    Used to attach an identifiable but non-functional reference to the
    x402 access token in span metadata. Long enough for humans to spot
    which token was used; short enough not to leak the credential.

    Returns ``None`` if ``token`` is ``None`` or empty. Returns the token
    unchanged when it is already 20 characters or fewer (no benefit to
    abbreviating) -- but emits a ``logging.warning`` in that case, because
    real x402 access tokens are JWTs (always >20 chars). A sub-21-char
    token would therefore ship in FULL under ``nvm.payment_token``, which
    usually means the wrong value was passed (e.g. a plan id or an opaque
    handle rather than the JWT). The return contract is preserved -- the
    value still comes back unchanged so the helper stays idempotent; only
    a warning is added so callers (especially the non-LangChain paths that
    use this as a public helper) notice the likely mistake.
    """
    if not token:
        return None
    if len(token) <= 20:
        logger.warning(
            "abbreviate_token: token shorter than expected (<21 chars) -- "
            "was the right x402 access token passed? It will be surfaced in "
            "full under nvm.payment_token."
        )
        return token
    return f"{token[:16]}…{token[-4:]}"


def build_verify_metadata(
    plan_ids: list[str],
    scheme: Optional[str] = None,
    network: Optional[str] = None,
    agent_id: Optional[str] = None,
    verification: Optional[VerifyResponse] = None,
    duration_ms: Optional[float] = None,
    token: Optional[str] = None,
) -> dict:
    """Build the ``nvm.*`` metadata dict for a verify span. Drops ``None`` values.

    ``token`` is abbreviated via :func:`abbreviate_token` before being
    surfaced as ``nvm.payment_token`` so the full credential never ends
    up in metadata that we control.
    """
    md: dict = {"nvm.plan_ids": list(plan_ids)}
    if scheme:
        md["nvm.scheme"] = scheme
    if network:
        md["nvm.network"] = network
    if agent_id:
        md["nvm.agent_id"] = agent_id
    if duration_ms is not None:
        md["nvm.verify.duration_ms"] = round(duration_ms, 2)
    abbreviated = abbreviate_token(token)
    if abbreviated:
        md["nvm.payment_token"] = abbreviated
    if verification is not None:
        if verification.payer:
            md["nvm.payer"] = verification.payer
        if verification.network and "nvm.network" not in md:
            md["nvm.network"] = verification.network
        if verification.agent_request_id:
            md["nvm.agent_request_id"] = verification.agent_request_id
    return md


def build_settle_metadata(
    settlement: SettleResponse,
    plan_ids: list[str],
    agent_id: Optional[str] = None,
    duration_ms: Optional[float] = None,
    token: Optional[str] = None,
) -> dict:
    """Build the ``nvm.*`` metadata dict for a settlement span. Drops ``None`` values.

    ``token`` is abbreviated via :func:`abbreviate_token` before being
    surfaced as ``nvm.payment_token``.
    """
    md: dict = {"nvm.plan_ids": list(plan_ids)}
    if agent_id:
        md["nvm.agent_id"] = agent_id
    if duration_ms is not None:
        md["nvm.settle.duration_ms"] = round(duration_ms, 2)
    abbreviated = abbreviate_token(token)
    if abbreviated:
        md["nvm.payment_token"] = abbreviated
    if settlement.credits_redeemed is not None:
        md["nvm.credits_redeemed"] = settlement.credits_redeemed
    if settlement.remaining_balance is not None:
        md["nvm.balance.after"] = settlement.remaining_balance
    if settlement.transaction:
        md["nvm.tx_hash"] = settlement.transaction
    if settlement.network:
        md["nvm.network"] = settlement.network
    if settlement.payer:
        md["nvm.payer"] = settlement.payer
    return md


@contextmanager
def _open_nvm_span(name: str, inputs: dict) -> Iterator[Optional[Any]]:
    """Shared implementation behind :func:`verify_span` / :func:`settlement_span`.

    Yields the underlying LangSmith ``RunTree`` if a parent run is active and
    ``_ls.trace`` setup succeeds; yields ``None`` otherwise. The ``ExitStack``
    is load-bearing: it swallows setup errors via the try/except below while
    letting body exceptions propagate cleanly through the ``@contextmanager``
    protocol (a previous broad try/except here surfaced as
    ``"generator didn't stop after throw()"`` -- see the regression tests in
    ``tests/unit/langsmith/test_spans.py``).
    """
    if active_run_tree() is None:
        yield None
        return

    with ExitStack() as stack:
        try:
            span = stack.enter_context(
                _ls.trace(  # type: ignore[union-attr]
                    name=name,
                    run_type="tool",
                    inputs=inputs,
                )
            )
        except Exception:
            logger.debug("LangSmith %s setup failed (ignored)", name, exc_info=True)
            yield None
            return
        yield span


@contextmanager
def verify_span(
    plan_ids: list[str],
    scheme: Optional[str] = None,
    network: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> Iterator[Optional[Any]]:
    """Open an ``nvm:verify`` child span around a verify call.

    Yields the underlying ``RunTree`` if LangSmith is active and a parent
    run is in scope; yields ``None`` otherwise. Always safe to call.

    Exceptions raised by the caller's body propagate out unchanged -- the
    underlying ``langsmith.trace`` context manager sees them via its
    ``__exit__`` and records the span as failed before re-raising. Only
    errors raised inside the trace SETUP (constructing or entering the
    LangSmith context) are swallowed, since those are pure observability
    concerns and must never interfere with the payment flow.

    Example::

        with verify_span(plan_ids=["plan-1"]) as span:
            verification = payments.facilitator.verify_permissions(...)
            add_metadata(span, build_verify_metadata(
                plan_ids=["plan-1"], verification=verification,
            ))
    """
    inputs: dict = {"plan_ids": list(plan_ids)}
    if scheme:
        inputs["scheme"] = scheme
    if network:
        inputs["network"] = network
    if agent_id:
        inputs["agent_id"] = agent_id

    with _open_nvm_span("nvm:verify", inputs) as span:
        yield span


@contextmanager
def settlement_span(
    plan_ids: list[str],
    agent_id: Optional[str] = None,
) -> Iterator[Optional[Any]]:
    """Open an ``nvm:settlement`` child span around a settle call.

    Same semantics as :func:`verify_span`.
    """
    inputs: dict = {"plan_ids": list(plan_ids)}
    if agent_id:
        inputs["agent_id"] = agent_id

    with _open_nvm_span("nvm:settlement", inputs) as span:
        yield span
