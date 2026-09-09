"""
The access-token request body, shared by the x402 and MPP mints.

The two routes take the same inputs **except for the v3 binding** —
``tokenVersion``, ``resource`` and ``httpVerb`` are x402-only, and are refused
below for MPP (nvm-monorepo#3266). Beyond that only the EIP-712 domain the
backend signs under differs, so the body is built in one place to keep the two
from drifting.
"""

import warnings
from typing import Any, Dict, Literal, Optional, Union

from payments_py.common.payments_error import PaymentsError
from payments_py.x402.schemes import get_default_network
from payments_py.x402.token_version import X402_TOKEN_VERSION_V3
from payments_py.x402.types import (
    DelegationConfig,
    MppTokenOptions,
    X402Resource,
    X402TokenOptions,
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
            whitespace-only. A blank is signed as the empty string, and the
            backend normalizes a signed ``''`` straight back to "not bound"
            (``orUndefined`` in ``resolveErc4337Binding``) — so it does NOT
            fail loudly as forgery. It silently mints an **unbound** v3 token:
            single-use, but presentable to any seller, which is half the
            guarantee the caller asked for and no error anywhere says so. That
            silence is why this is worth a fail-fast guard, the same reason as
            the blank ``delegation_id`` one below.
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


def _resolve_http_verb(http_verb: Optional[str]) -> Optional[str]:
    """Normalize ``token_options.http_verb`` into the form the seller will
    re-assert at settle.

    Upper-cased because the verb is compared against a framework-supplied
    ``request.method``, which is upper case everywhere (WSGI/ASGI, Express,
    ``requests``). ``"post"`` would sail through the mint, get signed verbatim
    on v3, and only fail at settle as a signature mismatch.

    Raises:
        PaymentsError: (``code='validation'``) if the verb is empty or
            whitespace-only — same rationale as the blank-URL guard below: the
            backend normalizes a signed blank back to "not bound", so it does
            not fail, it silently drops that dimension of the binding.
    """
    if http_verb is None:
        return None
    normalized = http_verb.strip().upper()
    if normalized == "":
        raise PaymentsError.validation(
            "http_verb must not be empty — pass the HTTP verb of the protected "
            "resource (e.g. 'POST'), or omit the field."
        )
    return normalized


def build_x402_token_request_body(
    plan_id: str,
    agent_id: Optional[str] = None,
    token_options: Optional[MppTokenOptions] = None,
    environment_name: Optional[str] = None,
    protocol: Literal["x402", "mpp"] = "x402",
) -> Dict[str, Any]:
    """Build the body both ``POST /api/v1/x402/permissions`` and
    ``POST /api/v1/mpp/permissions`` accept.

    ``resource``, ``accepted.extra.httpVerb`` and ``tokenVersion`` are what a
    **v3** token (nvm-monorepo#2646) is signed over on top of v2's
    ``[from, sessionKeysProvider, sessionKeys, planId]``. They travel together
    and are emitted **only** for ``token_version=3``.

    They are NOT inert on a v2 mint, which is why supplying them without the
    version raises rather than being dropped or forwarded. On v2 the fields
    land on the unsigned envelope and bind nothing, but the presence of the
    token's ``resource.url`` is exactly what switches the backend's
    ``enforceEndpointAllowlist`` on
    (``apps/api/src/x402/handlers/erc4337-scheme.handler.ts``): the
    ``resource.url not provided in token … skipping endpoint validation`` log
    is the marker of a check being SKIPPED, not noise to tidy away. Sending
    ``resource`` on v2 therefore adds no binding and arms an allowlist the
    caller never configured — for an agent registered with ``endpoints`` it
    turns a working mint into ``BCK.PROTOCOL.0031``.

    ``tokenVersion`` is a *request*, never a guarantee — the backend's
    ``ValidationPipe`` silently strips unknown fields, so a deployment
    predating #2646 returns a v2 token without complaining. Detect what you
    actually got with
    :func:`payments_py.x402.token.detect_access_token_version`.

    Args:
        protocol: Which mint this body is for, ``"x402"`` (default) or
            ``"mpp"``. An MPP token carries **none** of the v3 binding:
            ``tokenVersion`` because the two protocols stopped sharing a
            version ladder (nvm-monorepo#3266) and
            ``MppService.createPermission`` refuses ANY value with
            ``BCK.MPP.0007``, ``2`` included; ``resource`` / ``http_verb``
            because MPP redemption runs through the same shared ``verify``,
            so they would arm the endpoint allowlist while binding nothing.
            :class:`~payments_py.x402.types.MppTokenOptions` cannot carry any
            of the three, but :class:`~payments_py.x402.types.X402TokenOptions`
            subclasses it and can, so the refusal is enforced here.

    Raises:
        PaymentsError: (``code='validation'``) if
            ``token_options.delegation_config.delegation_id`` is an empty or
            whitespace-only string, if ``token_options.resource`` carries a
            blank URL, if ``http_verb`` is blank, if any part of the v3 binding
            is supplied without ``token_version=3``, or if any part of it
            reaches an MPP mint.
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

    # The v3 binding lives on X402TokenOptions only, so the reads are narrowed
    # by isinstance rather than done with getattr. getattr fails OPEN: rename or
    # mistype one of these fields and it returns None forever, `has_binding`
    # goes False, the refusal below never fires, and a caller who asked for a
    # bound v3 token silently gets an unbound one. isinstance puts the same
    # reads in front of the type checker, so that rename is a build error.
    if isinstance(token_options, X402TokenOptions):
        token_version = token_options.token_version
        resource = _resolve_resource(token_options.resource)
        http_verb = _resolve_http_verb(token_options.http_verb)
    else:
        token_version = None
        resource = None
        http_verb = None
    has_binding = resource is not None or http_verb is not None

    if protocol == "mpp":
        # MPP's single-use unit is the CHALLENGE, not the token: one MPP access
        # token is presented across many challenges by design, so the x402 v3
        # per-token nonce would kill every buyer's second challenge. And the
        # resource binding would arm the endpoint allowlist on the shared verify
        # while binding nothing, since the MPP struct has no members for it.
        # Refused here rather than discovered as a 400 whose cause is a field the
        # caller set two layers up.
        if token_version is not None:
            raise PaymentsError.validation(
                "token_version is not supported on MPP access tokens: MPP and "
                "x402 no longer share a token version ladder, and the backend "
                "refuses any tokenVersion on an MPP mint (BCK.MPP.0007). Omit "
                "the field — an MPP token is reusable across challenges, and "
                "the challenge is what is single-use."
            )
        if has_binding:
            raise PaymentsError.validation(
                "resource / http_verb are the x402 v3 binding and are not "
                "supported on MPP access tokens: an MPP token's struct has no "
                "members for them, so they would bind nothing while arming the "
                "backend's endpoint allowlist. Omit them — an MPP credential is "
                "bound by its challenge, not by its token."
            )
    elif has_binding and token_version != X402_TOKEN_VERSION_V3:
        # Dropping them silently would mint an unbound token while the caller
        # believes it is bound; forwarding them would arm the allowlist on a v2
        # token that binds nothing. Neither is a good failure, so refuse.
        raise PaymentsError.validation(
            "resource / http_verb are the v3 binding and require "
            "token_version=3. On a v2 token they are not signed — they bind "
            "nothing and only arm the backend's endpoint allowlist, which for "
            "an agent registered with `endpoints` fails as BCK.PROTOCOL.0031. "
            "Pass token_version=3, or omit resource and http_verb."
        )

    extra: Dict[str, Any] = {}
    if agent_id is not None:
        extra["agentId"] = agent_id
    if http_verb is not None:
        extra["httpVerb"] = http_verb

    body: Dict[str, Any] = {
        "accepted": {
            "scheme": scheme,
            "network": network,
            "planId": plan_id,
            "extra": extra,
        },
    }

    if resource is not None:
        body["resource"] = resource

    if token_version is not None:
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
