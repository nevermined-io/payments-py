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
from payments_py.api.contracts_api import ContractsAPI
from payments_py.x402.facilitator_api import FacilitatorAPI
from payments_py.x402.token import X402TokenAPI

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
    - `facilitator`: Handles X402 permission verification and settlement for AI Agents acting as facilitators.
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
        self.facilitator = FacilitatorAPI.get_instance(options)
        self.x402 = X402TokenAPI.get_instance(options)
        self.contracts_api = ContractsAPI(options)

        # Cached MCP integration
        self._mcp_integration = None

        # Cached AgentCore integration
        self._agentcore_api = None

        # Cached Delegation API
        self._delegation_api = None

    @property
    def contracts(self):
        """
        Get contract addresses from the deployment info endpoint.

        Returns:
            Contracts model with all contract addresses accessible via snake_case properties

        Example::
            template_address = payments.contracts.pay_as_you_go_template
        """
        return self.contracts_api.contracts

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
    def agentcore(self):
        """
        Returns the AgentCore integration API for AWS Bedrock.

        Provides methods to create x402 payment interceptors for
        AgentCore Gateway Lambda functions.

        Example:
            ```python
            interceptor = payments.agentcore.create_interceptor(plan_id="123")
            handler = payments.agentcore.create_lambda_handler(plan_id="123")
            ```
        """
        if self._agentcore_api is None:
            # Local import to avoid import cycles
            from payments_py.x402.agentcore import AgentCoreAPI  # noqa: WPS433

            self._agentcore_api = AgentCoreAPI(self)
        return self._agentcore_api

    @property
    def delegation(self):
        """
        Returns the Delegation API for managing card-delegation payment methods.

        Provides methods to list the user's enrolled Stripe payment methods
        for use with the nvm:card-delegation x402 scheme.

        Example:
            ```python
            methods = payments.delegation.list_payment_methods()
            for pm in methods:
                print(f"{pm.brand} *{pm.last4}")
            ```
        """
        if self._delegation_api is None:
            from payments_py.x402.delegation_api import DelegationAPI  # noqa: WPS433

            self._delegation_api = DelegationAPI.get_instance(self._build_options())
        return self._delegation_api

    def _build_options(self):
        """Build PaymentOptions from current state."""
        return PaymentOptions(
            nvm_api_key=self.nvm_api_key,
            environment=self.environment_name,
            app_id=self.app_id,
            version=self.version,
        )

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
