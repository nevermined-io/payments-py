"""
Transport doubles for the MPP buyer tests.

``payments.mpp.fetch`` drives ``requests.request`` directly, so the tests queue
responses (or exceptions) on a fake and assert on what was sent.
"""

from typing import Any, Dict, List, Optional, Sequence, Union

import pytest
import requests

DEFAULT_URL = "https://agent.example/ask"


def make_response(
    status: int,
    headers: Optional[Dict[str, str]] = None,
    body: Union[bytes, str] = b"",
    url: str = DEFAULT_URL,
) -> requests.Response:
    """A fully-buffered ``requests.Response``, the shape a non-streamed call
    yields."""
    response = requests.Response()
    response.status_code = status
    response.url = url
    response.encoding = "utf-8"
    if headers:
        response.headers.update(headers)
    response._content = body.encode("utf-8") if isinstance(body, str) else body
    response._content_consumed = True
    return response


class FakeTransport:
    """Returns queued responses in order, recording every call.

    A queued ``Exception`` is raised instead of returned, which is how a
    transport failure is placed on a specific turn.
    """

    def __init__(self, queue: Sequence[Any]):
        self.queue: List[Any] = list(queue)
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.queue:
            raise AssertionError(
                f"unexpected request #{len(self.calls)} to {method} {url}"
            )
        nxt = self.queue.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return nxt

    @property
    def count(self) -> int:
        return len(self.calls)


@pytest.fixture
def transport(monkeypatch):
    """Install a :class:`FakeTransport` over the buyer helper's ``requests``.

    Yields a factory: ``transport([resp1, resp2])`` queues and returns the fake.
    """
    installed: Dict[str, FakeTransport] = {}

    def install(queue: Sequence[Any]) -> FakeTransport:
        fake = FakeTransport(queue)
        monkeypatch.setattr("payments_py.mpp.fetch.requests.request", fake)
        installed["fake"] = fake
        return fake

    return install


class FakeMinter:
    """Stands in for ``MppAPI.get_mpp_access_token``."""

    def __init__(self, access_token: str = "BASE64_MPP_TOKEN", error: Any = None):
        self.access_token = access_token
        self.error = error
        self.calls: List[Dict[str, Any]] = []

    def __call__(self, plan_id, agent_id=None, token_options=None):
        self.calls.append(
            {"plan_id": plan_id, "agent_id": agent_id, "token_options": token_options}
        )
        if self.error is not None:
            raise self.error
        return {"accessToken": f"{self.access_token}-{len(self.calls)}"}

    @property
    def count(self) -> int:
        return len(self.calls)


@pytest.fixture
def minter():
    return FakeMinter()
