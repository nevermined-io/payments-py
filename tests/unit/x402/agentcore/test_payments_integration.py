"""
Tests for Payments.agentcore property integration.
"""

from unittest.mock import MagicMock, patch


class TestPaymentsAgentCoreIntegration:
    """Tests for the payments.agentcore property integration."""

    def test_agentcore_property_lazy_loads(self):
        """Test that agentcore property is lazy loaded."""
        # Create a mock Payments instance manually to avoid initialization
        from payments_py.x402.agentcore import AgentCoreAPI

        mock_payments = MagicMock()
        mock_payments._agentcore_api = None

        # Simulate the property behavior
        def get_agentcore():
            if mock_payments._agentcore_api is None:
                mock_payments._agentcore_api = AgentCoreAPI(mock_payments)
            return mock_payments._agentcore_api

        mock_payments.agentcore = property(lambda self: get_agentcore())

        # First access creates the API
        api1 = get_agentcore()
        assert isinstance(api1, AgentCoreAPI)

        # Second access returns same instance
        api2 = get_agentcore()
        assert api1 is api2

    def test_agentcore_api_creates_interceptor(self):
        """Test that AgentCoreAPI creates valid interceptors."""
        from payments_py.x402.agentcore import AgentCoreAPI, AgentCoreInterceptor

        mock_payments = MagicMock()
        api = AgentCoreAPI(mock_payments)

        interceptor = api.create_interceptor(plan_id="test-plan")

        assert isinstance(interceptor, AgentCoreInterceptor)
        assert interceptor.default_config.plan_id == "test-plan"

    def test_agentcore_api_creates_lambda_handler(self):
        """Test that AgentCoreAPI creates callable lambda handlers."""
        from payments_py.x402.agentcore import AgentCoreAPI

        mock_payments = MagicMock()
        api = AgentCoreAPI(mock_payments)

        handler = api.create_lambda_handler(plan_id="test-plan")

        assert callable(handler)

    def test_agentcore_api_passes_payments_to_interceptor(self):
        """Test that the Payments instance is correctly passed to interceptor."""
        from payments_py.x402.agentcore import AgentCoreAPI

        mock_payments = MagicMock()
        mock_payments.facilitator = MagicMock()

        api = AgentCoreAPI(mock_payments)
        interceptor = api.create_interceptor(plan_id="test-plan")

        # The interceptor should have access to payments
        assert interceptor.payments is mock_payments
        assert interceptor.payments.facilitator is mock_payments.facilitator

    def test_agentcore_api_forwards_all_kwargs(self):
        """Test that all kwargs are forwarded to interceptor."""
        from payments_py.x402.agentcore import AgentCoreAPI, InterceptorOptions

        mock_payments = MagicMock()
        api = AgentCoreAPI(mock_payments)

        options = InterceptorOptions(mock_mode=True)
        interceptor = api.create_interceptor(
            plan_id="test-plan",
            credits=5,
            agent_id="agent-123",
            network="eip155:1",
            description="Test description",
            options=options,
        )

        assert interceptor.default_config.plan_id == "test-plan"
        assert interceptor.default_config.credits == 5
        assert interceptor.default_config.agent_id == "agent-123"
        assert interceptor.default_config.network == "eip155:1"
        assert interceptor.default_config.description == "Test description"
        assert interceptor.options.mock_mode is True


class TestAgentCorePropertyInPaymentsClass:
    """Test the actual Payments class integration (with mocking)."""

    @patch("payments_py.payments.PlansAPI")
    @patch("payments_py.payments.AgentsAPI")
    @patch("payments_py.payments.AgentRequestsAPI")
    @patch("payments_py.payments.AIQueryApi")
    @patch("payments_py.payments.ObservabilityAPI")
    @patch("payments_py.payments.FacilitatorAPI")
    @patch("payments_py.payments.X402TokenAPI")
    @patch("payments_py.payments.ContractsAPI")
    @patch("payments_py.api.base_payments.BasePaymentsAPI._parse_nvm_api_key")
    def test_payments_has_agentcore_property(
        self,
        mock_parse,
        mock_contracts,
        mock_x402,
        mock_facilitator,
        mock_observability,
        mock_query,
        mock_requests,
        mock_agents,
        mock_plans,
    ):
        """Test that Payments class has agentcore property."""
        from payments_py import Payments, PaymentOptions

        payments = Payments(
            PaymentOptions(nvm_api_key="nvm:test", environment="sandbox")
        )

        # Check property exists
        assert hasattr(payments, "agentcore")

        # Access property
        api = payments.agentcore

        # Check it's the right type
        from payments_py.x402.agentcore import AgentCoreAPI

        assert isinstance(api, AgentCoreAPI)

    @patch("payments_py.payments.PlansAPI")
    @patch("payments_py.payments.AgentsAPI")
    @patch("payments_py.payments.AgentRequestsAPI")
    @patch("payments_py.payments.AIQueryApi")
    @patch("payments_py.payments.ObservabilityAPI")
    @patch("payments_py.payments.FacilitatorAPI")
    @patch("payments_py.payments.X402TokenAPI")
    @patch("payments_py.payments.ContractsAPI")
    @patch("payments_py.api.base_payments.BasePaymentsAPI._parse_nvm_api_key")
    def test_payments_agentcore_creates_interceptor(
        self,
        mock_parse,
        mock_contracts,
        mock_x402,
        mock_facilitator,
        mock_observability,
        mock_query,
        mock_requests,
        mock_agents,
        mock_plans,
    ):
        """Test creating interceptor via payments.agentcore."""
        from payments_py import Payments, PaymentOptions
        from payments_py.x402.agentcore import AgentCoreInterceptor

        payments = Payments(
            PaymentOptions(nvm_api_key="nvm:test", environment="sandbox")
        )

        interceptor = payments.agentcore.create_interceptor(plan_id="test-plan")

        assert isinstance(interceptor, AgentCoreInterceptor)

    @patch("payments_py.payments.PlansAPI")
    @patch("payments_py.payments.AgentsAPI")
    @patch("payments_py.payments.AgentRequestsAPI")
    @patch("payments_py.payments.AIQueryApi")
    @patch("payments_py.payments.ObservabilityAPI")
    @patch("payments_py.payments.FacilitatorAPI")
    @patch("payments_py.payments.X402TokenAPI")
    @patch("payments_py.payments.ContractsAPI")
    @patch("payments_py.api.base_payments.BasePaymentsAPI._parse_nvm_api_key")
    def test_payments_agentcore_property_is_memoized(
        self,
        mock_parse,
        mock_contracts,
        mock_x402,
        mock_facilitator,
        mock_observability,
        mock_query,
        mock_requests,
        mock_agents,
        mock_plans,
    ):
        """Test that agentcore property returns same instance on multiple accesses."""
        from payments_py import Payments, PaymentOptions

        payments = Payments(
            PaymentOptions(nvm_api_key="nvm:test", environment="sandbox")
        )

        api1 = payments.agentcore
        api2 = payments.agentcore

        assert api1 is api2
