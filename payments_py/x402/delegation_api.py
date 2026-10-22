"""
Delegation API for managing payment methods and delegations.

Provides access to the user's enrolled payment methods (Stripe, Braintree,
and Visa) and delegations for use with both nvm:erc4337 and
nvm:card-delegation x402 schemes.
"""

import requests
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.x402.types import (
    CreateDelegationPayload,
    CreateDelegationResponse,
    DelegationProvider,
    UpdatePaymentMethodDto,
)


class PaymentMethodSummary(BaseModel):
    """
    Summary of a user's enrolled payment method.

    The list returned by ``list_payment_methods`` is heterogeneous: it
    includes enrolled cards (``provider`` in ``stripe`` / ``braintree`` /
    ``visa``) AND, when the user has a smart account configured, an
    entry for the user's ERC-4337 wallet (``provider='erc4337'``,
    ``type='crypto_wallet'``, ``brand='ethereum'``). Filter on
    ``provider`` when callers only want one shape.

    Attributes:
        id: Payment method ID (Stripe 'pm_...', Braintree vault token,
            Visa Agentic token id 'vat_...', or — for the erc4337 entry —
            the user's smart-account address)
        type: Payment method type ('card', 'crypto_wallet', 'paypal', …)
        brand: Card brand (e.g., 'visa', 'mastercard'), 'ethereum' for
            the erc4337 entry, or payment method type ('paypal', 'venmo')
        last4: Last 4 digits (cards), trailing 4 chars of the wallet
            address (erc4337), or email/username (PayPal/Venmo)
        exp_month: Expiration month (None / 0 for non-card methods)
        exp_year: Expiration year (None / 0 for non-card methods)
        alias: Human-readable alias, if set
        provider: One of 'stripe' | 'braintree' | 'visa' | 'vgs' | 'erc4337'
            ('vgs' = a card tokenised in the VGS vault, e.g. Visa Agentic)
        status: Current status ('Active' or 'Revoked')
        allowed_api_key_ids: NVM API Key IDs allowed to use this payment
            method, or None if unrestricted
    """

    id: str
    type: Optional[str] = None
    brand: str
    last4: str
    exp_month: Optional[int] = Field(0, alias="expMonth")
    exp_year: Optional[int] = Field(0, alias="expYear")
    alias: Optional[str] = None
    provider: Optional[DelegationProvider] = None
    status: Optional[str] = None
    allowed_api_key_ids: Optional[List[str]] = Field(None, alias="allowedApiKeyIds")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class DelegationSummary(BaseModel):
    """
    Summary of an existing delegation (card or crypto).

    Mirrors the backend ``DelegationSummaryDto`` (nvm-monorepo
    ``apps/api/src/delegation/dto/delegation-response.dto.ts``) and the TS
    ``DelegationSummary``. The cents figures are strings on the wire — they
    accrue at sub-cent (micros) resolution and are reported rounded, so they
    are kept as strings rather than coerced to int.

    Attributes:
        delegation_id: Delegation UUID (wire ``delegationId``)
        provider: Payment provider, e.g. 'stripe', 'braintree', 'visa',
            'erc4337'. Kept a free ``str`` (like the TS ``DelegationSummary``)
            so an unknown provider from the backend never breaks parsing.
        provider_payment_method_id: Provider-side payment method / wallet id
            (wire ``providerPaymentMethodId``)
        status: Delegation status ('Active' | 'Revoked' | 'Expired' | 'Exhausted')
        spending_limit_cents: Maximum spending limit, whole cents (string)
        amount_spent_cents: Amount already spent, whole cents (string)
        remaining_budget_cents: Whole cents left under the cap (string)
        currency: Currency code (e.g., 'usd')
        transaction_count: Number of payments made against this delegation
        expires_at: ISO 8601 expiration timestamp
        created_at: ISO 8601 creation timestamp
        api_key_id: NVM API Key ID this delegation is pinned to, or None
    """

    delegation_id: str = Field(alias="delegationId")
    provider: Optional[str] = None
    provider_payment_method_id: Optional[str] = Field(
        None, alias="providerPaymentMethodId"
    )
    status: Optional[str] = None
    spending_limit_cents: Optional[str] = Field(None, alias="spendingLimitCents")
    amount_spent_cents: Optional[str] = Field(None, alias="amountSpentCents")
    remaining_budget_cents: Optional[str] = Field(None, alias="remainingBudgetCents")
    currency: Optional[str] = None
    transaction_count: Optional[int] = Field(None, alias="transactionCount")
    expires_at: Optional[str] = Field(None, alias="expiresAt")
    created_at: Optional[str] = Field(None, alias="createdAt")
    api_key_id: Optional[str] = Field(None, alias="apiKeyId")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class DelegationListResponse(BaseModel):
    """Paginated list of delegations returned by ``GET /api/v1/delegation``.

    Mirrors the backend ``DelegationListDto`` and the TS
    ``DelegationListResponse``.
    """

    # `delegations` is required (no default): a glitchy ``{}`` body then raises
    # rather than silently parsing as "zero delegations". A genuine empty page
    # is ``{"delegations": []}`` and still validates.
    delegations: List[DelegationSummary]
    total_results: int = Field(0, alias="totalResults")
    page: int = 1
    offset: int = 0

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class PurchasingPower(BaseModel):
    """An agent's purchasing power: accessible cards, active delegations, and
    their combined remaining budget. Mirrors the TS ``PurchasingPower``.
    """

    cards: List[PaymentMethodSummary] = Field(default_factory=list)
    delegations: List[DelegationSummary] = Field(default_factory=list)
    total_remaining_budget_cents: int = Field(0, alias="totalRemainingBudgetCents")
    currency: str = "usd"

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


