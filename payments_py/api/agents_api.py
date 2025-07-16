"""
The AgentsAPI class provides methods to register and interact with AI Agents on Nevermined.
"""

import requests
from typing import Dict, Any, List, Optional
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    PaymentOptions,
    AgentMetadata,
    AgentAPIAttributes,
    PlanMetadata,
    PlanPriceConfig,
    PlanCreditsConfig,
    PaginationOptions,
)
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import (
    API_URL_REGISTER_AGENT,
    API_URL_GET_AGENT,
    API_URL_ADD_PLAN_AGENT,
    API_URL_REMOVE_PLAN_AGENT,
    API_URL_GET_AGENT_ACCESS_TOKEN,
    API_URL_REGISTER_AGENTS_AND_PLAN,
    API_URL_GET_AGENT_PLANS,
)


class AgentsAPI(BasePaymentsAPI):
    """
    The AgentsAPI class provides methods to register and interact with AI Agents on Nevermined.
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "AgentsAPI":
        """
        Get a singleton instance of the AgentsAPI class.

        Args:
            options: The options to initialize the payments class

        Returns:
            The instance of the AgentsAPI class
        """
        return cls(options)

    def register_agent(
        self,
        agent_metadata: AgentMetadata,
        agent_api: AgentAPIAttributes,
        payment_plans: List[str],
    ) -> Dict[str, str]:
        """
        Registers a new AI Agent on Nevermined.
        The agent must be associated to one or multiple Payment Plans. Users that are subscribers of a payment plan can query the agent.
        Depending on the Payment Plan and the configuration of the agent, the usage of the agent/service will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

        Args:
            agent_metadata: Agent metadata
            agent_api: Agent API attributes
            payment_plans: The list of payment plans giving access to the agent

        Returns:
            The unique identifier of the newly created agent (Agent Id)

        Raises:
            PaymentsError: If registration fails
        """
        body = {
            "metadataAttributes": agent_metadata,
            "agentApiAttributes": agent_api,
            "plans": payment_plans,
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REGISTER_AGENT}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError(
                f"Unable to register agent. {response.status_code} - {response.text}"
            )
        agent_data = response.json()
        return {"agentId": agent_data["agentId"]}

    def register_agent_and_plan(
        self,
        agent_metadata: AgentMetadata,
        agent_api: AgentAPIAttributes,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
    ) -> Dict[str, str]:
        """
        Registers a new AI Agent and a Payment Plan associated to this new agent.
        Depending on the Payment Plan and the configuration of the agent, the usage of the agent/service will consume credits.
        When the plan expires (because the time is over or the credits are consumed), the user needs to renew the plan to continue using the agent.

        Args:
            agent_metadata: Agent metadata
            agent_api: Agent API attributes
            plan_metadata: Plan metadata
            price_config: Plan price configuration
            credits_config: Plan credits configuration

        Returns:
            Dictionary containing agentId, planId, and txHash

        Raises:
            PaymentsError: If registration fails
        """
        body = {
            "plan": {
                "metadataAttributes": plan_metadata,
                "priceConfig": price_config,
                "creditsConfig": credits_config,
            },
            "agent": {
                "metadataAttributes": agent_metadata,
                "agentApiAttributes": agent_api,
            },
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REGISTER_AGENTS_AND_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError(
                f"Unable to register agent & plan. {response.status_code} - {response.text}"
            )
        result = response.json()
        return {
            "agentId": result["data"]["agentId"],
            "planId": result["data"]["planId"],
            "txHash": result["data"]["txHash"],
        }

    def get_agent(self, agent_id: str) -> Dict[str, Any]:
        """
        Gets the metadata for a given Agent identifier.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            The agent's metadata

        Raises:
            PaymentsError: If the agent is not found
        """
        url = f"{self.environment.backend}{API_URL_GET_AGENT.format(agent_id=agent_id)}"
        response = requests.get(url)
        if not response.ok:
            raise PaymentsError(
                f"Agent not found. {response.status_code} - {response.text}"
            )
        return response.json()

    def get_agent_plans(
        self, agent_id: str, pagination: Optional[PaginationOptions] = None
    ) -> Dict[str, Any]:
        """
        Gets the list of plans that can be ordered to get access to an agent.

        Args:
            agent_id: The unique identifier of the agent
            pagination: Optional pagination options to control the number of results returned

        Returns:
            The list of all different plans giving access to the agent

        Raises:
            PaymentsError: If the agent is not found
        """
        if pagination is None:
            pagination = PaginationOptions()

        url = f"{self.environment.backend}{API_URL_GET_AGENT_PLANS.format(agent_id=agent_id)}"
        params = {
            "page": pagination.page,
            "offset": pagination.offset,
        }
        response = requests.get(url, params=params)
        if not response.ok:
            raise PaymentsError(
                f"Unable to get agent plans. {response.status_code} - {response.text}"
            )
        return response.json()

    def add_plan_to_agent(self, plan_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Add a plan to an agent.

        Args:
            plan_id: The unique identifier of the plan
            agent_id: The unique identifier of the agent

        Returns:
            The result of the operation

        Raises:
            PaymentsError: If unable to add plan to agent
        """
        options = self.get_backend_http_options("POST")
        url = f"{self.environment.backend}{API_URL_ADD_PLAN_AGENT.format(agent_id=agent_id, plan_id=plan_id)}"

        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError(
                f"Unable to add plan to agent. {response.status_code} - {response.text}"
            )
        return response.json()

    def remove_plan_from_agent(self, plan_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Remove a plan from an agent.

        Args:
            plan_id: The unique identifier of the plan
            agent_id: The unique identifier of the agent

        Returns:
            The result of the operation

        Raises:
            PaymentsError: If unable to remove plan from agent
        """
        url = f"{self.environment.backend}{API_URL_REMOVE_PLAN_AGENT.format(agent_id=agent_id, plan_id=plan_id)}"
        options = self.get_backend_http_options("DELETE")

        response = requests.delete(url, **options)
        if not response.ok:
            raise PaymentsError(
                f"Unable to remove plan from agent. {response.status_code} - {response.text}"
            )
        return response.json()

    def get_agent_access_token(self, plan_id: str, agent_id: str) -> Dict[str, Any]:
        """
        Get an access token for an agent.

        Args:
            plan_id: The unique identifier of the plan
            agent_id: The unique identifier of the agent

        Returns:
            The access token information

        Raises:
            PaymentsError: If unable to get access token
        """
        url = f"{self.environment.backend}{API_URL_GET_AGENT_ACCESS_TOKEN.format(plan_id=plan_id, agent_id=agent_id)}"
        options = self.get_backend_http_options("GET")

        response = requests.get(url, **options)
        if not response.ok:
            raise PaymentsError(
                f"Unable to get agent access token. {response.status_code} - {response.text}"
            )
        return response.json()
