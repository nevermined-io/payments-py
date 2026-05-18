"""Organizations API — workspace memberships and activity feed.

Wraps the multi-organization endpoints exposed by the Nevermined backend
(see ``apps/api/src/organizations/`` in nvm-monorepo):

- ``GET /api/v1/organizations/my-memberships`` — every organization the
  caller is an active member of, with their role.
- ``GET /api/v1/organizations/{org_id}/activity`` — paginated activity
  feed (member events, customer events, subscription transitions,
  webhook deliveries).

The active workspace for write operations (publishing agents, plans, …)
is selected via the inherited ``X-Current-Org-Id`` header plumbing on
:class:`BasePaymentsAPI`. Pin it instance-wide via
:meth:`Payments.set_organization_id` or pass ``organization_id=`` on the
relevant publish method for a one-off override.
"""

from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import requests

from payments_py.api.base_payments import (
    CURRENT_ORG_ID_HEADER,
    BasePaymentsAPI,
)
from payments_py.api.nvm_api import API_URL_MY_MEMBERSHIPS, API_URL_ORG_ACTIVITY
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    MyMembership,
    OrganizationActivityEvent,
    OrganizationActivityFilters,
    OrganizationActivityPage,
    PaymentOptions,
)


class OrganizationsAPI(BasePaymentsAPI):
    """Workspace memberships and organization activity feed.

    Example::

        payments = Payments.get_instance(options)
        memberships = payments.organizations.get_my_memberships()
        for membership in memberships:
            print(membership.organization_name, "-", membership.role)
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "OrganizationsAPI":
        """Get a singleton-like instance of :class:`OrganizationsAPI`."""
        return cls(options)

    def get_my_memberships(self) -> List[MyMembership]:
        """List every organization the authenticated user is an active member of.

        Returns:
            A list of :class:`MyMembership` — empty when the user has no
            active memberships and operates as a personal account.

        Raises:
            PaymentsError: If the backend call fails.
        """
        url = f"{self.environment.backend}{API_URL_MY_MEMBERSHIPS}"
        options = self.get_backend_http_options("GET")
        response = requests.get(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to fetch memberships", error)

        data = response.json()
        if not isinstance(data, list):
            return []
        return [MyMembership.model_validate(item) for item in data]

    def get_organization_activity(
        self,
        org_id: str,
        filters: Optional[OrganizationActivityFilters] = None,
    ) -> OrganizationActivityPage:
        """List activity events for an organization the caller is a member of.

        Requires Member or Admin membership on ``org_id``; Premium-tier
        entitlement is enforced server-side. The backend returns 403
        otherwise.

        Args:
            org_id: Organization id (e.g. ``"org-..."``) whose feed to read.
            filters: Optional :class:`OrganizationActivityFilters` filter
                set (event type, actor, date range, pagination).

        Returns:
            A paginated :class:`OrganizationActivityPage`.

        Raises:
            PaymentsError: If ``org_id`` is missing or the backend call fails.
        """
        if not org_id:
            raise PaymentsError.validation("org_id is required")

        query_params: Dict[str, str] = {}
        if filters is not None:
            event_type = filters.event_type
            if event_type is not None:
                query_params["eventType"] = getattr(
                    event_type, "value", str(event_type)
                )
            if filters.actor_user_id:
                query_params["actorUserId"] = filters.actor_user_id
            if filters.from_:
                query_params["from"] = filters.from_
            if filters.to:
                query_params["to"] = filters.to
            if filters.page is not None:
                query_params["page"] = str(filters.page)
            if filters.offset is not None:
                query_params["offset"] = str(filters.offset)

        path = API_URL_ORG_ACTIVITY.format(org_id=org_id)
        query_string = urlencode(query_params)
        url = f"{self.environment.backend}{path}"
        if query_string:
            url = f"{url}?{query_string}"

        options = self.get_backend_http_options("GET")
        response = requests.get(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend(
                "Unable to fetch organization activity", error
            )

        data: Dict[str, Any] = response.json() or {}
        items_raw = data.get("items") or []
        items = [OrganizationActivityEvent.model_validate(item) for item in items_raw]
        return OrganizationActivityPage(
            items=items,
            total=int(data.get("total", 0)),
            page=int(data.get("page", filters.page if filters and filters.page else 1)),
            offset=int(
                data.get("offset", filters.offset if filters and filters.offset else 10)
            ),
        )


def resolve_publication_headers(
    organization_id: Optional[str],
) -> Optional[Dict[str, str]]:
    """Build the per-call ``extra_headers`` dict for publish methods.

    Returns ``None`` when no override is requested so existing callers
    receive identical request shapes.
    """
    if organization_id:
        return {CURRENT_ORG_ID_HEADER: organization_id}
    return None
