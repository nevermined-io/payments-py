"""Unit tests for the OrganizationsAPI workspace surface.

Covers the two new endpoints (``GET /my-memberships`` and
``GET /:orgId/activity``) plus the ``X-Current-Org-Id`` header
plumbing — instance pin via ``PaymentOptions.organization_id`` /
``Payments.set_organization_id`` and per-call override on the
publish methods.

The mock NVM API key is the same fixture used in ``test_payments.py``.
"""

import os
from urllib.parse import parse_qs, urlparse

import pytest
import requests_mock

from payments_py.api.base_payments import CURRENT_ORG_ID_HEADER
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    AgentAPIAttributes,
    AgentMetadata,
    MyMembership,
    OrganizationActivityEventType,
    OrganizationActivityFilters,
    OrganizationMemberRole,
    OrganizationType,
    PaymentOptions,
    PlanCreditsConfig,
    PlanMetadata,
    PlanPriceConfig,
    PlanRedemptionType,
)
from payments_py.environments import Environments
from payments_py.payments import Payments

TEST_API_KEY = os.getenv(
    "TEST_PROXY_BEARER_TOKEN",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweEVCNDk3OTU2OTRBMDc1QTY0ZTY2MzdmMUU5MGYwMjE0Mzg5YjI0YTMiLCJqdGkiOiIweGMzYjYyMWJkYTM5ZDllYWQyMTUyMDliZWY0MDBhMDEzYjM1YjQ2Zjc1NzM4YWFjY2I5ZjdkYWI0ZjQ5MmM5YjgiLCJleHAiOjE3OTQ2NTUwNjAsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.YMkGQUjGh7_m07nj8SKXZReNKSryg9mTU3qwJr_TKYATUixbYQTte3CKucjqvgAGzJAd1Kq2ubz3b37n5Zsllxs",
)

BACKEND = Environments["staging_sandbox"].backend.rstrip("/")


def _make_payments(organization_id=None):
    return Payments.get_instance(
        PaymentOptions(
            nvm_api_key=TEST_API_KEY,
            environment="staging_sandbox",
            organization_id=organization_id,
        )
    )


def _make_publish_fixtures():
    """Minimal AgentMetadata/AgentAPI/PlanPriceConfig/PlanCreditsConfig
    fixtures suitable for register_* mocks.
    """
    return {
        "agent_metadata": AgentMetadata(name="Bot"),
        "agent_api": AgentAPIAttributes(),
        "plan_metadata": PlanMetadata(name="Plan"),
        "price_config": PlanPriceConfig(amounts=[0], receivers=[], is_crypto=True),
        "credits_config": PlanCreditsConfig(
            is_redemption_amount_fixed=True,
            redemption_type=PlanRedemptionType.ONLY_OWNER,
            duration_secs=0,
            amount="100",
            min_amount=1,
            max_amount=1,
        ),
    }


class TestGetMyMemberships:
    def test_returns_parsed_list(self):
        payments = _make_payments()
        body = [
            {
                "orgId": "org-aaa",
                "orgName": "Acme",
                "role": "Admin",
                "orgType": "Premium",
                "isAdmin": True,
                "hasSubscriptionHistory": True,
            },
            {
                "orgId": "org-bbb",
                "orgName": "Beta",
                "role": "Member",
                "orgType": "Enterprise",
                "isAdmin": False,
                "hasSubscriptionHistory": True,
            },
        ]
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/organizations/my-memberships", json=body)
            memberships = payments.organizations.get_my_memberships()

        assert len(memberships) == 2
        assert isinstance(memberships[0], MyMembership)
        assert memberships[0].org_id == "org-aaa"
        assert memberships[0].org_name == "Acme"
        assert memberships[0].org_type == OrganizationType.PREMIUM
        assert memberships[0].role == OrganizationMemberRole.ADMIN
        assert memberships[0].is_admin is True
        assert memberships[1].role == OrganizationMemberRole.MEMBER
        assert memberships[1].is_admin is False

    def test_tolerates_unexpected_non_array_body(self):
        # Backend changes that return an object instead of an array must
        # not crash the SDK — `get_my_memberships()` should degrade
        # gracefully to an empty list rather than a TypeError.
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/organizations/my-memberships",
                json={"unexpected": "shape"},
            )
            assert payments.organizations.get_my_memberships() == []

    def test_raises_on_5xx(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/organizations/my-memberships",
                status_code=500,
                json={"message": "boom"},
            )
            with pytest.raises(PaymentsError):
                payments.organizations.get_my_memberships()


