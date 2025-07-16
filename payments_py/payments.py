"""
Main Payments class for the Nevermined Payments protocol.
"""

from typing import Optional, Dict, Any
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.query_api import AIQueryApi
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.plans_api import PlansAPI
from payments_py.api.agents_api import AgentsAPI
from payments_py.api.requests_api import AgentRequestsAPI


class Payments(BasePaymentsAPI):
    """
    Main class that interacts with the Nevermined payments API.
    Use `Payments.get_instance` for server-side usage.

    The library provides methods to manage AI Agents, Plans & process AI Agent Requests.

    Each of these functionalities is encapsulated in its own API class:
    - `plans`: Manages AI Plans, including registration and ordering and retrieving plan details.
    - `agents`: Handles AI Agents, including registration of AI Agents and access token generation.
    - `requests`: Manages requests received by AI Agents, including validation and tracking.
    """

    def __init__(self, options: PaymentOptions, is_browser_instance: bool = False):
        """
        Initialize the Payments class.

        Args:
            options: The initialization options
            is_browser_instance: Whether this is a browser instance (default False)
        """
        super().__init__(options)
        self.is_browser_instance = is_browser_instance
        self._initialize_api(options)

    @classmethod
    def get_instance(cls, options: PaymentOptions) -> "Payments":
        """
        Get an instance of the Payments class for server-side usage.

        Args:
            options: The options to initialize the payments class

        Returns:
            An instance of Payments

        Raises:
            PaymentsError: If nvm_api_key is missing
        """
        if not options.nvm_api_key:
            raise PaymentsError("Nevermined API Key is required")
        return cls(options, False)

    @classmethod
    def get_browser_instance(cls, options: PaymentOptions) -> "Payments":
        """
        Get an instance of the Payments class for browser usage.

        Args:
            options: The options to initialize the payments class

        Returns:
            An instance of Payments

        Raises:
            PaymentsError: If return_url is missing
        """
        if not options.return_url:
            raise PaymentsError("return_url is required")
        return cls(options, True)

    def _initialize_api(self, options: PaymentOptions) -> None:
        """
        Initialize the AI Query Protocol API.
        """
        self.plans = PlansAPI.get_instance(options)
        self.agents = AgentsAPI.get_instance(options)
        self.requests = AgentRequestsAPI.get_instance(options)
        self.query = AIQueryApi.get_instance()

    @property
    def is_logged_in(self) -> bool:
        """
        Check if a user is logged in.

        Returns:
            True if the user is logged in

        Note: This is a browser-only function.
        """
        raise PaymentsError("This is a browser-only function")
        return bool(self.nvm_api_key)

    def connect(self) -> None:
        """
        Initiates the connect flow. The user's browser will be redirected to
        the Nevermined App login page.

        Note: This is a browser-only function.
        """
        raise PaymentsError("This is a browser-only function")
        url = f"{self.environment.frontend}/login?returnUrl={self.return_url}"
        # In a browser environment, this would redirect
        print(f"Redirecting to: {url}")

    def logout(self) -> None:
        """
        Logs out the user by removing the NVM API key.
        """
        raise PaymentsError("This is a browser-only function")
        self.nvm_api_key = ""
