"""
The AgentsAPI class provides methods to register and interact with AI Agents on Nevermined.
"""

import requests
from typing import Dict, Any, List, Optional, Literal
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
    API_URL_UPDATE_AGENT,
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
            "metadataAttributes": self.pydantic_to_dict(agent_metadata),
            "agentApiAttributes": self.pydantic_to_dict(agent_api),
            "plans": payment_plans,
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REGISTER_AGENT}"

        response = requests.post(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to register agent", error)
        agent_data = response.json()
        return {"agentId": agent_data["data"]["agentId"]}

    def register_agent_and_plan(
        self,
        agent_metadata: AgentMetadata,
        agent_api: AgentAPIAttributes,
        plan_metadata: PlanMetadata,
        price_config: PlanPriceConfig,
        credits_config: PlanCreditsConfig,
        access_limit: Optional[Literal["credits", "time"]] = None,
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
            access_limit: Optional access limit for the plan
        Returns:
            Dictionary containing agentId, planId, and txHash

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

        body = {
            "plan": {
                "metadataAttributes": self.pydantic_to_dict(plan_metadata),
                "priceConfig": self.pydantic_to_dict(price_config),
                "creditsConfig": self.pydantic_to_dict(credits_config),
                "accessLimit": access_limit,
            },
            "agent": {
                "metadataAttributes": self.pydantic_to_dict(agent_metadata),
                "agentApiAttributes": self.pydantic_to_dict(agent_api),
            },
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REGISTER_AGENTS_AND_PLAN}"

        response = requests.post(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to register agent & plan", error)
        result = response.json()

        return {
            "agentId": result["data"]["agentId"],
            "planId": result["data"]["planId"],
            "txHash": result["txHash"],
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
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Agent not found", error)
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
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to get agent plans", error)
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
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to add plan to agent", error)
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
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to remove plan from agent", error)
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
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Unable to get agent access token", error)
        return response.json()

    def update_agent_metadata(
        self,
        agent_id: str,
        agent_metadata: AgentMetadata,
        agent_api: AgentAPIAttributes,
    ) -> Dict[str, Any]:
        """
        Updates the metadata and API attributes of an existing AI Agent.

        Args:
            agent_id: The unique identifier of the agent
            agent_metadata: The new metadata attributes for the agent
            agent_api: The new API attributes for the agent

        Returns:
            The result of the update operation

        Raises:
            PaymentsError: If the agent is not found or if the update fails
        """
        body = {
            "metadataAttributes": self.pydantic_to_dict(agent_metadata),
            "agentApiAttributes": self.pydantic_to_dict(agent_api),
        }
        url = f"{self.environment.backend}{API_URL_UPDATE_AGENT.format(agent_id=agent_id)}"
        options = self.get_backend_http_options("PUT", body)
        response = requests.put(url, **options)
        if not response.ok:
            try:
                error = response.json()
            except Exception:
                error = {"message": response.text, "code": response.status_code}
            raise PaymentsError.from_backend("Error updating agent", error)
        return response.json()
