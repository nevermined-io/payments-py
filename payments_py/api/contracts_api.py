"""
Contracts API for accessing contract addresses from the deployment info endpoint.
"""

import warnings
from typing import Optional, Dict
from pydantic import BaseModel, Field, ConfigDict
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import API_URL_INFO
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
import requests


class DeploymentInfo(BaseModel):
    """
    Deployment information including contract addresses.
    """

    model_config = ConfigDict(populate_by_name=True)

    version: Optional[str] = None
    contracts: Dict[str, str]


class Contracts(BaseModel):
    """
    Contract addresses accessible via snake_case properties.
    """

    access_manager: str = Field(alias="AccessManager")
    agreements_store: str = Field(alias="AgreementsStore")
    assets_registry: str = Field(alias="AssetsRegistry")
    distribute_payments_condition: str = Field(alias="DistributePaymentsCondition")
    fiat_payment_template: str = Field(alias="FiatPaymentTemplate")
    fiat_settlement_condition: str = Field(alias="FiatSettlementCondition")
    fixed_payment_template: str = Field(alias="FixedPaymentTemplate")
    linear_pricing: str = Field(alias="LinearPricing")
    lock_payment_condition: str = Field(alias="LockPaymentCondition")
    nft1155_credits: str = Field(alias="NFT1155Credits")
    nft1155_expirable_credits: str = Field(alias="NFT1155ExpirableCredits")
    nft1155_expirable_credits_v2: str = Field(alias="NFT1155ExpirableCreditsV2")
    nvm_config: str = Field(alias="NVMConfig")
    one_time_creator_hook: str = Field(alias="OneTimeCreatorHook")
    pay_as_you_go_template: str = Field(alias="PayAsYouGoTemplate")
    payments_vault: str = Field(alias="PaymentsVault")
    protocol_standard_fees: str = Field(alias="ProtocolStandardFees")
    token_utils: str = Field(alias="TokenUtils")
    transfer_credits_condition: str = Field(alias="TransferCreditsCondition")

    model_config = ConfigDict(populate_by_name=True)


# snake_case address field names on the Contracts model — the back-compat
# surface ContractsAPI.__getattr__ forwards (see below).
_ADDRESS_FIELDS = frozenset(Contracts.model_fields)


class ContractsAPI(BasePaymentsAPI):
    """
    API for accessing contract addresses from the deployment info endpoint.
    """

    def __init__(self, options: PaymentOptions):
        """
        Initialize the Contracts API.

        Args:
            options: The options to initialize the payments class
        """
        super().__init__(options)
        self._deployment_info: Optional[DeploymentInfo] = None
        self._contracts: Optional[Contracts] = None

    def __getattr__(self, name: str):
        """Back-compat: the snake_case address attributes used to live on
        ``payments.contracts`` (the :class:`Contracts` model). ``payments.contracts``
        is now this API, so forward those names to the model to keep the
        previously-documented access working, with a deprecation nudge toward
        ``get_contract_address`` / ``.contracts``.

        Guarded to the known address field names so typos and ``_private`` /
        dunder lookups still raise ``AttributeError`` (and cannot recurse into
        the network-fetching ``contracts`` property).
        """
        if name in _ADDRESS_FIELDS:
            warnings.warn(
                "Accessing contract addresses on payments.contracts directly "
                "(payments.contracts.%s) is deprecated; use "
                "payments.contracts.get_contract_address(...) or "
                "payments.contracts.contracts.%s" % (name, name),
                DeprecationWarning,
                stacklevel=2,
            )
            return getattr(self.contracts, name)
        raise AttributeError(
            f"{type(self).__name__!r} object has no attribute {name!r}"
        )

    def get_deployment_info(self) -> DeploymentInfo:
        """
        Get deployment information including contract addresses from the API info endpoint.
        Results are cached to avoid repeated API calls.

        Returns:
            DeploymentInfo containing deployment information with contract addresses

        Raises:
            PaymentsError: If the request fails
        """
        if self._deployment_info is not None:
            return self._deployment_info

        try:
            backend_url = self.environment.backend
            info_url = f"{backend_url}{API_URL_INFO}"

            # Info endpoint doesn't require authentication, but it still
            # carries the API version pin like every other backend call.
            response = requests.get(info_url, **self.get_public_http_options("GET"))
            response.raise_for_status()

            info_data = response.json()
            deployment_data = info_data.get("deployment", {})

            if not deployment_data:
                raise PaymentsError.internal(
                    "Deployment info not found in API response"
                )

            self._deployment_info = DeploymentInfo(**deployment_data)
            self._contracts = Contracts(**deployment_data["contracts"])

            return self._deployment_info
        except requests.RequestException as e:
            raise PaymentsError.internal(
                f"Failed to fetch deployment info: {str(e)}"
            ) from e
        except Exception as e:
            raise PaymentsError.internal(
                f"Failed to parse deployment info: {str(e)}"
            ) from e

    def get_contract_address(self, contract_name: str) -> str:
        """
        Get a contract address by its deployment name (e.g.
        ``"PayAsYouGoTemplate"``). Mirrors the TS
        ``ContractsAPI.getContractAddress``.

        Args:
            contract_name: The contract's deployment key.

        Returns:
            The contract address.

        Raises:
            PaymentsError: If the name is not present in the deployment info.
        """
        info = self.get_deployment_info()
        address = info.contracts.get(contract_name)
        if not address:
            raise PaymentsError.internal(
                f"Contract address not found for {contract_name}"
            )
        return address

    def get_pay_as_you_go_template_address(self) -> str:
        """Convenience accessor for the ``PayAsYouGoTemplate`` address. Mirrors
        the TS ``ContractsAPI.getPayAsYouGoTemplateAddress``."""
        return self.get_contract_address("PayAsYouGoTemplate")

    @property
    def contracts(self) -> Contracts:
        """
        Get contract addresses as a Contracts model with snake_case properties.

        Returns:
            Contracts model with all contract addresses accessible via snake_case properties

        Example::
            payments = Payments(PaymentOptions(...))
            template_address = payments.contracts.contracts.pay_as_you_go_template
        """
        if self._contracts is None:
            self.get_deployment_info()
        return self._contracts

    @property
    def deployment(self) -> DeploymentInfo:
        """
        Get deployment information.

        Returns:
            DeploymentInfo containing version, chain_id, and contracts
        """
        if self._deployment_info is None:
            self.get_deployment_info()
        return self._deployment_info
