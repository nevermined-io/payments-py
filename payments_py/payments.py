"""
Main Payments class for the Nevermined Payments protocol.
"""

from typing import Dict, Any
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.api.query_api import AIQueryApi
from payments_py.api.base_payments import BasePaymentsAPI
from payments_py.api.plans_api import PlansAPI
from payments_py.api.agents_api import AgentsAPI
from payments_py.api.requests_api import AgentRequestsAPI
from payments_py.api.observability_api import ObservabilityAPI

# A2A integration
from payments_py.a2a.agent_card import build_payment_agent_card
from payments_py.a2a.client_registry import ClientRegistry


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
            raise PaymentsError.unauthorized("Nevermined API Key is required")
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
            raise PaymentsError.validation("return_url is required")
        return cls(options, True)

    def _initialize_api(self, options: PaymentOptions) -> None:
        """
        Initialize the AI Query Protocol API.
        """
        self.plans = PlansAPI.get_instance(options)
        self.agents = AgentsAPI.get_instance(options)
        self.requests = AgentRequestsAPI.get_instance(options)
        self.query = AIQueryApi.get_instance()
        self.observability = ObservabilityAPI.get_instance(options)

        # Cached MCP integration
        self._mcp_integration = None

    @property
    def mcp(self):
        """
        Returns the MCP integration API. The instance is memoized so that configuration
        set via configure({ agentId, serverName }) persists across calls.
        """
        if self._mcp_integration is None:
            # Local import to avoid import cycles
            from payments_py.mcp.index import build_mcp_integration  # noqa: WPS433

            self._mcp_integration = build_mcp_integration(self)
        return self._mcp_integration

    @property
    def is_logged_in(self) -> bool:
        """
        Check if a user is logged in.

        Returns:
            True if the user is logged in

        Note: This is a browser-only function.
        """
        raise PaymentsError.internal("This is a browser-only function")
        return bool(self.nvm_api_key)

    def connect(self) -> None:
        """
        Initiates the connect flow. The user's browser will be redirected to
        the Nevermined App login page.

        Note: This is a browser-only function.
        """
        raise PaymentsError.internal("This is a browser-only function")
        url = f"{self.environment.frontend}/login?returnUrl={self.return_url}"
        # In a browser environment, this would redirect
        print(f"Redirecting to: {url}")

    def logout(self) -> None:
        """
        Logs out the user by removing the NVM API key.
        """
        raise PaymentsError.internal("This is a browser-only function")
        self.nvm_api_key = ""

        # ---------------------------------------------------------------------
        # A2A integration helpers
        # ---------------------------------------------------------------------

    # A2A client registry cache
    _a2a_registry: "ClientRegistry | None" = None  # type: ignore[name-defined]

    @property
    def a2a(self) -> Dict[str, Any]:
        from payments_py.a2a.server import PaymentsA2AServer

        """Expose A2A helpers (start server / get client) for Nevermined Payments."""
        # Local imports to avoid circular dependencies

        def _get_client(**options: Any):  # noqa: WPS430
            if self._a2a_registry is None:
                self._a2a_registry = ClientRegistry(self)  # type: ignore[arg-type]
            return self._a2a_registry.get_client(**options)

        return {
            # type: ignore[lambda-assign]
            "start": lambda **opts: PaymentsA2AServer.start(
                payments_service=self, **opts
            ),
            "get_client": _get_client,
        }

    a2a_helpers: Dict[str, Any] = {  # noqa: WPS110
        "build_payment_agent_card": build_payment_agent_card,
    }
