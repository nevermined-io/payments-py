"""Unit tests for user-scoped listing.

``plans.get_user_plans`` / ``agents.get_user_agents`` wrap the authenticated,
caller-scoped ``GET /api/v1/protocol/{plans,agents}`` endpoints — "my plans" /
"my agents" account management, not a marketplace search. They must:
  * send the Authorization header (the backend derives "me" from the key),
  * forward pagination as ``page``/``offset``/``sortBy``/``sortOrder``,
  * forward ``orgId`` only when an org is requested,
  * raise ``PaymentsError`` on a non-2xx response.
"""

from urllib.parse import parse_qs, urlparse

import jwt
import pytest
import requests_mock

from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaginationOptions, PaymentOptions
from payments_py.environments import Environments
from payments_py.payments import Payments

BACKEND = Environments["sandbox"].backend.rstrip("/")

# A throwaway, locally-signed JWT — NOT a real credential. `_parse_nvm_api_key`
# needs a decodable key carrying `sub` + `o11y`, so we mint one per test run
# instead of committing a sandbox key.
_FAKE_API_KEY = "nvm:" + jwt.encode(
    {"sub": "0x0000000000000000000000000000000000000001", "o11y": "test-o11y"},
    "unit-test-secret-not-a-real-credential-0123456789",
    algorithm="HS256",
)


def _payments():
    return Payments.get_instance(
        PaymentOptions(nvm_api_key=_FAKE_API_KEY, environment="sandbox")
    )


class TestGetUserPlans:
    def test_returns_paginated_plans(self):
        body = {
            "total": 2,
            "page": 1,
            "offset": 10,
            "plans": [{"id": "plan-1"}, {"id": "plan-2"}],
        }
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/protocol/plans", json=body)
            result = payments.plans.get_user_plans()

        assert result["total"] == 2
        assert [p["id"] for p in result["plans"]] == ["plan-1", "plan-2"]
        # Authenticated request — the bearer token is what scopes it to "me".
        assert m.last_request.headers["Authorization"] == f"Bearer {_FAKE_API_KEY}"
        qs = parse_qs(urlparse(m.last_request.url).query)
        assert qs["page"] == ["1"]
        assert qs["offset"] == ["10"]
        assert "orgId" not in qs

    def test_scopes_to_org_when_org_id_set(self):
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/protocol/plans",
                json={"total": 0, "page": 1, "offset": 10, "plans": []},
            )
            payments.plans.get_user_plans(org_id="org-acme")

        qs = parse_qs(urlparse(m.last_request.url).query)
        assert qs["orgId"] == ["org-acme"]

    def test_forwards_pagination(self):
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/protocol/plans",
                json={"total": 0, "page": 2, "offset": 25, "plans": []},
            )
            payments.plans.get_user_plans(
                pagination=PaginationOptions(
                    page=2, offset=25, sort_by="created", sort_order="asc"
                )
            )

        qs = parse_qs(urlparse(m.last_request.url).query)
        assert qs["page"] == ["2"]
        assert qs["offset"] == ["25"]
        assert qs["sortBy"] == ["created"]
        assert qs["sortOrder"] == ["asc"]

    def test_raises_on_error(self):
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/protocol/plans",
                status_code=500,
                json={"message": "boom"},
            )
            with pytest.raises(PaymentsError):
                payments.plans.get_user_plans()


class TestGetUserAgents:
    def test_returns_paginated_agents(self):
        body = {"total": 1, "page": 1, "offset": 10, "agents": [{"id": "agent-1"}]}
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/protocol/agents", json=body)
            result = payments.agents.get_user_agents()

        assert result["total"] == 1
        assert result["agents"][0]["id"] == "agent-1"
        assert m.last_request.headers["Authorization"] == f"Bearer {_FAKE_API_KEY}"
        qs = parse_qs(urlparse(m.last_request.url).query)
        assert "orgId" not in qs

    def test_scopes_to_org_when_org_id_set(self):
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/protocol/agents",
                json={"total": 0, "page": 1, "offset": 10, "agents": []},
            )
            payments.agents.get_user_agents(org_id="org-acme")

        qs = parse_qs(urlparse(m.last_request.url).query)
        assert qs["orgId"] == ["org-acme"]

    def test_forwards_pagination(self):
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/protocol/agents",
                json={"total": 0, "page": 2, "offset": 25, "agents": []},
            )
            payments.agents.get_user_agents(
                pagination=PaginationOptions(
                    page=2, offset=25, sort_by="created", sort_order="asc"
                )
            )

        qs = parse_qs(urlparse(m.last_request.url).query)
        assert qs["page"] == ["2"]
        assert qs["offset"] == ["25"]
        assert qs["sortBy"] == ["created"]
        assert qs["sortOrder"] == ["asc"]

    def test_raises_on_error(self):
        payments = _payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/protocol/agents",
                status_code=500,
                json={"message": "boom"},
            )
            with pytest.raises(PaymentsError):
                payments.agents.get_user_agents()
