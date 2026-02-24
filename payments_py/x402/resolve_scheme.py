"""
Resolve the x402 scheme for a plan by fetching plan metadata (cached).

Used in callsites that don't have a token to extract scheme from
(402 responses and token generation).
"""

import logging
import time
from typing import Any, Optional

from .schemes import X402SchemeType

logger = logging.getLogger(__name__)

# 5-minute cache TTL
_CACHE_TTL_SECS = 300

_plan_metadata_cache: dict[str, dict[str, Any]] = {}


def _fetch_plan_metadata(payments: Any, plan_id: str) -> X402SchemeType:
    """Fetch plan metadata and determine scheme. Caches results for 5 minutes."""
    cached = _plan_metadata_cache.get(plan_id)
    if cached and (time.monotonic() - cached["cached_at"]) < _CACHE_TTL_SECS:
        return cached["scheme"]

    try:
        plan = payments.plans.get_plan(plan_id)
        registry = plan.get("registry", {}) if isinstance(plan, dict) else {}
        price = registry.get("price", {}) if isinstance(registry, dict) else {}
        is_crypto = price.get("isCrypto")
        scheme: X402SchemeType = (
            "nvm:card-delegation" if is_crypto is False else "nvm:erc4337"
        )
        _plan_metadata_cache[plan_id] = {
            "scheme": scheme,
            "cached_at": time.monotonic(),
        }
        return scheme
    except Exception:
        logger.debug(
            "Failed to fetch plan metadata for %s, defaulting to nvm:erc4337", plan_id
        )
        return "nvm:erc4337"


def resolve_scheme(
    payments: Any,
    plan_id: str,
    explicit_scheme: Optional[str] = None,
) -> X402SchemeType:
    """Resolve the x402 scheme for a plan.

    If *explicit_scheme* is provided it is returned immediately.
    Otherwise the plan metadata is fetched (with a 5-minute TTL cache)
    and the scheme is determined from ``plan.registry.price.isCrypto``.

    Args:
        payments: The Payments instance (needs ``payments.plans.get_plan``).
        plan_id: The plan identifier.
        explicit_scheme: Optional explicit override; returned immediately if provided.

    Returns:
        The resolved scheme type (``"nvm:erc4337"`` or ``"nvm:card-delegation"``).
    """
    if explicit_scheme:
        return explicit_scheme  # type: ignore[return-value]
    return _fetch_plan_metadata(payments, plan_id)


def clear_scheme_cache() -> None:
    """Clear the plan metadata cache (useful for testing)."""
    _plan_metadata_cache.clear()
