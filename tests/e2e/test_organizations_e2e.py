"""End-to-end coverage for the multi-org workspace surface added in PR #179.

Runs against staging-sandbox using the ``Testing Merchant`` fixture identity,
which is an Admin of the Enterprise org ``Nevermined Testing``. Verifies the
three building blocks the SDK now exposes:

  1. ``get_my_memberships()`` returns the org the caller belongs to with the
     backend-defined shape (orgId / orgName / role / orgType / isAdmin).
  2. Pinning the workspace via ``set_organization_id(org_id)`` routes a
     publish into that org — the resulting plan carries the org id.
  3. The per-call ``organization_id=`` override on a publish method does the
     same thing for a single call without mutating the instance pin.

``get_organization_activity`` is exercised as a smoke read; the assertion is
only that the call returns a paginated shape.
"""

from datetime import datetime, timezone

import pytest

from payments_py.common.types import (
    OrganizationActivityEventType,
    OrganizationActivityFilters,
    OrganizationMemberRole,
    OrganizationType,
    PaymentOptions,
    PlanMetadata,
)
from payments_py.payments import Payments
from payments_py.plans import (
    get_crypto_price_config,
    get_fixed_credits_config,
)

from tests.e2e.conftest import (
    BUILDER_API_KEY,
    TEST_BUILDER_ORG_ID,
    TEST_ENVIRONMENT,
)

pytestmark = pytest.mark.slow


def _unpinned_payments() -> Payments:
    """Fresh client with no pinned workspace; lets the test drive the pin."""
    return Payments(
        PaymentOptions(nvm_api_key=BUILDER_API_KEY, environment=TEST_ENVIRONMENT)
    )


def _ensure_in_target_org() -> Payments:
    """Skip the test cleanly if the configured ``BUILDER_API_KEY`` identity
    is not a member of ``TEST_BUILDER_ORG_ID``.

    Some CI environments still wire the legacy fixture accounts that
    aren't members of the new Enterprise test org; in that case these
    tests skip rather than fail. Once the secrets are rotated to the
    ``testing-merchant@nevermined.io`` / ``testing-buyer@nevermined.io``
    identities described in CLAUDE.md, every test runs.
    """
    payments = _unpinned_payments()
    try:
        memberships = payments.organizations.get_my_memberships()
    except Exception as e:  # pragma: no cover - network failure path
        pytest.skip(f"get_my_memberships() failed: {e}")
    if not any(m.org_id == TEST_BUILDER_ORG_ID for m in memberships):
        pytest.skip(
            f"account is not a member of {TEST_BUILDER_ORG_ID}; "
            "rotate TEST_BUILDER_API_KEY to enable"
        )
    return payments


def test_get_my_memberships_returns_enterprise_org_with_dto_shape():
    payments = _ensure_in_target_org()
    memberships = payments.organizations.get_my_memberships()

    assert isinstance(memberships, list)
    assert len(memberships) > 0

    matches = [m for m in memberships if m.org_id == TEST_BUILDER_ORG_ID]
    assert matches, f"expected to find {TEST_BUILDER_ORG_ID} in memberships"
    m = matches[0]
    assert m.org_name
    assert m.org_type == OrganizationType.ENTERPRISE
    assert m.role in (OrganizationMemberRole.ADMIN, OrganizationMemberRole.MEMBER)
    assert isinstance(m.is_admin, bool)
    assert isinstance(m.has_subscription_history, bool)


def test_set_organization_id_routes_published_plan_into_target_org():
    payments = _ensure_in_target_org()
    payments.set_organization_id(TEST_BUILDER_ORG_ID)
    assert payments.get_organization_id() == TEST_BUILDER_ORG_ID

    builder_address = payments.get_account_address()
    price_config = get_crypto_price_config(0, builder_address)
    credits_config = get_fixed_credits_config(100, 1)

    plan_name = f"E2E orgs set_organization_id {datetime.now(timezone.utc).isoformat()}"
    result = payments.plans.register_plan(
        plan_metadata=PlanMetadata(name=plan_name),
        price_config=price_config,
        credits_config=credits_config,
    )
    plan_id = result["planId"]
    assert plan_id

    plan = payments.plans.get_plan(plan_id)
    assert plan.get("orgId") == TEST_BUILDER_ORG_ID

    # Reset pin to a known state.
    payments.set_organization_id(None)
    assert payments.get_organization_id() is None


def test_per_call_organization_id_override_targets_org_without_mutating_pin():
    payments = _ensure_in_target_org()
    assert payments.get_organization_id() is None

    builder_address = payments.get_account_address()
    price_config = get_crypto_price_config(0, builder_address)
    credits_config = get_fixed_credits_config(100, 1)

    plan_name = f"E2E orgs per-call override {datetime.now(timezone.utc).isoformat()}"
    result = payments.plans.register_plan(
        plan_metadata=PlanMetadata(name=plan_name),
        price_config=price_config,
        credits_config=credits_config,
        organization_id=TEST_BUILDER_ORG_ID,
    )
    plan_id = result["planId"]
    assert plan_id

    plan = payments.plans.get_plan(plan_id)
    assert plan.get("orgId") == TEST_BUILDER_ORG_ID
    assert payments.get_organization_id() is None


def test_get_organization_activity_returns_paginated_page():
    payments = _ensure_in_target_org()
    page = payments.organizations.get_organization_activity(
        TEST_BUILDER_ORG_ID,
        OrganizationActivityFilters(page=1, limit=5),
    )

    assert isinstance(page.items, list)
    assert isinstance(page.total, int)
    assert len(page.items) > 0

    event = page.items[0]
    assert isinstance(event.id, str)
    assert isinstance(event.event_type, str)
    assert event.subject is not None
    assert isinstance(event.subject.kind, str)
    assert isinstance(event.subject.id, str)
    assert isinstance(event.occurred_at, str)


def test_get_organization_activity_narrows_by_event_type():
    payments = _ensure_in_target_org()
    page = payments.organizations.get_organization_activity(
        TEST_BUILDER_ORG_ID,
        OrganizationActivityFilters(
            event_type=OrganizationActivityEventType.PLAN_CREATED,
            page=1,
            limit=10,
        ),
    )
    assert all(
        event.event_type == OrganizationActivityEventType.PLAN_CREATED.value
        for event in page.items
    )