def _parse_cents(value: Any) -> int:
    """Parse a whole-cents wire string to int; a missing or non-numeric value
    counts as 0 rather than raising (the budget-summing equivalent of JS
    ``parseInt(x, 10) || 0`` for the whole-cent strings the backend sends —
    note ``int()`` rejects partials like ``"100.5"``, which never occur here)."""
    # ponytail: cents strings are always whole integers; non-numeric → 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class DelegationAPI(BasePaymentsAPI):
    """API for managing enrolled payment methods and delegations."""

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "DelegationAPI":
        """Get an instance of the DelegationAPI class."""
        return cls(options)

    def list_payment_methods(
        self,
        provider: Optional[DelegationProvider] = None,
        accessible: bool = False,
    ) -> List[PaymentMethodSummary]:
        """
        List the user's enrolled payment methods for card delegation.

        Args:
            provider: When set, return only methods backed by this provider
                ('stripe' | 'braintree' | 'visa' | 'erc4337'). Forwarded as a
                ``?provider=`` query string. Omit to return methods from every
                provider (default).
            accessible: When True, return only methods accessible to the
                requesting API key (``?accessible=true``). Defaults to False
                (all of the user's methods).

        Returns:
            A list of payment method summaries

        Raises:
            PaymentsError: If the request fails
        """
        url = f"{self.environment.backend}/api/v1/payment-methods"
        options = self.get_backend_http_options("GET")
        params: Dict[str, Any] = {}
        if provider:
            params["provider"] = provider
        if accessible:
            params["accessible"] = "true"
        params = params or None

        try:
            response = requests.get(url, params=params, **options)
            response.raise_for_status()
            data = response.json()
            return [PaymentMethodSummary.model_validate(pm) for pm in data]
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to list payment methods"
            ) from err
        except Exception as err:
            # Include the exception type so backend-shape mismatches
            # (pydantic ValidationError) don't get masked as "network
            # error" — the full ValidationError stringifies to the
            # field path + offending value + reason, which is exactly
            # what's needed to diagnose backend contract drift.
            raise PaymentsError.internal(
                f"Failed to list payment methods: {type(err).__name__}: {err}"
            ) from err

    def create_delegation(
        self, payload: CreateDelegationPayload
    ) -> CreateDelegationResponse:
        """
        Create a new delegation for any supported provider (stripe, braintree,
        visa, or erc4337).

        Note: Visa delegations require a per-delegation device-binding ceremony
        (FIDO/passkey + assuranceData) that must be performed in the browser
        via the Nevermined webapp. The SDK can list and consume an already-
        created Visa delegation but cannot create one programmatically.

        Args:
            payload: The delegation creation parameters

        Returns:
            The created delegation ID (and token for card delegations)

        Raises:
            PaymentsError: If the request fails. ``error.code`` carries the
                backend NVMException code (e.g. ``'BCK.VISA.0014'``) when the
                response was a structured failure.
        """
        url = f"{self.environment.backend}/api/v1/delegation/create"
        body = payload.model_dump(exclude_none=True)
        options = self.get_backend_http_options("POST", body)

        try:
            response = requests.post(url, **options)
            response.raise_for_status()
            return CreateDelegationResponse.model_validate(response.json())
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to create delegation"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while creating delegation: {str(err)}"
            ) from err

    def list_delegations(self, accessible: bool = False) -> DelegationListResponse:
        """
        List the user's existing delegations.

        The backend returns a paginated envelope
        (``{delegations, totalResults, page, offset}``); a backend that has
        not yet shipped the envelope returns a bare array, which is wrapped so
        the return type is stable across the deployment window.

        Args:
            accessible: When True, return only usable delegations (active,
                non-expired, with budget) accessible to the requesting API key
                (``?accessible=true``). Defaults to False (all delegations).

        Returns:
            A :class:`DelegationListResponse` paginated envelope.

        Raises:
            PaymentsError: If the request fails
        """
        url = f"{self.environment.backend}/api/v1/delegation"
        options = self.get_backend_http_options("GET")
        params = {"accessible": "true"} if accessible else None

        try:
            response = requests.get(url, params=params, **options)
            response.raise_for_status()
            data = response.json()
            if isinstance(data, list):
                # ponytail: pre-envelope backend; wrap the bare array
                return DelegationListResponse(
                    delegations=[DelegationSummary.model_validate(d) for d in data],
                    total_results=len(data),
                    page=1,
                    offset=0,
                )
            return DelegationListResponse.model_validate(data)
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to list delegations"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Failed to list delegations: {type(err).__name__}: {err}"
            ) from err

    def get_purchasing_power(self) -> PurchasingPower:
        """
        Get the agent's purchasing power: accessible cards, active delegations,
        and their combined remaining budget. Mirrors the TS
        ``DelegationAPI.getPurchasingPower``.

        Returns:
            A :class:`PurchasingPower` summary.

        Raises:
            PaymentsError: If either underlying request fails
        """
        cards = self.list_payment_methods(accessible=True)
        delegations = self.list_delegations(accessible=True).delegations
        # Label with the first delegation's currency and total only THAT
        # currency's budget — summing mixed currencies under one label is
        # meaningless. The TS SDK sums every delegation under the first label;
        # in practice every delegation is USD, so this matches it there and is
        # safer when it does not (a currency-less entry counts toward the label).
        currency = next((d.currency for d in delegations if d.currency), "usd")
        total = sum(
            _parse_cents(d.remaining_budget_cents)
            for d in delegations
            if not d.currency or d.currency == currency
        )
        return PurchasingPower(
            cards=cards,
            delegations=delegations,
            total_remaining_budget_cents=total,
            currency=currency,
        )

    def update_payment_method(
        self, payment_method_id: str, dto: UpdatePaymentMethodDto
    ) -> PaymentMethodSummary:
        """
        Update a payment method's alias and/or allowed API keys.

        Only the fields set on ``dto`` are sent: pass ``alias`` to rename,
        ``allowed_api_key_ids`` (a list) to replace the allow-list, or an
        explicit ``allowed_api_key_ids=None`` to clear it. Mirrors the TS
        ``DelegationAPI.updatePaymentMethod``.

        Args:
            payment_method_id: The payment method id to update.
            dto: The fields to change.

        Returns:
            The updated payment method summary.

        Raises:
            PaymentsError: If the request fails
        """
        url = f"{self.environment.backend}/api/v1/payment-methods/{payment_method_id}"
        body = dto.model_dump(by_alias=True, exclude_unset=True)
        options = self.get_backend_http_options("PATCH", body)

        try:
            response = requests.patch(url, **options)
            response.raise_for_status()
            return PaymentMethodSummary.model_validate(response.json())
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to update payment method"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Failed to update payment method: {type(err).__name__}: {err}"
            ) from err
