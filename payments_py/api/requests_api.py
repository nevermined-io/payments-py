"""
The AgentRequestsAPI class provides methods to manage the requests received by AI Agents integrated with Nevermined.
"""

import requests
import time
from urllib.parse import urljoin
from typing import Dict, Any
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import (
    PaymentOptions,
    TrackAgentSubTaskDto,
    StartAgentRequest,
)
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.nvm_api import (
    API_URL_REDEEM_PLAN,
    API_URL_INITIALIZE_AGENT,
    API_URL_TRACK_AGENT_SUB_TASK,
    API_URL_SIMULATE_AGENT_REQUEST,
    API_URL_SIMULATE_REDEEM_AGENT_REQUEST,
)
from payments_py.utils import decode_access_token


class AgentRequestsAPI(BasePaymentsAPI):
    """
    The AgentRequestsAPI class provides methods to manage the requests received by AI Agents integrated with Nevermined.
    """

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "AgentRequestsAPI":
        """
        Get a singleton instance of the AgentRequestsAPI class.

        Args:
            options: The options to initialize the payments class

        Returns:
            The instance of the AgentRequestsAPI class
        """
        return cls(options)

    def start_processing_batch_request(
        self,
        agent_id: str,
        access_token: str,
        url_requested: str,
        http_method_requested: str,
    ) -> StartAgentRequest:
        """
        This method initializes a batch agent request.

        Args:
            agent_id: The unique identifier of the AI Agent
            access_token: The access token provided by the subscriber to validate
            url_requested: The URL requested by the subscriber to access the agent's API
            http_method_requested: The HTTP method requested by the subscriber to access the agent's API

        Returns:
            The information about the initialization of the request

        Raises:
            PaymentsError: If unable to initialize the agent request
        """
        return self.start_processing_request(
            agent_id, access_token, url_requested, http_method_requested, batch=True
        )

    def start_processing_request(
        self,
        agent_id: str,
        access_token: str,
        url_requested: str,
        http_method_requested: str,
        batch: bool = False,
    ) -> StartAgentRequest:
        """
        This method initializes an agent request.

        Args:
            agent_id: The unique identifier of the AI Agent
            access_token: The access token provided by the subscriber to validate
            url_requested: The URL requested by the subscriber to access the agent's API
            http_method_requested: The HTTP method requested by the subscriber to access the agent's API
            batch: Whether the request is a batch request

        Returns:
            The information about the initialization of the request

        Raises:
            PaymentsError: If unable to initialize the agent request
        """
        if not agent_id:
            raise PaymentsError.validation("Agent ID is required")

        initialize_agent_url = API_URL_INITIALIZE_AGENT.format(agent_id=agent_id)
        body = {
            "accessToken": access_token,
            "endpoint": url_requested,
            "httpVerb": http_method_requested,
            "batch": batch,
        }
        options = self.get_backend_http_options("POST", body)

        url = f"{self.environment.backend}{initialize_agent_url}"
        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to validate access token. {response.status_code} - {response.text}"
            )

        # Parse and validate response using Pydantic model to ensure type conversion
        response_data = response.json()
        return StartAgentRequest(**response_data)

    def is_valid_request(
        self,
        agent_id: str,
        access_token: str,
        url_requested: str,
        http_method_requested: str,
    ) -> Dict[str, Any]:
        """
        This method validates if a request sent by a user is valid to be processed by an AI Agent.

        This method can be used to build the agent authorization system.
        This method is a simplification of the `start_processing_request` method.

        Args:
            agent_id: The unique identifier of the AI Agent
            access_token: The access token provided by the subscriber to validate
            url_requested: The URL requested by the subscriber to access the agent's API
            http_method_requested: The HTTP method requested by the subscriber to access the agent's API

        Returns:
            Dictionary with agentRequestId and isValidRequest boolean

        Raises:
            PaymentsError: If unable to initialize the agent request
        """
        agent_request_info = self.start_processing_request(
            agent_id, access_token, url_requested, http_method_requested
        )
        return {
            "agentRequestId": agent_request_info.get("agentRequestId"),
            "isValidRequest": agent_request_info.get("balance", {}).get(
                "isSubscriber", False
            ),
        }

    def redeem_with_margin_from_request(
        self,
        agent_request_id: str,
        request_access_token: str,
        margin_percent: float,
    ) -> Dict[str, Any]:
        """
        Allows the agent to redeem credits based on margin percentage from a request.

        Args:
            agent_request_id: The unique identifier of the agent request
            request_access_token: The access token of the request
            margin_percent: The margin percentage to apply

        Returns:
            A promise that resolves to the result of the operation

        Raises:
            PaymentsError: If unable to redeem credits from the request
        """
        return self._redeem_credits(
            agent_request_id,
            request_access_token,
            batch=False,
            margin_percent=margin_percent,
        )

    def redeem_with_margin_from_batch_request(
        self,
        agent_request_id: str,
        request_access_token: str,
        margin_percent: float,
    ) -> Dict[str, Any]:
        """
        Allows the agent to redeem credits based on margin percentage from a batch request.

        Args:
            agent_request_id: The unique identifier of the agent request
            request_access_token: The access token of the request
            margin_percent: The margin percentage to apply

        Returns:
            A promise that resolves to the result of the operation

        Raises:
            PaymentsError: If unable to redeem credits from the request
        """
        return self._redeem_credits(
            agent_request_id,
            request_access_token,
            batch=True,
            margin_percent=margin_percent,
        )

    def redeem_credits_from_batch_request(
        self,
        agent_request_id: str,
        request_access_token: str,
        credits_to_burn: int,
    ) -> Dict[str, Any]:
        """
        Allows the agent to redeem credits from a batch request.

        Args:
            agent_request_id: The unique identifier of the agent request
            request_access_token: The access token of the request
            credits_to_burn: The number of credits to burn

        Returns:
            A promise that resolves to the result of the operation

        Raises:
            PaymentsError: If unable to redeem credits from the request
        """
        return self._redeem_credits(
            agent_request_id,
            request_access_token,
            batch=True,
            credits_to_burn=credits_to_burn,
        )

    def redeem_credits_from_request(
        self,
        agent_request_id: str,
        request_access_token: str,
        credits_to_burn: int,
    ) -> Dict[str, Any]:
        """
        Allows the agent to redeem credits from a request.

        Args:
            agent_request_id: The unique identifier of the agent request
            request_access_token: The access token of the request
            credits_to_burn: The number of credits to burn

        Returns:
            A promise that resolves to the result of the operation

        Raises:
            PaymentsError: If unable to redeem credits from the request
        """
        return self._redeem_credits(
            agent_request_id,
            request_access_token,
            batch=False,
            credits_to_burn=credits_to_burn,
        )

    def _redeem_credits(
        self,
        agent_request_id: str,
        request_access_token: str,
        batch: bool = False,
        credits_to_burn: int = None,
        margin_percent: float = None,
    ) -> Dict[str, Any]:
        """
        Private method to redeem credits from a request.

        Args:
            agent_request_id: The unique identifier of the agent request
            request_access_token: The access token of the request
            batch: Whether the request is a batch request
            credits_to_burn: The number of credits to burn
            margin_percent: The margin percentage to apply

        Returns:
            A promise that resolves to the result of the operation

        Raises:
            PaymentsError: If unable to redeem credits from the request
        """
        # Validate mutually exclusive parameters
        if (credits_to_burn is not None and margin_percent is not None) or (
            credits_to_burn is None and margin_percent is None
        ):
            raise PaymentsError.validation(
                "Either credits_to_burn or margin_percent must be provided, but not both"
            )

        # Decode the access token to get the wallet address and plan ID
        decoded_token = decode_access_token(request_access_token)
        if not decoded_token:
            raise PaymentsError.validation("Invalid access token provided")

        # Extract wallet address and plan ID from the token
        # Check if authToken is a nested JWT string that needs to be decoded
        auth_token_value = decoded_token.get("authToken")
        if auth_token_value and isinstance(auth_token_value, str):
            auth_token_decoded = decode_access_token(auth_token_value)
        else:
            auth_token_decoded = auth_token_value

        # Extract wallet address and plan ID with fallback logic like TypeScript version
        wallet_address = None
        if auth_token_decoded and isinstance(auth_token_decoded, dict):
            wallet_address = auth_token_decoded.get("sub")
        if not wallet_address:
            wallet_address = decoded_token.get("sub")

        plan_id = None
        if auth_token_decoded and isinstance(auth_token_decoded, dict):
            plan_id = auth_token_decoded.get("planId")
        if not plan_id:
            plan_id = decoded_token.get("planId")

        if not wallet_address or not plan_id:
            raise PaymentsError.validation(
                "Missing wallet address or plan ID in access token"
            )

        body = {
            "agentRequestId": agent_request_id,
            "planId": str(plan_id),  # Keep as string to avoid scientific notation
            "redeemFrom": wallet_address,
            "batch": batch,
        }

        if credits_to_burn is not None:
            body["amount"] = credits_to_burn
        if margin_percent is not None:
            body["marginPercent"] = margin_percent

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REDEEM_PLAN}"
        response = requests.post(url, **options)
        response_body = response.json() if response.text else {}
        if not response.ok:
            raise PaymentsError.from_backend(
                "Unable to redeem credits from request", response_body
            )

        return response_body

    def track_agent_sub_task(
        self, track_agent_sub_task: TrackAgentSubTaskDto
    ) -> Dict[str, Any]:
        """
        Tracks an agent sub task.

        This method is used by agent owners to track agent sub tasks for agent tasks.
        It records information about credit redemption, categorization tags, and processing descriptions.

        Args:
            track_agent_sub_task: The agent sub task data to track

        Returns:
            A promise that resolves to the result of the operation

        Raises:
            PaymentsError: If unable to track the agent sub task
        """
        body = {
            "agentRequestId": track_agent_sub_task.agent_request_id,
            "creditsToRedeem": track_agent_sub_task.credits_to_redeem or 0,
            "tag": track_agent_sub_task.tag,
            "description": track_agent_sub_task.description,
            "status": (
                track_agent_sub_task.status.value
                if track_agent_sub_task.status
                else None
            ),
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_TRACK_AGENT_SUB_TASK}"
        response = requests.post(url, **options)

        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to track agent sub task. {response.status_code} - {response.text}"
            )

        return response.json()

    def start_simulation_request(
        self,
        price_per_credit: float = 0.01,
        batch: bool = False,
        agent_name: str = None,
        plan_name: str = None,
    ) -> StartAgentRequest:
        """
        This method simulates an agent request.

        Args:
            price_per_credit: The price per credit in USD
            batch: Whether the request is a batch request
            agent_name: The name of the agent
            plan_name: The name of the plan

        Returns:
            The information about the simulation of the request
        """

        body = {
            "pricePerCredit": price_per_credit,
            "batch": batch,
        }
        if agent_name is not None:
            body["agentName"] = agent_name
        if plan_name is not None:
            body["planName"] = plan_name
        options = self.get_backend_http_options("POST", body)
        url = urljoin(self.environment.backend, API_URL_SIMULATE_AGENT_REQUEST)
        response = requests.post(url, **options)

        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to start simulation request. {response.status_code} - {response.text}"
            )

        response_data = response.json()
        return StartAgentRequest(**response_data)

    def finish_simulation_request(
        self, agent_request_id: str, margin_percent: float = 0.2, batch: bool = False
    ) -> Dict[str, Any]:
        """
        Simulates the redemption of credits for an agent request.

        Args:
            agent_request_id: The unique identifier of the agent request.
            margin_percent: The margin percentage to apply. Defaults to 0.2.
            batch: Whether the request is a batch request. Defaults to False.

        Returns:
            A dictionary containing the result of the simulation, including the credits to redeem and the success status.

        Raises:
            PaymentsError: If unable to finish the simulation request.
        """

        body = {
            "agentRequestId": agent_request_id,
            "marginPercent": margin_percent,
            "batch": batch,
        }
        options = self.get_backend_http_options("POST", body)
        url = urljoin(self.environment.backend, API_URL_SIMULATE_REDEEM_AGENT_REQUEST)

        # Since this method is usually called immediately after the llm call
        # the request might not be immediately available on helicone, so we need to retry.
        max_retries = 3
        last_error = None

        for attempt in range(max_retries):
            try:
                response = requests.post(url, **options)
                if not response.ok:
                    last_error = PaymentsError.internal(
                        f"Unable to finish simulation request. {response.status_code} - {response.text}"
                    )
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
                    raise last_error
                return response.json()
            except requests.exceptions.RequestException as e:
                last_error = PaymentsError.internal(
                    f"Unable to finish simulation request. Request failed: {str(e)}"
                )
                if attempt < max_retries - 1:
                    time.sleep(1)
                    continue
                raise last_error
