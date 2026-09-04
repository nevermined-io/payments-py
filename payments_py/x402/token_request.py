"""
The access-token request body, shared by the x402 and MPP mints.

Both routes take identical inputs — only the EIP-712 domain the backend signs
under differs — so the body is built in one place to keep them from drifting.
"""

import warnings
from typing import Any, Dict, Optional, Union

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.schemes import get_default_network
from payments_py.x402.types import (
    DelegationConfig,
    MppTokenOptions,
    X402Resource,
)


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


def _resolve_resource(
    resource: Optional[Union[str, X402Resource]],
) -> Optional[Dict[str, Any]]:
    """Normalize ``token_options.resource`` into the ``{"url": …}`` object the
    mint endpoints accept.

    A bare URL string is the common case and is accepted directly; an
    :class:`X402Resource` carries the optional ``description`` / ``mimeType``
    alongside it.

    Raises:
        PaymentsError: (``code='validation'``) if the URL is empty or
            whitespace-only. On a v3 token the URL is *signed*: a blank one is
            signed as the empty string, which is indistinguishable from "field
            absent" and then makes the seller's own ``resource.url`` disagree
            with the signature at settle — rejected as forgery
            (``BCK.X402.0005``) long after the mistake was made. Same fail-fast
            rationale as the blank ``delegation_id`` guard below.
    """
    if resource is None:
        return None
    if isinstance(resource, str):
        payload: Dict[str, Any] = {"url": resource}
    else:
        payload = resource.model_dump(by_alias=True, exclude_none=True)

    url = payload.get("url")
    if not isinstance(url, str) or url.strip() == "":
        raise PaymentsError.validation(
            "resource.url must not be empty — pass the URL of the protected "
            "resource the token is minted for, or omit the field."
        )
    return payload


def build_x402_token_request_body(
    plan_id: str,
    agent_id: Optional[str] = None,
    token_options: Optional[MppTokenOptions] = None,
    environment_name: Optional[str] = None,
    protocol: str = "x402",
) -> Dict[str, Any]:
    """Build the body both ``POST /api/v1/x402/permissions`` and
    ``POST /api/v1/mpp/permissions`` accept.

    ``resource``, ``accepted.extra.httpVerb`` and ``tokenVersion`` are what a
    **v3** token (nvm-monorepo#2646) is signed over on top of v2's
    ``[from, sessionKeysProvider, sessionKeys, planId]``. They are sent
    whenever the caller supplies them, on every version: a v2 mint ignores
    them, and sending ``resource.url`` on v2 also stops the backend logging
    ``resource.url not provided in token … skipping endpoint validation``.

    ``tokenVersion`` is a *request*, never a guarantee — the backend's
    ``ValidationPipe`` silently strips unknown fields, so a deployment
    predating #2646 returns a v2 token without complaining. Detect what you
    actually got with
    :func:`payments_py.x402.token.detect_access_token_version`.

    Args:
        protocol: Which mint this body is for, ``"x402"`` (default) or
            ``"mpp"``. MPP has no token version at all — it is not "x402 v2
            by another name": the two protocols stopped sharing a version
            ladder (nvm-monorepo#3266) and ``MppService.createPermission``
            refuses ANY ``tokenVersion`` with ``BCK.MPP.0007``, ``2``
            included. Sending one would 400 the mint, so it is refused here
            instead, where the caller can be told why.

    Raises:
        PaymentsError: (``code='validation'``) if
            ``token_options.delegation_config.delegation_id`` is an empty or
            whitespace-only string, if ``token_options.resource`` carries a
            blank URL, or if a ``token_version`` is set on an MPP mint.
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
    if token_options and token_options.http_verb is not None:
        extra["httpVerb"] = token_options.http_verb

    body: Dict[str, Any] = {
        "accepted": {
            "scheme": scheme,
            "network": network,
            "planId": plan_id,
            "extra": extra,
        },
    }

    resource = _resolve_resource(token_options.resource if token_options else None)
    if resource is not None:
        body["resource"] = resource

    # `token_version` lives on X402TokenOptions only; a plain MppTokenOptions
    # has no such attribute, hence getattr rather than a direct read.
    token_version = getattr(token_options, "token_version", None)
    if token_version is not None:
        # MPP's single-use unit is the CHALLENGE, not the token: one MPP access
        # token is presented across many challenges by design, so the x402 v3
        # per-token nonce would kill every buyer's second challenge. The backend
        # refuses the field outright; refuse it here too rather than let the
        # caller discover it as a 400 whose cause is a field they set two layers
        # up.
        if protocol == "mpp":
            raise PaymentsError.validation(
                "token_version is not supported on MPP access tokens: MPP and "
                "x402 no longer share a token version ladder, and the backend "
                "refuses any tokenVersion on an MPP mint (BCK.MPP.0007). Omit "
                "the field — an MPP token is reusable across challenges, and "
                "the challenge is what is single-use."
            )
        body["tokenVersion"] = token_version

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
