"""Send one request to an ASGI app with its path exactly as uvicorn delivers it.

httpx (and so ``TestClient``) normalises the URL before sending: it removes
``.`` and ``..`` segments and cannot put a decoded ``?`` or ``#`` into the path.
uvicorn does neither, and Starlette's router matches ``scope["path"]`` as it
arrives, so tests about what reaches a route have to build the scope by hand.
"""

import asyncio
import base64
import json
from typing import Any, Dict, Optional, Tuple

from starlette.types import ASGIApp


def send_raw(
    app: ASGIApp, method: str, path: str, raw_path: Optional[bytes] = None
) -> Tuple[int, Dict[str, str]]:
    """Return the response status and headers for ``method path``."""
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": raw_path if raw_path is not None else path.encode(),
        "root_path": "",
        "query_string": b"",
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "client": ("testclient", 50000),
    }
    messages = [{"type": "http.request", "body": b"", "more_body": False}]
    sent = []

    async def receive() -> Dict[str, Any]:
        return messages.pop(0) if messages else {"type": "http.disconnect"}

    async def send(message: Dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(app(scope, receive, send))
    start = sent[0]
    headers = {k.decode(): v.decode() for k, v in start.get("headers", [])}
    return start["status"], headers


def required_plan(headers: Dict[str, str]) -> str:
    """The plan a 402's ``payment-required`` header asks the buyer to pay."""
    envelope = json.loads(base64.b64decode(headers["payment-required"]))
    return envelope["accepts"][0]["planId"]
