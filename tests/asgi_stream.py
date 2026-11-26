"""A response body that reports whether a middleware let it stream.

``TestClient`` and httpx's ``ASGITransport`` both run the app to completion
before they hand back a response, so a test written through them cannot tell a
streamed body from one a middleware read into memory first (payments-py#339).

:class:`StreamProbe` drives the app one ASGI message at a time instead. Its body
yields one chunk, then waits for that chunk to have reached the client before it
finishes, so it ends in :data:`STREAMED` only when it was streamed; a middleware
that drains it first holds the chunk back, the wait times out, and it ends in
:data:`BUFFERED`.
"""

import asyncio
from typing import AsyncIterator, Dict, Tuple

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message

STREAMED = b"first|streamed"
BUFFERED = b"first|buffered"


class StreamProbe:
    def __init__(self, timeout: float = 1.0):
        self._delivered = asyncio.Event()
        self._timeout = timeout

    async def body(self) -> AsyncIterator[bytes]:
        yield b"first"
        try:
            await asyncio.wait_for(self._delivered.wait(), self._timeout)
        except asyncio.TimeoutError:
            yield b"|buffered"
            return
        yield b"|streamed"

    async def request(
        self,
        app: ASGIApp,
        method: str,
        path: str,
        headers: Dict[str, str],
        body: bytes = b"",
    ) -> Tuple[Headers, bytes]:
        """Send one request to ``app``; return the response headers and body."""
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": method,
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (name.lower().encode("latin-1"), value.encode("latin-1"))
                for name, value in headers.items()
            ],
            "client": ("testclient", 50000),
            "server": ("testserver", 80),
        }
        request_sent = False

        async def receive() -> Message:
            nonlocal request_sent
            if not request_sent:
                request_sent = True
                return {"type": "http.request", "body": body, "more_body": False}
            # No disconnect: block until the app cancels the wait.
            await asyncio.Event().wait()
            raise AssertionError("unreachable")

        start: Message = {}
        chunks = []

        async def send(message: Message) -> None:
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body" and message.get("body"):
                chunks.append(message["body"])
                self._delivered.set()

        await app(scope, receive, send)
        return Headers(raw=start["headers"]), b"".join(chunks)
