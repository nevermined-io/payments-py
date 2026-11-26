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
- **Fail loudly, not silently.** A key the matcher would get wrong raises
  ``ValueError`` naming the key when the middleware is built: see
  ``_compile_key`` for every check.
"""

import re
from typing import Dict, List, Optional, Pattern, Tuple

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

# Keys have no wildcard syntax: `*` and `?` would only match those literal
# characters, so a seller who writes them expects a key to gate paths it does
# not. A brace must belong to a `{param}`. (A route declared with a literal `*`
# cannot be gated by a key.)
_NOT_LITERAL = re.compile(r"[*?{}]")

CompiledRoute = Tuple[str, Pattern[str], RouteConfig]


def _invalid(key: str, reason: str) -> ValueError:
    return ValueError(
        f"Route key {key!r} is rejected: {reason}. Keys are "
        f'"METHOD /path", with path parameters written as in FastAPI '
        f'("/users/{{user_id}}", "/files/{{file_path:path}}") or as '
        f'"/users/:user_id"; parameter names are letters, digits and "_".'
    )


def _compile_key(key: str) -> Tuple[str, Pattern[str], str]:
    """Return the key's method, path regex, and a signature shared by keys that
    differ only in parameter names and method case.

    Rejected: no method or no path, a method outside ``HTTP_METHODS``, a path
    not starting with ``/``, a ``:`` segment that is not ``:name``, ``*``,
    ``?``, a brace outside a ``{name}`` or ``{name:converter}``, an unknown
    converter, and a repeated parameter name.
    """
    parts = key.split(maxsplit=1)
    if len(parts) != 2:
        raise _invalid(key, 'it is not "METHOD /path"')
    method, path = parts[0].upper(), parts[1].strip()
    if method not in HTTP_METHODS:
        raise _invalid(key, f"{parts[0]!r} is not a standard HTTP method")
    if not path.startswith("/"):
        raise _invalid(key, "the path does not start with '/'")

    segments = []
    for segment in path.split("/"):
        if segment.startswith(":"):
            param = _COLON_PARAM.fullmatch(segment)
            if not param:
                raise _invalid(key, f"{segment!r} is not a ':name' segment")
            segment = "{%s}" % param.group(1)
        segments.append(segment)
    path = "/".join(segments)

    if _NOT_LITERAL.search(PARAM_REGEX.sub("", path)):
        raise _invalid(
            key, "'*' and '?' are not wildcards, and braces must hold a parameter"
        )
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


def compile_routes(routes: Dict[str, RouteConfig]) -> Tuple[CompiledRoute, ...]:
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
    return tuple(sorted(compiled, key=lambda route: bool(route[1].groupindex)))


def request_paths(request: Request) -> Tuple[str, ...]:
    """The paths a key may describe a request by: as the router sees it
    (``root_path`` stripped), then with ``root_path`` in front.

    Both come from the scope. ``request.url.path`` is rebuilt from a URL
    string, so a ``%3F`` or ``%23`` the server decoded into the path cuts it
    short, and the buyer, who writes the URL, could pick a cheaper key."""
    route_path = get_route_path(request.scope)
    full_path = request.scope["path"]
    return (route_path,) if route_path == full_path else (route_path, full_path)


def match_route(
    method: str, paths: Tuple[str, ...], routes: Tuple[CompiledRoute, ...]
) -> Optional[RouteConfig]:
    """Return the config of the first route matching ``method`` and any of
    ``paths``, or ``None`` when the request is not gated.

    Within a method, routes are the outer loop, so precedence comes from
    ``compile_routes``' order alone, whichever form of the path matched.
    ``HEAD`` falls back to ``GET`` keys when no ``HEAD`` key matches, because
    Starlette's ``Route`` serves HEAD with the GET handler."""
    method = method.upper()
    for candidate in (method, "GET") if method == "HEAD" else (method,):
        for route_method, regex, config in routes:
            if route_method == candidate and any(regex.match(p) for p in paths):
                return config
    return None
