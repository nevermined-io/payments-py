"""
Unit tests for create_require_auth_middleware.

Ported from the TypeScript SDK
``tests/unit/mcp/oauth_router_require_auth_middleware.test.ts``, adapted to the
FastAPI dependency (which raises ``HTTPException`` instead of calling ``res``).

RFC 9728 §5.1: a 401 from a protected resource advertises where its PRM lives so
a client can discover the authorization server. RFC 6750 §3/§3.1: the ``error``
auth-param is added only when a credential WAS presented but is malformed.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.datastructures import Headers

from payments_py.mcp.http.oauth_router import (
    create_cors_middleware,
    create_require_auth_middleware,
)


def make_request(headers=None, host="mcp.example.com", protocol="https"):
    """A minimal stand-in for the FastAPI/Starlette Request the dependency reads.

    ``Headers`` is case-insensitive like the real thing; the dependency only ever
    touches ``.headers`` and ``.url.scheme``.
    """
    raw = dict(headers or {})
    # Express's ``req.get('host')`` is the Host header; model it the same way.
    raw.setdefault("host", host)
    return SimpleNamespace(
        headers=Headers(raw),
        url=SimpleNamespace(scheme=protocol),
    )


async def call(middleware, request):
    """Invoke the dependency, returning the raised HTTPException or None."""
    try:
        await middleware(request)
        return None
    except HTTPException as exc:
        return exc


# =============================================================================
# Presence / shape checks (parity with the base middleware tests)
# =============================================================================


@pytest.mark.asyncio
async def test_401_when_authorization_header_missing():
    exc = await call(create_require_auth_middleware(), make_request({}))
    assert exc is not None and exc.status_code == 401
    assert exc.detail == {
        "error": "unauthorized",
        "error_description": "Authorization header required",
    }


@pytest.mark.asyncio
async def test_401_when_not_bearer():
    exc = await call(
        create_require_auth_middleware(),
        make_request({"authorization": "Basic dXNlcjpwYXNz"}),
    )
    assert exc is not None and exc.status_code == 401
    assert exc.detail["error_description"] == "Bearer token required"


@pytest.mark.asyncio
async def test_401_when_bearer_empty():
    exc = await call(
        create_require_auth_middleware(), make_request({"authorization": "Bearer "})
    )
    assert exc is not None and exc.status_code == 401
    assert exc.detail["error_description"] == "Bearer token cannot be empty"


@pytest.mark.asyncio
async def test_401_when_bearer_only_whitespace():
    exc = await call(
        create_require_auth_middleware(), make_request({"authorization": "Bearer    "})
    )
    assert exc is not None and exc.status_code == 401
    assert exc.detail["error_description"] == "Bearer token cannot be empty"


@pytest.mark.asyncio
async def test_passes_when_valid_bearer_present():
    exc = await call(
        create_require_auth_middleware(),
        make_request({"authorization": "Bearer valid-token-123"}),
    )
    assert exc is None


@pytest.mark.asyncio
async def test_accepts_authorization_capital_a():
    # Starlette Headers are case-insensitive, like Express's normalized headers.
    exc = await call(
        create_require_auth_middleware(),
        make_request({"Authorization": "Bearer token-ABC"}),
    )
    assert exc is None


@pytest.mark.asyncio
async def test_lowercase_bearer_rejected():
    exc = await call(
        create_require_auth_middleware(),
        make_request({"authorization": "bearer token-xyz"}),
    )
    assert exc is not None and exc.status_code == 401


@pytest.mark.asyncio
async def test_trims_whitespace_after_bearer_prefix():
    exc = await call(
        create_require_auth_middleware(),
        make_request({"authorization": "Bearer   token-with-spaces"}),
    )
    assert exc is None


# =============================================================================
# WWW-Authenticate challenge (RFC 9728 §5.1)
# =============================================================================


@pytest.mark.asyncio
async def test_challenge_points_at_prm_from_requested_host():
    exc = await call(
        create_require_auth_middleware(),
        make_request({}, host="mcp.example.com", protocol="https"),
    )
    assert exc.status_code == 401
    assert exc.headers["WWW-Authenticate"] == (
        'Bearer resource_metadata="https://mcp.example.com'
        '/.well-known/oauth-protected-resource"'
    )


@pytest.mark.asyncio
async def test_prefers_x_forwarded_proto_host():
    exc = await call(
        create_require_auth_middleware(),
        make_request(
            {"x-forwarded-proto": "https", "x-forwarded-host": "mcp.public.example"},
            host="internal:8080",
            protocol="http",
        ),
    )
    assert exc.headers["WWW-Authenticate"] == (
        'Bearer resource_metadata="https://mcp.public.example'
        '/.well-known/oauth-protected-resource"'
    )


@pytest.mark.asyncio
async def test_pinned_base_url_wins_and_ignores_forged_host():
    exc = await call(
        create_require_auth_middleware(base_url="https://mcp.pinned.example/"),
        make_request({}, host="evil.example", protocol="http"),
    )
    assert exc.headers["WWW-Authenticate"] == (
        'Bearer resource_metadata="https://mcp.pinned.example'
        '/.well-known/oauth-protected-resource"'
    )


@pytest.mark.asyncio
async def test_advertises_scoped_prm_path():
    exc = await call(
        create_require_auth_middleware(
            resource_metadata_path="/.well-known/oauth-protected-resource/mcp"
        ),
        make_request({}, host="mcp.example.com", protocol="https"),
    )
    assert exc.headers["WWW-Authenticate"] == (
        'Bearer resource_metadata="https://mcp.example.com'
        '/.well-known/oauth-protected-resource/mcp"'
    )


@pytest.mark.asyncio
async def test_security_host_with_quote_breaking_chars_dropped():
    # ``Host: evil"; foo="bar`` would inject a second auth-param pointing
    # resource_metadata at the attacker origin. It must be dropped, not emitted.
    exc = await call(
        create_require_auth_middleware(),
        make_request({}, host='evil.example"; foo="bar', protocol="https"),
    )
    assert exc.status_code == 401
    assert "WWW-Authenticate" not in (exc.headers or {})


@pytest.mark.asyncio
async def test_no_derivable_host_no_pinned_base_omits_challenge():
    exc = await call(create_require_auth_middleware(), make_request({}, host=""))
    assert exc.status_code == 401
    assert "WWW-Authenticate" not in (exc.headers or {})


@pytest.mark.asyncio
async def test_missing_credential_has_no_error_param():
    exc = await call(create_require_auth_middleware(), make_request({}))
    challenge = exc.headers["WWW-Authenticate"]
    assert "resource_metadata=" in challenge
    assert "error=" not in challenge


@pytest.mark.asyncio
async def test_malformed_credential_has_invalid_request_error():
    for authorization in ("Basic x", "Bearer "):
        exc = await call(
            create_require_auth_middleware(),
            make_request({"authorization": authorization}),
        )
        assert 'error="invalid_request"' in exc.headers["WWW-Authenticate"]
        assert "resource_metadata=" in exc.headers["WWW-Authenticate"]


@pytest.mark.asyncio
async def test_valid_token_emits_no_challenge():
    exc = await call(
        create_require_auth_middleware(),
        make_request({"authorization": "Bearer good-token"}),
    )
    assert exc is None


def test_cors_exposes_www_authenticate_header():
    # The 401 challenge is useless to a cross-origin browser client unless
    # WWW-Authenticate is CORS-exposed (it is not a safelisted response header).
    cors = create_cors_middleware()
    assert "WWW-Authenticate" in cors["expose_headers"]


@pytest.mark.asyncio
async def test_empty_x_forwarded_host_does_not_fall_back_to_host():
    # A present-but-empty X-Forwarded-Host behind a proxy must NOT advertise the
    # internal Host header — it yields no challenge (nullish, not falsy).
    exc = await call(
        create_require_auth_middleware(),
        make_request({"x-forwarded-host": ""}, host="internal:8080"),
    )
    assert exc.status_code == 401
    assert "WWW-Authenticate" not in (exc.headers or {})
