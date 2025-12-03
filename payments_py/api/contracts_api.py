"""
Contracts API for accessing contract addresses from the deployment info endpoint.
"""

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
    erc2771_forwarder: str = Field(alias="ERC2771Forwarder")
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

            # Info endpoint doesn't require authentication
            response = requests.get(info_url, verify=False)
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

    @property
    def contracts(self) -> Contracts:
        """
        Get contract addresses as a Contracts model with snake_case properties.

        Returns:
            Contracts model with all contract addresses accessible via snake_case properties

        Example::
            payments = Payments(PaymentOptions(...))
            template_address = payments.contracts.pay_as_you_go_template
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
