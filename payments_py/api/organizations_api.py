"""Organizations API — workspace memberships, activity feed, and member admin.

Wraps the multi-organization endpoints exposed by the Nevermined backend
(see ``apps/api/src/organizations/`` in nvm-monorepo):

- ``GET /api/v1/organizations/my-memberships`` — every organization the
  caller is an active member of, with their role.
- ``GET /api/v1/organizations/{org_id}/activity`` — paginated activity
  feed (member events, customer events, subscription transitions,
  webhook deliveries).
- ``POST /api/v1/organizations/account`` — member invitation and
  white-label customer onboarding (admin only).
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

from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlencode

import requests
from pydantic import ValidationError

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
    CustomerOnboardingResponse,
    MyMembership,
    OrganizationActivityEvent,
    OrganizationActivityFilters,
    OrganizationActivityPage,
    OrganizationInvitation,
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
    ) -> Union[OrganizationInvitation, CreateUserResponse]:
        """Invite a member to the caller's organization.

        Wraps ``POST /api/v1/organizations/account``. Admin-only on the
        backend (``OrganizationAdminGuard`` is enforced) — non-admin
        callers get a 403.

        Current backends (nvm-monorepo#5349) create a pending invitation and
        email ``user_email`` a link to join. No account is provisioned and
        nothing about one is returned: the invitee becomes a member when they
        accept. The result is an :class:`OrganizationInvitation`. Backends
        that predate that change provisioned the account at once and return
        a :class:`CreateUserResponse`; check the result's type to tell the
        two apart.

        Do not retry a call that returned an invitation: while it is
        pending, the backend refuses another one for the same email with 409
        ``BCK.INVITATIONS.0002``.

        Args:
            user_id: Caller-side identifier for the new member. Sent as
                ``uniqueExternalId``, which current backends ignore.
            user_email: Email address of the invitee. The backend requires
                it: a missing one is refused with 400 ``BCK.HTTP.400``, a
                malformed one with 400 ``BCK.INVITATIONS.0007``.
            user_role: Optional role (``ADMIN`` or ``MEMBER``); defaults
                backend-side to :class:`OrganizationMemberRole.MEMBER`.

        Returns:
            An :class:`OrganizationInvitation` from current backends, or a
            :class:`CreateUserResponse` (the new member's wallet and key
            hash) from backends that predate nvm-monorepo#5349.

        Raises:
            PaymentsError: If ``user_id`` is empty, the backend call fails,
                or the response matches neither shape. ``code`` carries the
                backend error code, e.g. ``BCK.INVITATIONS.0002`` (409, a
                pending invitation exists for this email),
                ``BCK.ORGANIZATIONS.0008`` (403, the email belongs to an
                active member of this organization),
                ``BCK.INVITATIONS.0006`` (403, the organization is below the
                Premium tier), ``BCK.INVITATIONS.0001`` (422, no free member
                seat), ``BCK.NOTIF.0007`` (500, the backend has no mail
                provider; a retry will not help) or ``BCK.ORGANIZATIONS.0041``
                (503, the invitation email was not accepted for delivery and
                nothing was created; retry after a backoff).
        """
        if not user_id:
            raise PaymentsError.validation("user_id is required")

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
            raise PaymentsError.from_backend("Unable to create member", error)

        data: Dict[str, Any] = response.json() or {}
        wallet = data.get("walletResult")
        if not isinstance(wallet, dict):
            raise PaymentsError.from_backend(
                "Unable to create member",
                {"message": "missing walletResult in response"},
            )
        # nvm-monorepo#5349: the backend invites rather than provisions, and
        # ``walletResult.invitation`` is the only thing it returns. Its
        # presence is what tells the current contract from the legacy one.
        if "invitation" in wallet:
            try:
                return OrganizationInvitation.model_validate(wallet["invitation"])
            except ValidationError as error:
                raise PaymentsError.from_backend(
                    "Unable to create member",
                    {"message": f"walletResult.invitation is malformed: {error}"},
                ) from error
        # Legacy backends store the new NVM API key under ``walletResult.hash``
        # (both the TS SDK and product copy expose it as ``nvmApiKey``).
        # Fail loudly if the required keys are absent — silent fallback to
        # empty strings would make a contract regression look like a
        # successful enrolment with invalid data.
        required_keys = ("hash", "userId", "userWallet")
        missing = [k for k in required_keys if not wallet.get(k)]
        if missing:
            raise PaymentsError.from_backend(
                "Unable to create member",
                {
                    "message": (
                        "walletResult is missing required keys: "
                        f"{', '.join(missing)}"
                    ),
                },
            )
        return CreateUserResponse(
            nvm_api_key=wallet["hash"],
            user_id=wallet["userId"],
            user_wallet=wallet["userWallet"],
            already_member=bool(wallet.get("alreadyMember", False)),
        )

    def onboard_customer(self, email: str) -> CustomerOnboardingResponse:
        """Onboard a white-label customer into the caller's organization (#2418).

        Wraps ``POST /api/v1/organizations/account`` with ``as='customer'``.
        Admin-only on the backend. Provisions a Nevermined account for the
        customer **without consuming a member seat** and returns a usable,
        scoped NVM API key the org can use to transparently act on the
        customer's behalf (purchase plans / redeem credits). The usable
        Bearer is ``walletResult.hash`` (``<prefix>:<jwt>``) and is surfaced
        as ``nvm_api_key``; the sibling
        ``walletResult.nvmApiKey`` is the encrypted server-side blob and is
        **not** a valid Bearer.

        If the email already belongs to an account the org does NOT own, no key
        is issued: the backend replies ``202`` and the result carries
        ``consent_required=True`` (an email challenge was sent to the owner, and
        the account's identity is deliberately not disclosed). Call again once
        the owner has consented to complete onboarding.

        Args:
            email: The customer's email address.

        Returns:
            A :class:`CustomerOnboardingResponse` — either the issued key
            (``nvm_api_key``, ``user_id``, ``user_wallet``, ``is_customer``,
            ``customer_recorded``) or ``consent_required=True``.

        Raises:
            PaymentsError: If ``email`` is empty, the backend call fails, or the
                response is missing the expected ``walletResult`` envelope.
        """
        if not email:
            raise PaymentsError.validation("email is required")

        body: Dict[str, Any] = {"email": email, "as": "customer"}
        url = f"{self.environment.backend}{API_URL_CREATE_USER}"
        options = self.get_backend_http_options("POST", body)
        response = requests.post(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except (ValueError, requests.exceptions.JSONDecodeError):
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to onboard customer", error)

        data: Dict[str, Any] = response.json() or {}
        wallet = data.get("walletResult")
        if not isinstance(wallet, dict):
            raise PaymentsError.from_backend(
                "Unable to onboard customer",
                {"message": "missing walletResult in response"},
            )

        result = CustomerOnboardingResponse.model_validate(wallet)
        # Existing, non-owned account: opaque consent-pending outcome. The
        # backend signals it with HTTP 202 and ``walletResult.consentRequired``;
        # treat either as authoritative and return a clean object so no identity
        # or key can leak even if the backend regresses.
        if response.status_code == 202 or result.consent_required:
            return CustomerOnboardingResponse(consent_required=True)
        # New account or returning customer: the Bearer MUST be present. The
        # backend returns the usable credential as ``walletResult.hash``
        # (``<prefix>:<jwt>``); the sibling ``nvmApiKey`` — which the
        # ``model_validate`` above mapped into ``nvm_api_key`` — is the encrypted
        # server-side blob and is NOT a valid Bearer. Surface ``hash`` instead.
        # A 2xx without a hash means a partial/unexpected payload — fail loudly
        # rather than return a "success" carrying no usable credential.
        # ``model_copy(update=…)`` below does not validate, so assert the shape
        # here: the backend contract is ``<env>:<JWT>`` — a non-string truthy
        # ``hash`` must never reach ``Payments`` as the Bearer.
        hash_key = wallet.get("hash")
        if not isinstance(hash_key, str) or not hash_key:
            raise PaymentsError.from_backend(
                "Unable to onboard customer",
                {
                    "message": (
                        "onboarding completed but no API key was returned "
                        "(unexpected backend response)"
                    )
                },
            )
        return result.model_copy(update={"nvm_api_key": hash_key})

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
