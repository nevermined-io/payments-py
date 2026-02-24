"""
Delegation API for managing card-delegation payment methods.

Provides access to the user's enrolled Stripe payment methods
for use with the nvm:card-delegation x402 scheme.
"""

import requests
from typing import List
from pydantic import BaseModel, ConfigDict, Field
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.base_payments import BasePaymentsAPI


class PaymentMethodSummary(BaseModel):
    """
    Summary of a user's enrolled payment method.

    Attributes:
        id: Payment method ID (e.g., 'pm_...')
        brand: Card brand (e.g., 'visa', 'mastercard')
        last4: Last 4 digits of the card number
        exp_month: Card expiration month
        exp_year: Card expiration year
    """

    id: str
    brand: str
    last4: str
    exp_month: int = Field(alias="expMonth")
    exp_year: int = Field(alias="expYear")

    model_config = ConfigDict(
        populate_by_name=True,
        from_attributes=True,
    )


class DelegationAPI(BasePaymentsAPI):
    """API for listing enrolled payment methods for card delegation."""

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
        url = f"{self.environment.backend}/api/v1/delegation/payment-methods"
        options = self.get_backend_http_options("GET")

        try:
            response = requests.get(url, **options)
            response.raise_for_status()
            data = response.json()
            return [PaymentMethodSummary.model_validate(pm) for pm in data]
        except requests.HTTPError as err:
            try:
                error_message = response.json().get(
                    "message", "Failed to list payment methods"
                )
            except Exception:
                error_message = "Failed to list payment methods"
            raise PaymentsError.internal(
                f"{error_message} (HTTP {response.status_code})"
            ) from err
        except Exception as err:
            raise PaymentsError.internal(
                f"Network error while listing payment methods: {str(err)}"
            ) from err
