"""Organizations API — workspace memberships, activity feed, and member admin.

Wraps the multi-organization endpoints exposed by the Nevermined backend
(see ``apps/api/src/organizations/`` in nvm-monorepo):

- ``GET /api/v1/organizations/my-memberships`` — every organization the
  caller is an active member of, with their role.
- ``GET /api/v1/organizations/{org_id}/activity`` — paginated activity
  feed (member events, customer events, subscription transitions,
  webhook deliveries).
- ``POST /api/v1/organizations/account`` — Privy-backed member enrolment
  (admin only).
- ``POST /api/v1/organizations/members`` — paginated member listing
  (admin only).
- ``POST /api/v1/fiat/stripe/account`` — Stripe Connect onboarding
  link (admin only).

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
from payments_py.api.nvm_api import (
    API_URL_CONNECT_STRIPE_ACCOUNT,
    API_URL_CREATE_USER,
    API_URL_GET_MEMBERS,
    API_URL_MY_MEMBERSHIPS,
    API_URL_ORG_ACTIVITY,
)
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    CreateUserResponse,
    MyMembership,
    OrganizationActivityEvent,
    OrganizationActivityFilters,
    OrganizationActivityPage,
    OrganizationMember,
    OrganizationMemberRole,
    OrganizationMembersResponse,
    PaymentOptions,
    StripeAccountConnectResult,
)


class OrganizationsAPI(BasePaymentsAPI):
    """Workspace memberships and organization activity feed.

    Example::

        payments = Payments.get_instance(options)
        memberships = payments.organizations.get_my_memberships()
        for membership in memberships:
            print(membership.org_name, "-", membership.role)
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
                if isinstance(event_type, list):
                    joined = ",".join(
                        getattr(value, "value", str(value)) for value in event_type
                    )
                    if joined:
                        query_params["eventType"] = joined
                else:
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
            if filters.limit is not None:
                query_params["limit"] = str(filters.limit)

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
        return OrganizationActivityPage(items=items, total=int(data.get("total", 0)))

    def create_member(
        self,
        user_id: str,
        user_email: Optional[str] = None,
        user_role: Optional[OrganizationMemberRole] = None,
    ) -> CreateUserResponse:
        """Enrol a new member in the caller's organization.

        Wraps ``POST /api/v1/organizations/account``. Admin-only on the
        backend (``OrganizationAdminGuard`` is enforced) — non-admin
        callers get a 403. The endpoint provisions a fresh Privy wallet
        for ``user_id`` and binds it to the active workspace.

        Args:
            user_id: Stable external id for the new member (e.g. an
                identifier from the org admin's own user-management
                system). The backend uses it as ``uniqueExternalId``.
            user_email: Optional email; if omitted the backend uses the
                wallet address as a placeholder.
            user_role: Optional role; defaults backend-side to
                :class:`OrganizationMemberRole.MEMBER`.

        Returns:
            A :class:`CreateUserResponse` with the new member's wallet
            and NVM API key.

        Raises:
            PaymentsError: If the backend call fails (403 for non-admin
                callers, validation errors for bad input).
        """
        body: Dict[str, Any] = {"uniqueExternalId": user_id}
        if user_email is not None:
            body["email"] = user_email
        if user_role is not None:
            body["role"] = getattr(user_role, "value", str(user_role))

        url = f"{self.environment.backend}{API_URL_CREATE_USER}"
        options = self.get_backend_http_options("POST", body)
        response = requests.post(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to create user", error)

        data: Dict[str, Any] = response.json() or {}
        wallet = data.get("walletResult") or {}
        # The backend stores the new NVM API key under ``walletResult.hash``;
        # both the TS SDK and product copy expose it as ``nvmApiKey``.
        return CreateUserResponse(
            nvm_api_key=wallet.get("hash", ""),
            user_id=wallet.get("userId", ""),
            user_wallet=wallet.get("userWallet", ""),
            already_member=bool(wallet.get("alreadyMember", False)),
        )

    def get_members(
        self,
        role: Optional[OrganizationMemberRole] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        offset: int = 100,
    ) -> OrganizationMembersResponse:
        """List members of the caller's organization (admin-only).

        Wraps ``POST /api/v1/organizations/members``. The active
        workspace is derived from ``X-Current-Org-Id`` / the API key's
        org tag, so callers don't need to pass an ``org_id``.

        Args:
            role: Optional role filter — ``ADMIN`` or ``MEMBER``.
            is_active: Optional active-state filter.
            page: 1-based page number. Defaults to ``1``.
            offset: Page size. Defaults to ``100``; backend caps higher
                values server-side.

        Returns:
            A paginated :class:`OrganizationMembersResponse`.

        Raises:
            PaymentsError: If the backend call fails (403 for non-admin
                callers).
        """
        body: Dict[str, Any] = {"page": page, "offset": offset}
        if role is not None:
            body["role"] = getattr(role, "value", str(role))
        if is_active is not None:
            body["isActive"] = is_active

        url = f"{self.environment.backend}{API_URL_GET_MEMBERS}"
        options = self.get_backend_http_options("POST", body)
        response = requests.post(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to get members", error)

        data: Dict[str, Any] = response.json() or {}
        members_raw = data.get("members") or []
        members = [OrganizationMember.model_validate(item) for item in members_raw]
        # Backend exposes the total as ``totalResults`` but we normalise
        # to ``total`` to match the TS SDK and the activity-feed shape.
        total = data.get("totalResults", data.get("total", 0))
        return OrganizationMembersResponse(members=members, total=int(total))

    def connect_stripe_account(
        self,
        user_email: str,
        user_country_code: str,
        return_url: str,
    ) -> StripeAccountConnectResult:
        """Generate a Stripe Connect onboarding link for the active workspace.

        Wraps ``POST /api/v1/fiat/stripe/account``. The link the
        backend returns sends the org admin through Stripe's hosted
        Connect onboarding so the workspace can accept fiat payouts.

        Args:
            user_email: Email address that should own the Stripe
                account.
            user_country_code: ISO 3166-1 alpha-2 country code
                (e.g. ``"US"``, ``"ES"``).
            return_url: URL Stripe redirects to after onboarding
                completes.

        Returns:
            A :class:`StripeAccountConnectResult` carrying the hosted
            onboarding link and identifiers.

        Raises:
            PaymentsError: If the backend call fails.
        """
        body: Dict[str, Any] = {
            "userEmail": user_email,
            "userCountryCode": user_country_code,
            "returnUrl": return_url,
        }
        url = f"{self.environment.backend}{API_URL_CONNECT_STRIPE_ACCOUNT}"
        options = self.get_backend_http_options("POST", body)
        response = requests.post(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to connect with Stripe", error)

        data: Dict[str, Any] = response.json() or {}
        return StripeAccountConnectResult.model_validate(data)


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
