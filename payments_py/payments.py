"""
Main Payments class for the Nevermined Payments protocol.
"""
from typing import Optional, Dict, Any, List
import jwt
import requests
import json
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    PaymentOptions,
    PlanMetadata,
    PlanPriceConfig,
    PlanCreditsConfig,
    AgentMetadata,
    AgentAPIAttributes,
    PlanCreditsType
)
from payments_py.api.query_api import AIQueryApi
from payments_py.api.nvm_api import (
    API_URL_REGISTER_PLAN,
    API_URL_GET_PLAN,
    API_URL_PLAN_BALANCE,
    API_URL_ORDER_PLAN,
    API_URL_MINT_PLAN,
    API_URL_MINT_EXPIRABLE_PLAN,
    API_URL_BURN_PLAN,
    API_URL_REGISTER_AGENT,
    API_URL_GET_AGENT,
    API_URL_SEARCH_AGENTS,
    API_URL_ADD_PLAN_AGENT,
    API_URL_REMOVE_PLAN_AGENT
)
from payments_py.environments import get_environment
from payments_py.common.helper import get_random_big_int, dict_keys_to_camel
from enum import Enum

class Payments:
    """
    Main class for interacting with the Nevermined Payments protocol.
    """
    query: AIQueryApi
    return_url: str
    environment: str
    app_id: Optional[str]
    version: Optional[str]
    account_address: Optional[str]
    nvm_api_key: Optional[str]
    is_browser_instance: bool

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> 'Payments':
        """
        Get an instance of the payments class.
        
        Args:
            options: The options to initialize the payments class
            
        Returns:
            An instance of Payments
            
        Raises:
            PaymentsError: If nvm_api_key is not provided
        """
        if not options.return_url:
            raise PaymentsError("return_url is required")
        return cls(options)

    def __init__(self, options: PaymentOptions | dict, is_browser_instance: bool = False):
        """
        Initialize the Payments class.
        Args:
            options: The initialization options (PaymentOptions or dict)
            is_browser_instance: Whether this is a browser instance (default False)
        """
        if isinstance(options, dict):
            options = PaymentOptions(**options)
        self.nvm_api_key = options.nvm_api_key
        self.return_url = options.return_url or ''
        self.environment = get_environment(options.environment)
        self.app_id = options.app_id
        self.version = options.version
        self.is_browser_instance = is_browser_instance
        self.query = None
        self._parse_nvm_api_key()
        self._initialize_api()

    def _parse_nvm_api_key(self) -> None:
        """
        Parse the NVM API Key to get the account address.
        
        Raises:
            PaymentsError: If the API key is invalid
        """
        try:
            decoded_jwt = jwt.decode(
                self.nvm_api_key,
                options={"verify_signature": False}
            )
            self.account_address = decoded_jwt.get("sub")
        except Exception as e:
            raise PaymentsError(f"Invalid NVM API Key: {str(e)}")

    def _initialize_api(self) -> None:
        """
        Initialize the AI Query Protocol API.
        """
        from payments_py.api.nvm_api import BackendApiOptions
        self.query = AIQueryApi(
            BackendApiOptions(
                backend_host=self.environment.backend,
                api_key=self.nvm_api_key,
                proxy_host=self.environment.proxy,
                headers={}
            )
        )

    @property
    def is_logged_in(self) -> bool:
        """
        Check if a user is logged in.
        
        Returns:
            True if the user is logged in
        """
        return bool(self.nvm_api_key)

    def get_backend_http_options(self, body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Get HTTP options for backend requests (headers and body only).
        Args:
            body: Optional request body
        Returns:
            The HTTP options (headers and body)
        """
        options = {
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.nvm_api_key}",
            }
        }
        if body:
            options["data"] = json.dumps(body)
        return options

    def pydantic_to_dict(self, obj):
        """
        Recursively convert Pydantic models and Enums to serializable dicts.
        """
        if isinstance(obj, list):
            return [self.pydantic_to_dict(i) for i in obj]
        elif isinstance(obj, dict):
            return {k: self.pydantic_to_dict(v) for k, v in obj.items() if v is not None}
        elif hasattr(obj, 'dict'):
            return self.pydantic_to_dict(obj.dict(exclude_none=True))
        elif isinstance(obj, Enum):
            return obj.value
        else:
            return obj

    def register_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
        nonce: Optional[int] = None
    ) -> Dict[str, str]:
        """
        Allows an AI Builder to create a Payment Plan on Nevermined in a flexible manner.
        A Nevermined Credits Plan limits access based on plan usage.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated with the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration
            nonce: Optional nonce for the transaction

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan.

        Raises:
            PaymentsError: If registration fails

        Example:
            >>> crypto_price_config = get_native_token_price_config(100, builder_address)
            >>> credits_config = get_fixed_credits_config(100)
            >>> result = payments.register_plan(plan_metadata, crypto_price_config, credits_config)
            >>> plan_id = result["planId"]
        """
        nonce = nonce or get_random_big_int()
        body = {
            "metadataAttributes": self.pydantic_to_dict(plan_metadata),
            "priceConfig": self.pydantic_to_dict(price_config),
            "creditsConfig": self.pydantic_to_dict(credits_config),
            "nonce": nonce
        }
        body = dict_keys_to_camel(body)
        response = requests.post(
            f"{self.environment.backend}{API_URL_REGISTER_PLAN}",
            **self.get_backend_http_options(body)
        ).json()
        if not response:
            raise PaymentsError("Failed to register plan")
        if 'plan_id' in response:
            response['planId'] = response.pop('plan_id')
        return response

    def register_credits_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig
    ) -> Dict[str, str]:
        """
        It allows to an AI Builder to create a Payment Plan on Nevermined based on Credits.
        A Nevermined Credits Plan limits the access by the access/usage of the Plan.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated with the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan.

        Raises:
            PaymentsError: If the credits type is invalid or min amount is greater than max amount

        Example:
            >>> crypto_price_config = get_native_token_price_config(100, builder_address)
            >>> credits_config = get_fixed_credits_config(100)
            >>> result = payments.register_credits_plan(plan_metadata, crypto_price_config, credits_config)
            >>> plan_id = result["planId"]
        """
        if credits_config.credits_type not in [PlanCreditsType.FIXED, PlanCreditsType.DYNAMIC]:
            raise PaymentsError("The creditsConfig.creditsType must be FIXED or DYNAMIC")
            
        if credits_config.min_amount > credits_config.max_amount:
            raise PaymentsError("The creditsConfig.minAmount can not be more than creditsConfig.maxAmount")
            
        return self.register_plan(plan_metadata, price_config, credits_config)

    def register_time_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig
    ) -> Dict[str, str]:
        """
        It allows to an AI Builder to create a Payment Plan on Nevermined limited by duration.
        A Nevermined Credits Plan limits the access by the access/usage of the Plan.
        With them, AI Builders control the number of requests that can be made to an agent or service.
        Every time a user accesses any resource associated with the Payment Plan, the usage consumes from a capped amount of credits.
        When the user consumes all the credits, the plan automatically expires and the user needs to top up to continue using the service.

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan.

        Raises:
            PaymentsError: If the credits type is not EXPIRABLE

        Example:
            >>> crypto_price_config = get_native_token_price_config(100, builder_address)
            >>> one_day_duration_plan = get_expirable_duration_config(ONE_DAY_DURATION)
            >>> result = payments.register_time_plan(plan_metadata, crypto_price_config, one_day_duration_plan)
            >>> plan_id = result["planId"]
        """
        if credits_config.credits_type != PlanCreditsType.EXPIRABLE:
            raise PaymentsError("The creditsConfig.creditsType must be EXPIRABLE")
            
        return self.register_plan(plan_metadata, price_config, credits_config)

    def register_credits_trial_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig
    ) -> Dict[str, str]:
        """
        It allows to an AI Builder to create a Trial Payment Plan on Nevermined limited by duration.
        A Nevermined Trial Plan allow subscribers of that plan to test the Agents associated to it.
        A Trial plan is a plan that only can be purchased once by a user.
        Trial plans, as regular plans, can be limited by duration (i.e 1 week of usage) or by credits (i.e 100 credits to use the agent).

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan.

        Example:
            >>> free_price_config = get_free_price_config()
            >>> one_day_duration_plan = get_expirable_duration_config(ONE_DAY_DURATION)
            >>> result = payments.register_credits_trial_plan(plan_metadata, free_price_config, one_day_duration_plan)
            >>> plan_id = result["planId"]
        """
        plan_metadata.is_trial_plan = True
        return self.register_credits_plan(plan_metadata, price_config, credits_config)

    def register_time_trial_plan(
        self,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig
    ) -> Dict[str, str]:
        """
        It allows to an AI Builder to create a Trial Payment Plan on Nevermined limited by duration.
        A Nevermined Trial Plan allow subscribers of that plan to test the Agents associated to it.
        A Trial plan is a plan that only can be purchased once by a user.
        Trial plans, as regular plans, can be limited by duration (i.e 1 week of usage) or by credits (i.e 100 credits to use the agent).

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/create-plan

        Args:
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            The unique identifier of the plan (Plan ID) of the newly created plan.

        Example:
            >>> free_price_config = get_free_price_config()
            >>> one_day_duration_plan = get_expirable_duration_config(ONE_DAY_DURATION)
            >>> result = payments.register_time_trial_plan(plan_metadata, free_price_config, one_day_duration_plan)
            >>> plan_id = result["planId"]
        """
        plan_metadata.is_trial_plan = True
        return self.register_time_plan(plan_metadata, price_config, credits_config)

    def register_agent(
        self,
        agent_metadata: AgentMetadata,
        agent_api: AgentAPIAttributes,
        payment_plans: List[str]
    ) -> Dict[str, str]:
        """
        It registers a new AI Agent on Nevermined.
        The agent must be associated to one or multiple Payment Plans. Users that are subscribers of a payment plan can access the agent.
        Depending on the Payment Plan and the configuration of the agent, the usage of the agent/service will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/register-agent

        Args:
            agent_metadata: The agent metadata
            agent_api: The agent API attributes
            payment_plans: The list of payment plans giving access to the agent

        Returns:
            The unique identifier of the newly created agent (Agent Id)

        Example:
            >>> agent_metadata = {"name": "My AI Payments Agent", "tags": ["test"]}
            >>> agent_api = {"endpoints": [{"POST": "https://example.com/api/v1/agents/(.*)/tasks"}]}
            >>> payment_plans = [plan_id]
            >>> result = payments.register_agent(agent_metadata, agent_api, payment_plans)
            >>> agent_id = result["agentId"]
        """
        body = {
            "metadataAttributes": self.pydantic_to_dict(agent_metadata),
            "agentApiAttributes": self.pydantic_to_dict(agent_api),
            "plans": payment_plans
        }
        body = dict_keys_to_camel(body)
        response = requests.post(
            f"{self.environment.backend}{API_URL_REGISTER_AGENT}",
            **self.get_backend_http_options(body)
        ).json()
        if not response:
            raise PaymentsError("Failed to register agent")
        if 'agent_id' in response:
            response['agentId'] = response.pop('agent_id')
        return response

    def register_agent_and_plan(
        self,
        agent_metadata: AgentMetadata,
        agent_api: AgentAPIAttributes,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig
    ) -> Dict[str, str]:
        """
        It registers a new AI Agent and a Payment Plan associated to this new agent.
        Depending on the Payment Plan and the configuration of the agent, the usage of the agent/service will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

        .. seealso:: https://docs.nevermined.app/docs/tutorials/builders/register-agent

        Args:
            agent_metadata: The agent metadata
            agent_api: The agent API attributes
            plan_metadata: The plan metadata
            price_config: The price configuration
            credits_config: The credits configuration

        Returns:
            The unique identifier of the newly created agent (agentId) and plan (planId)

        Example:
            >>> agent_metadata = {"name": "My AI Payments Agent", "tags": ["test"]}
            >>> agent_api = {"endpoints": [{"POST": "https://example.com/api/v1/agents/(.*)/tasks"}]}
            >>> crypto_price_config = get_native_token_price_config(100, builder_address)
            >>> one_day_duration_plan = get_expirable_duration_config(ONE_DAY_DURATION)
            >>> result = payments.register_agent_and_plan(
            ...     agent_metadata,
            ...     agent_api,
            ...     crypto_price_config,
            ...     one_day_duration_plan
            ... )
            >>> agent_id = result["agentId"]
            >>> plan_id = result["planId"]
        """
        plan_result = self.register_plan(plan_metadata, price_config, credits_config)
        agent_result = self.register_agent(agent_metadata, agent_api, [plan_result["planId"]])
        return {
            "agentId": agent_result["agentId"],
            "planId": plan_result["planId"]
        }

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """
        Get the metadata (aka Decentralized Document or DDO) for a given Agent identifier (agentId).
        
        Args:
            agent_id: The unique identifier of the agent

        Returns:
            The metadata (aka Decentralized Document or DDO) for the given Agent identifier (agentId)
            
        Raises:
            PaymentsError: If the agent is not found
        """
        url = API_URL_GET_AGENT.replace('{agent_id}', agent_id)
        response = requests.get(
            f"{self.environment.backend}{url}",
            headers={"Accept": "application/json", "Content-Type": "application/json"}
        ).json()
        
        if not response:
            raise PaymentsError(f"Agent not found. {response.statusText} - {response.text}")
            
        return response
    
    def get_plan(self, plan_id: str) -> Dict[str, Any]:
        """
        Get the metadata (aka Decentralized Document or DDO) for a given Plan identifier (planId).
        
        Args:
            plan_id: The unique identifier of the plan
            
        Returns:
            The metadata (aka Decentralized Document or DDO) for the given Plan identifier (planId)
            
        Raises:
            PaymentsError: If the plan is not found
        """
        url = API_URL_GET_PLAN.replace('{plan_id}', plan_id)
        response = requests.get(
            f"{self.environment.backend}{url}",
            headers={"Accept": "application/json", "Content-Type": "application/json"}
        ).json()
        
        if not response:
            raise PaymentsError(f"Plan not found. {response.statusText} - {response.text}")
            
        return response

    def get_plan_balance(self, plan_id: str, account_address: Optional[str] = None) -> Dict[str, Any]:
        """
        Get the balance of an account for a Payment Plan.
        
        Args:
            plan_id: The identifier of the Payment Plan
            account_address: The address of the account to get the balance.

        Returns:
            The balance of the account for the given Payment Plan
            
        Raises:
            PaymentsError: If unable to get balance
        """
        url = API_URL_PLAN_BALANCE.replace('{plan_id}', plan_id).replace('{holder_address}', account_address or self.account_address)
        response = requests.get(
            f"{self.environment.backend}{url}",
            headers={"Accept": "application/json", "Content-Type": "application/json"}
        ).json()
        
        if not response:
            raise PaymentsError(f"Plan balance not found. {response.statusText} - {response.text}")
            
        return response

    def order_plan(self, plan_did: str) -> Dict[str, bool]:
        """
        Orders a Payment Plan. The user needs to have enough balance in the token selected by the owner of the Payment Plan.
        
        Args:
            plan_did: The identifier of the Payment Plan
            
        Returns:
            A promise that resolves indicating if the operation was successful.
            
        Raises:
            PaymentsError: If unable to order plan
        """
        url = API_URL_ORDER_PLAN.replace('{plan_id}', plan_did)
        response = requests.post(
            f"{self.environment.backend}{url}",
            **self.get_backend_http_options()
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to order plan. {response.statusText} - {response.text}")
            
        return response

    def mint_plan_credits(self, plan_id: str, credits_amount: int, credits_receiver: str) -> Dict[str, Any]:
        """
        Mint credits for a given Payment Plan and transfer them to a receiver.
        
        Args:
            plan_id: The identifier of the Payment Plan
            credits_amount: The number of credits to mint
            credits_receiver: The address of the receiver where the credits will be transferred

        Returns:
            A promise that resolves indicating if the operation was successful.
            
        Raises:
            PaymentsError: If unable to mint credits
        """
        body = {
            "planId": plan_id,
            "amount": credits_amount,
            "creditsReceiver": credits_receiver
        }
        body = dict_keys_to_camel(body)
        response = requests.post(
            f"{self.environment.backend}{API_URL_MINT_PLAN}",
            **self.get_backend_http_options(self.pydantic_to_dict(body))
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to mint plan credits.")
        
        return response

    def mint_plan_expirable(self, plan_id: str, credits_amount: int, credits_receiver: str, credits_duration: int = 0) -> Dict[str, Any]:
        """
        Mint credits for a given Payment Plan and transfer them to a receiver.
        
        Args:
            plan_id: The identifier of the Payment Plan
            credits_amount: The number of credits to mint
            credits_receiver: The address of the receiver where the credits will be transferred
            credits_duration: The duration of the credits in seconds
            
        Returns:
            A promise that resolves indicating if the operation was successful.
            
        Raises:
            PaymentsError: If unable to mint expirable credits
        """
        body = {
            "planId": plan_id,
            "amount": credits_amount,
            "creditsReceiver": credits_receiver,
            "duration": credits_duration
        }
        body = dict_keys_to_camel(body)
        response = requests.post(
            f"{self.environment.backend}{API_URL_MINT_EXPIRABLE_PLAN}",
            **self.get_backend_http_options(self.pydantic_to_dict(body))
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to mint expirable credits.")
        
        return response

    def burn_credits(self, plan_id: str, credits_amount: str) -> Dict[str, Any]:
        """
        Burn credits for a given Payment Plan.

        This method is only can be called by the owner of the Payment Plan.
        
        Args:
            plan_id: The identifier of the Payment Plan
            credits_amount: The number of credits to burn

        Returns:
            A promise that resolves indicating if the operation was successful.
            
        Raises:
            PaymentsError: If unable to burn credits
        """
        body = {
            "planId": plan_id,
            "creditsAmountToBurn": credits_amount
        }
        body = dict_keys_to_camel(body)
        response = requests.delete(
            f"{self.environment.backend}{API_URL_BURN_PLAN}",
            **self.get_backend_http_options(self.pydantic_to_dict(body))
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to burn credits.")
        
        return response
    
    def add_plan_to_agent(self, plan_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Add a Payment Plan to an AI Agent.

        This method is only can be called by the owner of the Payment Plan.

        Args:
            plan_id: The identifier of the Payment Plan
            agent_id: The identifier of the AI Agent

        Returns:
            A promise that resolves indicating if the operation was successful.
            
        Raises:
            PaymentsError: If unable to add plan to agent
        """
        url = API_URL_ADD_PLAN_AGENT.replace('{plan_id}', plan_id).replace('{agent_id}', agent_id)
        response = requests.post(
            f"{self.environment.backend}{url}",
            **self.get_backend_http_options()
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to add plan to agent.")
        
        return response
    
    def remove_plan_from_agent(self, plan_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Remove a Payment Plan from an AI Agent.
        After this operation, users having access to the Payment Plan will not longer be able to access the AI Agent.

        This method is only can be called by the owner of the Payment Plan.

        Args:
            plan_id: The identifier of the Payment Plan
            agent_id: The identifier of the AI Agent

        Returns:
            A promise that resolves indicating if the operation was successful.
            
        Raises:
            PaymentsError: If unable to remove plan from agent
        """
        url = API_URL_REMOVE_PLAN_AGENT.replace('{plan_id}', plan_id).replace('{agent_id}', agent_id)
        response = requests.delete(
            f"{self.environment.backend}{url}",
            **self.get_backend_http_options()
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to remove plan from agent.")
        
        return response
    
    def search_agents(self, text: str, page: int = 1, offset: int = 10) -> Dict[str, Any]:
        """
        Search for AI Agents based on a text query.
        
        Args:
            text: The text query to search for Payment Plans.
            page: The page number for pagination.
            offset: The number of items per page.

        Returns:
            A promise that resolves to the JSON response from the server.
            
        Raises:
            PaymentsError: If the search fails
            
        Example:
            >>> agents = payments.search_agents(text='test')
            >>> print(agents.agents)
        """
        url = API_URL_SEARCH_AGENTS
        response = requests.get(
            f"{self.environment.backend}{url}",
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            params={"text": text, "page": page, "offset": offset}
        ).json()
        
        if not response:
            raise PaymentsError(f"Unable to search agents. {response.statusText} - {response.text}")
        
        return response
    
    def connect(self):
        """
        Initiate the connect flow. Only allowed in browser context.
        """
        if self.is_browser_instance:
            raise PaymentsError("This method can only be used in a browser environment")
        raise NotImplementedError("Connect is not implemented in Python.")

    def init(self):
        """
        Initialize after login. Only allowed in browser context.
        """
        if self.is_browser_instance:
            raise PaymentsError("This method can only be used in a browser environment")
        raise NotImplementedError("Init is not implemented in Python.")

    def logout(self):
        """
        Logout the user. Only allowed in browser context.
        """
        if self.is_browser_instance:
            raise PaymentsError("This method can only be used in a browser environment")
        self.nvm_api_key = None


