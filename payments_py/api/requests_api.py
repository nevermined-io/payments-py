"""
The AgentRequestsAPI class provides methods to manage the requests received by AI Agents integrated with Nevermined.

Note: The old token flow methods (start_processing_request, redeem_credits_from_request) have been removed.
Use the x402 API (facilitator.verify_permissions, facilitator.settle_permissions) instead.
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
    API_URL_TRACK_AGENT_SUB_TASK,
    API_URL_SIMULATE_AGENT_REQUEST,
    API_URL_SIMULATE_REDEEM_AGENT_REQUEST,
)


class AgentRequestsAPI(BasePaymentsAPI):
    """
    The AgentRequestsAPI class provides methods to manage the requests received by AI Agents integrated with Nevermined.

    Note: For request validation and credit settlement, use the x402 API instead:
    - payments.facilitator.verify_permissions() - to verify token and permissions
    - payments.facilitator.settle_permissions() - to burn credits
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
