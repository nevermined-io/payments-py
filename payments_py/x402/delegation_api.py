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
from payments_py.x402.types import CreateDelegationPayload, CreateDelegationResponse


class PaymentMethodSummary(BaseModel):
    """
    Summary of a user's enrolled payment method.

    Attributes:
        id: Payment method ID (Stripe 'pm_...', Braintree vault token, or
            Visa Agentic token id 'vat_...')
        type: Payment method type (e.g., 'card', 'paypal')
        brand: Card brand (e.g., 'visa', 'mastercard') or payment method type ('paypal', 'venmo')
        last4: Last 4 digits (cards) or email/username (PayPal/Venmo)
        exp_month: Expiration month (0 for non-card methods)
        exp_year: Expiration year (0 for non-card methods)
        provider: Payment provider ('stripe', 'braintree', or 'visa')
    """

    id: str
    type: Optional[str] = None
    brand: str
    last4: str
    exp_month: Optional[int] = Field(0, alias="expMonth")
    exp_year: Optional[int] = Field(0, alias="expYear")
    provider: Optional[str] = None

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class DelegationSummary(BaseModel):
    """
    Summary of an existing delegation (card or crypto).

    Attributes:
        id: Delegation UUID
        card_id: Associated PaymentMethod entity UUID
        spending_limit_cents: Maximum spending limit in cents
        spent_cents: Amount already spent in cents
        duration_secs: Duration of the delegation in seconds
        currency: Currency code (e.g., 'usd')
        status: Delegation status (e.g., 'active', 'expired')
        created_at: ISO 8601 creation timestamp
        expires_at: ISO 8601 expiration timestamp
    """

    id: str
    card_id: Optional[str] = Field(None, alias="cardId")
    spending_limit_cents: Optional[int] = Field(None, alias="spendingLimitCents")
    spent_cents: Optional[int] = Field(None, alias="spentCents")
    duration_secs: Optional[int] = Field(None, alias="durationSecs")
    currency: Optional[str] = None
    status: Optional[str] = None
    created_at: Optional[str] = Field(None, alias="createdAt")
    expires_at: Optional[str] = Field(None, alias="expiresAt")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class DelegationAPI(BasePaymentsAPI):
    """API for managing enrolled payment methods and delegations."""

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "DelegationAPI":
        """Get an instance of the DelegationAPI class."""
        return cls(options)

    def list_payment_methods(self) -> List[PaymentMethodSummary]:
        """
        List the user's enrolled payment methods for card delegation.

        Returns:
            A list of payment method summaries

        Raises:
            PaymentsError: If the request fails
        """
        url = f"{self.environment.backend}/api/v1/payment-methods"
        options = self.get_backend_http_options("GET")

        try:
            response = requests.get(url, **options)
            response.raise_for_status()
            data = response.json()
            return [PaymentMethodSummary.model_validate(pm) for pm in data]
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to list payment methods"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while listing payment methods: {str(err)}"
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
            if isinstance(err, PaymentsError):
                raise
            raise PaymentsError.internal(
                f"Network error while creating delegation: {str(err)}"
            ) from err

    def list_delegations(self) -> List[DelegationSummary]:
        """
        List the user's existing card delegations.

        Returns:
            A list of delegation summaries

        Raises:
            PaymentsError: If the request fails
        """
        url = f"{self.environment.backend}/api/v1/delegation"
        options = self.get_backend_http_options("GET")

        try:
            response = requests.get(url, **options)
            response.raise_for_status()
            data = response.json()
            return [DelegationSummary.model_validate(d) for d in data]
        except requests.HTTPError as err:
            raise PaymentsError.from_response(
                response, "Failed to list delegations"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while listing delegations: {str(err)}"
            ) from err
