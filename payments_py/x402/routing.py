"""
Route-key matching for the payment middlewares (FastAPI and LangSmith).

A middleware gates a request when its ``"METHOD /path"`` key matches, and lets
it through unpaid when no key does. So a key that the router would send a
request to, but the matcher does not recognise, protects nothing (#341). Two
rules close that gap:

- **Match the way the router does.** Paths are compiled with Starlette's own
  ``compile_path``, so ``{name}``, ``{name:int}`` and ``{name:path}`` mean what
  they mean in ``@app.get(...)``. ``:name`` stays accepted as an alias for
  ``{name}``. A request is tried both as the router sees it (``root_path``
  stripped) and as the client sent it, so a key written either way matches
  behind ``uvicorn --root-path``.
- **Fail at startup, not silently.** A key the matcher cannot match — no
  method, a non-HTTP method, a wildcard, a partial ``:param``, an unknown
  converter, or two keys for the same requests — raises ``ValueError`` naming
  the key.
"""

import re
from typing import Dict, Iterable, List, Optional, Pattern, Tuple

# Private, but it is what Starlette's router matches against; reimplementing
# it would reopen the gap this module closes. A move fails loudly at import.
from starlette._utils import get_route_path
from starlette.convertors import CONVERTOR_TYPES
from starlette.requests import Request
from starlette.routing import PARAM_REGEX, compile_path

from payments_py.x402.types import RouteConfig

HTTP_METHODS = frozenset(
    {"GET", "HEAD", "POST", "PUT", "DELETE", "CONNECT", "OPTIONS", "TRACE", "PATCH"}
)

_COLON_PARAM = re.compile(r":([A-Za-z_][A-Za-z0-9_]*)")

# Characters that never match as written: a wildcard, a query string, or a
# brace that is not part of a `{param}`.
_UNMATCHABLE = re.compile(r"[*?{}]")

CompiledRoute = Tuple[str, Pattern[str], RouteConfig]


def _invalid(key: str, reason: str) -> ValueError:
    return ValueError(
        f"Route key {key!r} can never match a request: {reason}. Keys are "
        f'"METHOD /path", with path parameters written as in FastAPI '
        f'("/users/{{user_id}}", "/files/{{file_path:path}}") or as ":user_id".'
    )


def _compile_key(key: str) -> Tuple[str, Pattern[str], str]:
    """Return the key's method, path regex, and a signature that is equal for
    two keys exactly when they match the same requests."""
    parts = key.split(maxsplit=1)
    if len(parts) != 2:
        raise _invalid(key, 'it is not "METHOD /path"')
    method, path = parts[0].upper(), parts[1].strip()
    if method not in HTTP_METHODS:
        raise _invalid(key, f"{parts[0]!r} is not an HTTP method")
    if not path.startswith("/"):
        raise _invalid(key, "the path does not start with '/'")

    segments = []
    for segment in path.split("/"):
        if segment.startswith(":"):
            param = _COLON_PARAM.fullmatch(segment)
            if not param:
                raise _invalid(key, f"{segment!r} is not a whole ':param' segment")
            segment = "{%s}" % param.group(1)
        segments.append(segment)
    path = "/".join(segments)

    if _UNMATCHABLE.search(PARAM_REGEX.sub("", path)):
        raise _invalid(key, "it contains '*', '?' or a stray brace")
    for param in PARAM_REGEX.finditer(path):
        converter = (param.group(2) or ":str")[1:]
        if converter not in CONVERTOR_TYPES:
            raise _invalid(key, f"{converter!r} is not a path converter")
    try:
        regex, _, _ = compile_path(path)
    except ValueError as error:  # a repeated parameter name
        raise _invalid(key, str(error)) from error

    signature = PARAM_REGEX.sub(lambda m: "{%s}" % (m.group(2) or ":str"), path)
    return method, regex, f"{method} {signature}"


def compile_routes(routes: Dict[str, RouteConfig]) -> List[CompiledRoute]:
    """Compile route keys, raising ``ValueError`` for any that cannot match.

    Literal keys come first, so ``GET /users/me`` wins over
    ``GET /users/{user_id}`` whatever order they are declared in. Keys with
    parameters keep their declaration order.
    """
    compiled: List[CompiledRoute] = []
    seen: Dict[str, str] = {}
    for key, config in routes.items():
        method, regex, signature = _compile_key(key)
        if signature in seen:
            raise ValueError(
                f"Route keys {seen[signature]!r} and {key!r} match the same "
                "requests; keep one."
            )
        seen[signature] = key
        compiled.append((method, regex, config))
    # Stable sort: literal keys (no named groups) first, in declaration order.
    return sorted(compiled, key=lambda route: bool(route[1].groupindex))


def request_paths(request: Request) -> Tuple[str, ...]:
    """The paths a key may describe a request by: as the router sees it
    (``root_path`` stripped), then as the client sent it."""
    route_path = get_route_path(request.scope)
    full_path = request.url.path
    return (route_path,) if route_path == full_path else (route_path, full_path)


def match_route(
    method: str, paths: Iterable[str], routes: List[CompiledRoute]
) -> Optional[RouteConfig]:
    """Return the config of the first route matching ``method`` and any of
    ``paths``, or ``None`` when the request is not gated.

    ``HEAD`` falls back to ``GET`` keys, because Starlette's ``Route`` serves
    HEAD with the GET handler."""
    method = method.upper()
    methods = (method, "GET") if method == "HEAD" else (method,)
    for path in paths:
        for candidate in methods:
            for route_method, regex, config in routes:
                if route_method == candidate and regex.match(path):
                    return config
    return None