class TestGetOrganizationActivity:
    def test_encodes_filters_in_query_string(self):
        payments = _make_payments()
        body = {"items": [], "total": 0}
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/organizations/org-xyz/activity",
                json=body,
            )
            page = payments.organizations.get_organization_activity(
                "org-xyz",
                OrganizationActivityFilters(
                    event_type=OrganizationActivityEventType.MEMBER_INVITED,
                    actor_user_id="us-1",
                    **{"from": "2026-01-01T00:00:00Z"},
                    to="2026-12-31T23:59:59Z",
                    page=2,
                    limit=25,
                ),
            )

        assert page.total == 0
        assert m.last_request is not None
        qs = parse_qs(urlparse(m.last_request.url).query)
        assert qs["eventType"] == ["member.invited"]
        assert qs["actorUserId"] == ["us-1"]
        assert qs["from"] == ["2026-01-01T00:00:00Z"]
        assert qs["to"] == ["2026-12-31T23:59:59Z"]
        assert qs["page"] == ["2"]
        assert qs["limit"] == ["25"]

    def test_joins_array_event_type_filter(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/organizations/org-xyz/activity",
                json={"items": [], "total": 0},
            )
            payments.organizations.get_organization_activity(
                "org-xyz",
                OrganizationActivityFilters(
                    event_type=[
                        OrganizationActivityEventType.PLAN_CREATED,
                        OrganizationActivityEventType.AGENT_CREATED,
                    ],
                ),
            )
            qs = parse_qs(urlparse(m.last_request.url).query)
            assert qs["eventType"] == ["plan.created,agent.created"]

    def test_no_filters_means_no_query_string(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/organizations/org-xyz/activity",
                json={"items": [], "total": 0},
            )
            payments.organizations.get_organization_activity("org-xyz")
            assert m.last_request.qs == {}

    def test_parses_items(self):
        payments = _make_payments()
        body = {
            "items": [
                {
                    "id": "ae-1",
                    "eventType": "plan.created",
                    "actorUserId": "us-admin",
                    "subject": {
                        "kind": "plan",
                        "id": "12345",
                        "name": "Test Plan",
                    },
                    "metadata": {"foo": "bar"},
                    "occurredAt": "2026-05-21T00:00:00Z",
                },
            ],
            "total": 1,
        }
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/organizations/org-xyz/activity", json=body)
            page = payments.organizations.get_organization_activity("org-xyz")

        assert page.total == 1
        assert len(page.items) == 1
        event = page.items[0]
        assert event.id == "ae-1"
        assert event.event_type == "plan.created"
        assert event.actor_user_id == "us-admin"
        assert event.subject.kind == "plan"
        assert event.subject.id == "12345"
        # Extras from the subject flow through via Pydantic's extra="allow".
        assert getattr(event.subject, "name", None) == "Test Plan"
        assert event.metadata == {"foo": "bar"}
        assert event.occurred_at == "2026-05-21T00:00:00Z"

    def test_rejects_without_org_id(self):
        payments = _make_payments()
        with pytest.raises(PaymentsError):
            payments.organizations.get_organization_activity("")

    def test_raises_on_403(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(
                f"{BACKEND}/api/v1/organizations/org-forbidden/activity",
                status_code=403,
                json={"errorCode": "BCK.AUTH.0004", "message": "not a member"},
            )
            with pytest.raises(PaymentsError):
                payments.organizations.get_organization_activity("org-forbidden")


class TestInstanceLevelOrgPin:
    def test_constructor_option_sets_header(self):
        payments = _make_payments(organization_id="org-pin")
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/organizations/my-memberships", json=[])
            payments.organizations.get_my_memberships()

            assert m.last_request.headers.get(CURRENT_ORG_ID_HEADER) == "org-pin"

    def test_set_organization_id_mutates_subsequent_calls(self):
        payments = _make_payments()
        with requests_mock.Mocker() as m:
            m.get(f"{BACKEND}/api/v1/organizations/my-memberships", json=[])

            payments.organizations.get_my_memberships()
            first_header = m.last_request.headers.get(CURRENT_ORG_ID_HEADER)

            payments.set_organization_id("org-after-set")
            payments.organizations.get_my_memberships()
            second_header = m.last_request.headers.get(CURRENT_ORG_ID_HEADER)

            payments.set_organization_id(None)
            payments.organizations.get_my_memberships()
            third_header = m.last_request.headers.get(CURRENT_ORG_ID_HEADER)

        assert first_header is None
        assert second_header == "org-after-set"
        assert third_header is None

    def test_set_organization_id_propagates_to_sibling_apis(self):
        payments = _make_payments()
        payments.set_organization_id("org-fan-out")

        assert payments.agents.get_organization_id() == "org-fan-out"
        assert payments.plans.get_organization_id() == "org-fan-out"
        assert payments.organizations.get_organization_id() == "org-fan-out"


class TestPerCallOrgOverride:
    def test_register_agent_forwards_organization_id_without_mutating_pin(self):
        payments = _make_payments(organization_id="org-pinned")
        fixtures = _make_publish_fixtures()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/protocol/agents",
                json={"data": {"agentId": "ag-1"}},
            )
            payments.agents.register_agent(
                fixtures["agent_metadata"],
                fixtures["agent_api"],
                ["plan-1"],
                organization_id="org-override",
            )

            assert m.last_request.headers.get(CURRENT_ORG_ID_HEADER) == "org-override"

        # Instance pin must not be overwritten by the per-call hint.
        assert payments.agents.get_organization_id() == "org-pinned"
        assert payments.get_organization_id() == "org-pinned"

    def test_register_agent_falls_back_to_pin_when_no_override(self):
        payments = _make_payments(organization_id="org-pinned")
        fixtures = _make_publish_fixtures()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/protocol/agents",
                json={"data": {"agentId": "ag-2"}},
            )
            payments.agents.register_agent(
                fixtures["agent_metadata"],
                fixtures["agent_api"],
                ["plan-1"],
            )

            assert m.last_request.headers.get(CURRENT_ORG_ID_HEADER) == "org-pinned"

    def test_register_agent_and_plan_accepts_override(self):
        payments = _make_payments()
        fixtures = _make_publish_fixtures()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/protocol/agents/plans",
                json={
                    "data": {"agentId": "ag-3", "planId": "pl-3"},
                    "txHash": "0xabc",
                },
            )
            payments.agents.register_agent_and_plan(
                fixtures["agent_metadata"],
                fixtures["agent_api"],
                fixtures["plan_metadata"],
                fixtures["price_config"],
                fixtures["credits_config"],
                None,
                organization_id="org-c",
            )

            assert m.last_request.headers.get(CURRENT_ORG_ID_HEADER) == "org-c"

    def test_register_plan_forwards_override(self):
        payments = _make_payments()
        fixtures = _make_publish_fixtures()
        with requests_mock.Mocker() as m:
            m.post(
                f"{BACKEND}/api/v1/protocol/plans",
                json={"planId": "pl-4"},
            )
            payments.plans.register_plan(
                fixtures["plan_metadata"],
                fixtures["price_config"],
                fixtures["credits_config"],
                organization_id="org-d",
            )

            assert m.last_request.headers.get(CURRENT_ORG_ID_HEADER) == "org-d"
