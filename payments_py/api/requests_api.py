"""
The AgentRequestsAPI class provides methods to manage the requests received by AI Agents integrated with Nevermined.
"""

import requests
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

    def start_processing_request(
        self,
        agent_id: str,
        access_token: str,
        url_requested: str,
        http_method_requested: str,
    ) -> StartAgentRequest:
        """
        This method initializes an agent request.

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
        initialize_agent_url = API_URL_INITIALIZE_AGENT.format(agent_id=agent_id)
        body = {
            "accessToken": access_token,
            "endpoint": url_requested,
            "httpVerb": http_method_requested,
        }
        options = self.get_backend_http_options("POST", body)

        url = f"{self.environment.backend}{initialize_agent_url}"
        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to validate access token. {response.status_code} - {response.text}"
            )

        return response.json()

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
            "amount": credits_to_burn,
        }

        options = self.get_backend_http_options("POST", body)
        url = f"{self.environment.backend}{API_URL_REDEEM_PLAN}"
        response = requests.post(url, **options)
        if not response.ok:
            raise PaymentsError.internal(
                f"Unable to redeem credits from request. {response.status_code} - {response.text}"
            )

        return response.json()

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
