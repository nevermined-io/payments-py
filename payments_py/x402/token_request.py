"""
The access-token request body, shared by the x402 and MPP mints.

Both routes take identical inputs — only the EIP-712 domain the backend signs
under differs — so the body is built in one place to keep them from drifting.
"""

import warnings
from typing import Any, Dict, Optional

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.schemes import get_default_network
from payments_py.x402.types import DelegationConfig, X402TokenOptions


def _is_inline_create(delegation_config: DelegationConfig) -> bool:
    """Whether a delegation config asks the backend to create a delegation on
    the fly (the deprecated path) rather than reusing an existing one.

    The supported flow is create-first: create the delegation via
    ``POST /delegation/create`` and pass only ``delegation_id`` here. A config
    that carries no ``delegation_id`` but does carry an inline-create signal (a
    payment-method reference or spending limits) triggers the backend's
    deprecated create-on-the-fly path, which logs its own deprecation warning
    server-side (#1674) and will be removed in a future release.
    """
    if delegation_config.delegation_id:
        return False
    return any(
        value is not None
        for value in (
            delegation_config.card_id,
            delegation_config.provider_payment_method_id,
            delegation_config.spending_limit_cents,
            delegation_config.duration_secs,
        )
    )


def build_x402_token_request_body(
    plan_id: str,
    agent_id: Optional[str] = None,
    token_options: Optional[X402TokenOptions] = None,
    environment_name: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the body both ``POST /api/v1/x402/permissions`` and
    ``POST /api/v1/mpp/permissions`` accept.

    Raises:
        PaymentsError: (``code='validation'``) if
            ``token_options.delegation_config.delegation_id`` is an empty or
            whitespace-only string.
    """
    scheme = (
        token_options.scheme
        if token_options and token_options.scheme
        else "nvm:erc4337"
    )
    network = (
        token_options.network
        if token_options and token_options.network
        else get_default_network(scheme, environment_name)
    )

    extra: Dict[str, Any] = {}
    if agent_id is not None:
        extra["agentId"] = agent_id

    body: Dict[str, Any] = {
        "accepted": {
            "scheme": scheme,
            "network": network,
            "planId": plan_id,
            "extra": extra,
        },
    }

    # Add delegation config for both erc4337 and card-delegation schemes
    if token_options and token_options.delegation_config:
        delegation_config = token_options.delegation_config
        # An empty- or whitespace-only delegation_id is neither a valid reuse
        # (it's not a UUID) nor "absent": model_dump(exclude_none=True) keeps it
        # (it is not None), so it would serialize a blank ``delegationId`` and
        # 4xx at the backend, while _is_inline_create would (mis)read it as
        # inline. Fail fast with a clear client-input error instead. Strip first
        # to match the TS SDK guard's ``.trim() === ''`` (payments#379) — exact
        # cross-SDK symmetry.
        if (
            delegation_config.delegation_id is not None
            and delegation_config.delegation_id.strip() == ""
        ):
            raise PaymentsError.validation(
                "delegation_id must not be an empty string — pass a valid "
                "delegation UUID or omit the field."
            )
        if _is_inline_create(delegation_config):
            # FutureWarning (not DeprecationWarning): DeprecationWarning is
            # filtered out by default outside __main__, so agents running under
            # FastAPI / gunicorn / Celery / Docker workers would never see the
            # nudge. FutureWarning is shown by default → true runtime parity
            # with the TS SDK's console.warn.
            #
            # Wording is deliberately neutral about WHICH mint was called: this
            # builder is shared by get_x402_access_token and the MPP mint
            # (payments.mpp.fetch / get_mpp_access_token), so naming one caller
            # would send an MPP buyer grepping for a symbol they never called.
            # stacklevel=3 so the warning still points at the SDK user's own
            # call site (user → mint method → here), not at this module.
            warnings.warn(
                "Passing spending limits / a payment method when requesting an "
                "access token (inline delegation create-on-the-fly) is "
                "deprecated and will be removed in a future release. Create the "
                "delegation first with payments.delegation.create_delegation(...) "
                "and pass only DelegationConfig(delegation_id=...) instead.",
                FutureWarning,
                stacklevel=3,
            )
        body["delegationConfig"] = delegation_config.model_dump(
            by_alias=True, exclude_none=True
        )

    return body


__all__ = ["build_x402_token_request_body"]
