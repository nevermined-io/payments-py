"""
The PlansAPI class provides methods to register and interact with payment plans on Nevermined.
"""

import requests
from typing import Dict, Any, Optional, Literal
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    PaymentOptions,
    PlanMetadata,
    PlanPriceConfig,
    PlanCreditsConfig,
    PlanRedemptionType,
    PaginationOptions,
    PlanBalance,
)
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import (
    API_URL_REGISTER_PLAN,
    API_URL_GET_PLAN,
    API_URL_PLAN_BALANCE,
    API_URL_ORDER_PLAN,
    API_URL_MINT_PLAN,
    API_URL_MINT_EXPIRABLE_PLAN,
    API_URL_BURN_PLAN,
    API_URL_GET_PLAN_AGENTS,
    API_URL_STRIPE_CHECKOUT,
    API_URL_REDEEM_PLAN,
)
from payments_py.utils import get_random_big_int, is_ethereum_address
from payments_py import plans as plan_utils


class PlansAPI(BasePaymentsAPI):
    """
    The PlansAPI class provides methods to register and interact with payment plans on Nevermined.
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "PlansAPI":
        """
        Get a singleton instance of the PlansAPI class.

        Args:
            options: The options to initialize the payments class

        Returns:
            The instance of the PlansAPI class
        """
        return cls(options)

    def register_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
        nonce: Optional[int] = None,
        access_limit: Optional[
            Literal["credits", "time"]
        ] = None,  # 'credits' or 'time'
    ) -> Dict[str, str]:
        """
        Allows an AI Builder to create a Payment Plan on Nevermined in a flexible manner.
        A Nevermined Credits Plan limits access based on plan usage.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated with the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration
            nonce: Optional nonce for the transaction

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan

        Raises:
            PaymentsError: If registration fails
        """
        if access_limit and access_limit not in ["credits", "time"]:
            raise PaymentsError.validation(
                "Invalid access limit",
                "accessLimit must be either 'credits' or 'time'",
            )
        if not access_limit:
            access_limit = "time" if credits_config.duration_secs > 0 else "credits"

        if nonce is None:
            nonce = get_random_big_int()

        body = {
            "metadataAttributes": self.pydantic_to_dict(plan_metadata),
            "priceConfig": self.pydantic_to_dict(price_config),
            "creditsConfig": self.pydantic_to_dict(credits_config),
            "nonce": nonce,
            "isTrialPlan": getattr(plan_metadata, "is_trial_plan", False),
            "accessLimit": access_limit,
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REGISTER_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to register plan. {response.status_code} - {response.text}"
            )

        return response.json()

    def register_credits_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
    ) -> Dict[str, str]:
        """
        Allows an AI Builder to create a Payment Plan on Nevermined based on Credits.
        A Nevermined Credits Plan limits the access by the access/usage of the Plan.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated with the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan

        Raises:
            PaymentsError: If the credits configuration is invalid
        """

        if credits_config.min_amount > credits_config.max_amount:
            raise PaymentsError.validation(
                "The creditsConfig.minAmount can not be more than creditsConfig.maxAmount"
            )

        return self.register_plan(
            plan_metadata, price_config, credits_config, access_limit="credits"
        )

    def register_time_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
    ) -> Dict[str, str]:
        """
        Allows an AI Builder to create a Payment Plan on Nevermined limited by duration.
        A Nevermined Credits Plan limits the access by the access/usage of the Plan.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated with the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan

        Raises:
            PaymentsError: If the credits configuration is invalid
        """

        return self.register_plan(
            plan_metadata, price_config, credits_config, access_limit="time"
        )

    def register_credits_trial_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
    ) -> Dict[str, str]:
        """
        Allows an AI Builder to create a Trial Payment Plan on Nevermined based on Credits.
        A Nevermined Trial Plan allow subscribers of that plan to test the Agents associated to it.
        A Trial plan is a plan that only can be purchased once by a user.

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan
        """
        plan_metadata.is_trial_plan = True
        return self.register_credits_plan(plan_metadata, price_config, credits_config)

    def register_time_trial_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
    ) -> Dict[str, str]:
        """
        Allows an AI Builder to create a Trial Payment Plan on Nevermined limited by duration.
        A Nevermined Trial Plan allow subscribers of that plan to test the Agents associated to it.
        A Trial plan is a plan that only can be purchased once by a user.

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan
        """
        plan_metadata.is_trial_plan = True
        return self.register_time_plan(plan_metadata, price_config, credits_config)

    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        """
        Get the metadata for a given Plan identifier.

        Args:
            plan_id: The unique identifier of the plan

        Returns:
            The plan's metadata

        Raises:
            PaymentsError: If the plan is not found
        """
        url = f"{self.environment.backend}{API_URL_GET_PLAN.format(plan_id=plan_id)}"
        response = requests.get(url)
        if not response.ok:
            raise PaymentsError.validation(
                f"Plan not found. {response.status_code} - {response.text}"
            )
        return response.json()

    def get_plan_balance(
        self, plan_id: str, account_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the balance of a plan for a specific account.

        Args:
            plan_id: The unique identifier of the plan
            account_address: The account address to check balance for (defaults to current user)

        Returns:
            The plan balance information with properly typed fields (balance as int)

        Raises:
            PaymentsError: If unable to get plan balance
        """

        if not is_ethereum_address(account_address):
            account_address = self.get_account_address()

        url = f"{self.environment.backend}{API_URL_PLAN_BALANCE.format(plan_id=plan_id, holder_address=account_address)}"
        response = requests.get(
            url,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
        )
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to get plan balance. {response.status_code} - {response.text}"
            )

        # Parse and validate response using Pydantic model to ensure type conversion
        response_data = response.json()
        return PlanBalance(**response_data)

    def order_plan(self, plan_id: str) -> Dict[str, bool]:
        """
        Order a plan by its ID.

        Args:
            plan_id: The ID of the plan to order

        Returns:
            The result of the order operation

        Raises:
            PaymentsError: If unable to order the plan
        """
        options = self.get_backend_http_options("POST")
        url = f"{self.environment.backend}{API_URL_ORDER_PLAN}".format(plan_id=plan_id)

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to order plan. {response.status_code} - {response.text}"
            )
        return response.json()

    def mint_plan_credits(
        self, plan_id: str, credits_amount: int, credits_receiver: str
    ) -> Dict[str, Any]:
        """
        Mint credits for a plan.

        Args:
            plan_id: The unique identifier of the plan
            credits_amount: The amount of credits to mint
            credits_receiver: The address that will receive the credits

        Returns:
            The result of the mint operation

        Raises:
            PaymentsError: If unable to mint credits
        """
        body = {
            "planId": plan_id,
            "amount": credits_amount,
            "creditsReceiver": credits_receiver,
        }
        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_MINT_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to mint credits. {response.status_code} - {response.text}"
            )
        return response.json()

    def mint_plan_expirable(
        self,
        plan_id: str,
        credits_amount: int,
        credits_receiver: str,
        credits_duration: int = 0,
    ) -> Dict[str, Any]:
        """
        Mint expirable credits for a plan.

        Args:
            plan_id: The unique identifier of the plan
            credits_amount: The amount of credits to mint
            credits_receiver: The address that will receive the credits
            credits_duration: The duration of the credits in seconds

        Returns:
            The result of the mint operation

        Raises:
            PaymentsError: If unable to mint credits
        """
        body = {
            "planId": plan_id,
            "creditsAmount": credits_amount,
            "creditsReceiver": credits_receiver,
            "creditsDuration": credits_duration,
        }
        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_MINT_EXPIRABLE_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to mint expirable credits. {response.status_code} - {response.text}"
            )
        return response.json()

    def burn_credits(self, plan_id: str, credits_amount: str) -> Dict[str, Any]:
        """
        Burn credits from a plan.

        Args:
            plan_id: The unique identifier of the plan
            credits_amount: The amount of credits to burn

        Returns:
            The result of the burn operation

        Raises:
            PaymentsError: If unable to burn credits
        """
        body = {
            "planId": plan_id,
            "creditsAmount": credits_amount,
        }
        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_BURN_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to burn credits. {response.status_code} - {response.text}"
            )
        return response.json()

    def get_agents_associated_to_plan(
        self, plan_id: str, pagination: Optional[PaginationOptions] = None
    ) -> Dict[str, Any]:
        """
        Gets the list of agents that can be accessed with a plan.

        Args:
            plan_id: The unique identifier of the plan
            pagination: Optional pagination options to control the number of results returned

        Returns:
            The list of all different agents giving access to the plan

        Raises:
            PaymentsError: If the plan is not found
        """
        if pagination is None:
            pagination = PaginationOptions()

        url = f"{self.environment.backend}{API_URL_GET_PLAN_AGENTS.format(plan_id=plan_id)}"
        params = {
            "page": pagination.page,
            "offset": pagination.offset,
        }
        response = requests.get(url, params=params)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to get agents associated to plan. {response.status_code} - {response.text}"
            )
        return response.json()

    # ------------------------------------------------------------------
    # Static helper methods to build price/credits configurations
    # These mirror functions in payments_py/plans.py for ergonomic access as
    # Payments.plans.<method>(...)
    # ------------------------------------------------------------------

    # Expose duration constants for convenience
    ONE_DAY_DURATION: int = plan_utils.ONE_DAY_DURATION
    ONE_WEEK_DURATION: int = plan_utils.ONE_WEEK_DURATION
    ONE_MONTH_DURATION: int = plan_utils.ONE_MONTH_DURATION
    ONE_YEAR_DURATION: int = plan_utils.ONE_YEAR_DURATION

    # Price configuration builders -------------------------------------
    @staticmethod
    def get_fiat_price_config(amount: int, receiver: str) -> PlanPriceConfig:
        """Build a fiat price configuration."""
        return plan_utils.get_fiat_price_config(amount, receiver)

    @staticmethod
    def get_crypto_price_config(
        amount: int,
        receiver: str,
        token_address: str = "0x0000000000000000000000000000000000000000",
    ) -> PlanPriceConfig:
        """Build a crypto (native/ERC20) price configuration."""
        return plan_utils.get_crypto_price_config(amount, receiver, token_address)

    @staticmethod
    def get_erc20_price_config(
        amount: int, token_address: str, receiver: str
    ) -> PlanPriceConfig:
        """Build an ERC20 price configuration."""
        return plan_utils.get_erc20_price_config(amount, token_address, receiver)

    @staticmethod
    def get_free_price_config() -> PlanPriceConfig:
        """Build a free price configuration."""
        return plan_utils.get_free_price_config()

    @staticmethod
    def get_native_token_price_config(amount: int, receiver: str) -> PlanPriceConfig:
        """Build a native token price configuration."""
        return plan_utils.get_native_token_price_config(amount, receiver)

    # Credits configuration builders -----------------------------------
    @staticmethod
    def get_expirable_duration_config(duration_of_plan: int) -> PlanCreditsConfig:
        """Build an expirable duration credits configuration."""
        return plan_utils.get_expirable_duration_config(duration_of_plan)

    @staticmethod
    def get_non_expirable_duration_config() -> PlanCreditsConfig:
        """Build a non-expirable duration credits configuration."""
        return plan_utils.get_non_expirable_duration_config()

    @staticmethod
    def get_fixed_credits_config(
        credits_granted: int, credits_per_request: int = 1
    ) -> PlanCreditsConfig:
        """Build a fixed credits configuration."""
        return plan_utils.get_fixed_credits_config(credits_granted, credits_per_request)

    @staticmethod
    def get_dynamic_credits_config(
        credits_granted: int,
        min_credits_per_request: int = 1,
        max_credits_per_request: int = 1,
    ) -> PlanCreditsConfig:
        """Build a dynamic credits configuration."""
        return plan_utils.get_dynamic_credits_config(
            credits_granted, min_credits_per_request, max_credits_per_request
        )

    @staticmethod
    def set_redemption_type(
        credits_config: PlanCreditsConfig, redemption_type: PlanRedemptionType
    ) -> PlanCreditsConfig:
        """Set redemption type on a credits configuration (returns new object)."""
        return plan_utils.set_redemption_type(credits_config, redemption_type)

    @staticmethod
    def set_proof_required(
        credits_config: PlanCreditsConfig, proof_required: bool = True
    ) -> PlanCreditsConfig:
        """Set proof requirement on a credits configuration (returns new object)."""
        return plan_utils.set_proof_required(credits_config, proof_required)

    def order_fiat_plan(self, plan_id: str) -> Dict[str, Any]:
        """
        Order a fiat plan using Stripe checkout.

        Args:
            plan_id: The unique identifier of the plan

        Returns:
            The Stripe checkout result

        Raises:
            PaymentsError: If unable to order the fiat plan
        """
        body = {"planId": plan_id, "sessionType": "embedded"}
        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_STRIPE_CHECKOUT}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to order fiat plan. {response.status_code} - {response.text}"
            )
        return response.json()

    def redeem_credits(
        self,
        agent_request_id: str,
        plan_id: str,
        redeem_from: str,
        credits_amount_to_redeem: str,
    ) -> Dict[str, Any]:
        """
        Redeem credits from a plan for a specific agent request.

        Args:
            agent_request_id: The unique identifier of the agent request
            plan_id: The unique identifier of the plan
            redeem_from: The address to redeem credits from
            credits_amount_to_redeem: The amount of credits to redeem

        Returns:
            The result of the redeem operation

        Raises:
            PaymentsError: If unable to redeem credits
        """
        body = {
            "agentRequestId": agent_request_id,
            "planId": plan_id,
            "redeemFrom": redeem_from,
            "amount": credits_amount_to_redeem,
        }
        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REDEEM_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to redeem credits. {response.status_code} - {response.text}"
            )
        return response.json()
