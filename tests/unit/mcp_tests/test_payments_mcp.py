"""
Unit tests for PaymentsMCP decorator-based API.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestPaymentsMCPInit:
    """Tests for PaymentsMCP initialization."""

    def test_creates_instance_with_payments_and_name(self):
        """Test that PaymentsMCP can be created with payments and name."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        assert mcp.name == "test-server"
        assert mcp.payments == mock_payments

    def test_creates_instance_with_agent_id(self):
        """Test that PaymentsMCP can be created with agent_id."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server", agent_id="did:nv:123")

        assert mcp._agent_id == "did:nv:123"

    def test_configure_updates_agent_id_and_name(self):
        """Test that configure() updates agent_id and server_name."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="initial-name")

        mcp.configure(agent_id="did:nv:456", server_name="new-name")

        assert mcp._agent_id == "did:nv:456"
        assert mcp.name == "new-name"


class TestPaymentsMCPToolDecorator:
    """Tests for @mcp.tool() decorator."""

    def test_tool_decorator_raises_when_called_without_parens(self):
        """Test that @tool without () raises TypeError."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        with pytest.raises(TypeError, match="Did you forget to call it"):
            # Simulate @mcp.tool instead of @mcp.tool()
            mcp.tool(lambda x: x)

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_tool_decorator_registers_function(self, mock_get_mcp):
        """Test that @tool() registers the function with FastMCP."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool()
        def my_tool(x: int) -> int:
            return x * 2

        # Verify add_tool was called
        mock_fastmcp.add_tool.assert_called_once()
        call_args = mock_fastmcp.add_tool.call_args
        assert call_args[1]["name"] == "my_tool"

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_tool_decorator_with_custom_name(self, mock_get_mcp):
        """Test that @tool(name='custom') uses custom name."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool(name="custom_tool_name", description="A custom tool")
        def my_tool(x: int) -> int:
            return x * 2

        call_args = mock_fastmcp.add_tool.call_args
        assert call_args[1]["name"] == "custom_tool_name"
        assert call_args[1]["description"] == "A custom tool"

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_tool_decorator_with_credits(self, mock_get_mcp):
        """Test that @tool(credits=N) enables payment functionality."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server", agent_id="did:nv:123")

        @mcp.tool(credits=5)
        def paid_tool(x: int) -> int:
            return x * 2

        assert paid_tool(5) == 10


class TestPaymentsMCPResourceDecorator:
    """Tests for @mcp.resource() decorator."""

    def test_resource_decorator_raises_when_called_without_uri(self):
        """Test that @resource without uri raises TypeError."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        with pytest.raises(TypeError, match="Did you forget to call it"):
            # Simulate @mcp.resource instead of @mcp.resource('uri')
            mcp.resource(lambda: "data")

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_resource_decorator_registers_function(self, mock_get_mcp):
        """Test that @resource() registers the function with FastMCP."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.resource("data://config")
        def get_config() -> str:
            return '{"version": "1.0.0"}'

        # Verify add_resource was called
        mock_fastmcp.add_resource.assert_called_once()
        call_args = mock_fastmcp.add_resource.call_args
        assert call_args[1]["uri"] == "data://config"


class TestPaymentsMCPPromptDecorator:
    """Tests for @mcp.prompt() decorator."""

    def test_prompt_decorator_raises_when_called_without_parens(self):
        """Test that @prompt without () raises TypeError."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        with pytest.raises(TypeError, match="Did you forget to call it"):
            # Simulate @mcp.prompt instead of @mcp.prompt()
            mcp.prompt(lambda: [])

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    @patch("mcp.server.fastmcp.prompts.Prompt")
    def test_prompt_decorator_registers_function(self, mock_prompt_class, mock_get_mcp):
        """Test that @prompt() registers the function with FastMCP."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp
        mock_prompt_class.from_function.return_value = MagicMock()

        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.prompt(description="A greeting prompt")
        def greeting(name: str) -> list:
            return [{"role": "user", "content": f"Hello {name}!"}]

        # Verify add_prompt was called
        mock_fastmcp.add_prompt.assert_called_once()


class TestPaymentsMCPDelegation:
    """Tests for delegation to FastMCP methods."""

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_list_tools_delegates_to_fastmcp(self, mock_get_mcp):
        """Test that list_tools() delegates to FastMCP."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_fastmcp.list_tools.return_value = ["tool1", "tool2"]
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server")
        tools = mcp.list_tools()

        assert tools == ["tool1", "tool2"]
        mock_fastmcp.list_tools.assert_called_once()

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_mcp_property_returns_fastmcp_instance(self, mock_get_mcp):
        """Test that .mcp property returns FastMCP instance."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server")

        assert mcp.mcp == mock_fastmcp


class TestPaymentsMCPCreditsCallback:
    """Tests for dynamic credits via callback."""

    @patch("payments_py.mcp.payments_mcp.PaymentsMCP._get_mcp")
    def test_tool_accepts_credits_as_callable(self, mock_get_mcp):
        """Test that credits can be a callable for dynamic pricing."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mock_fastmcp = MagicMock()
        mock_get_mcp.return_value = mock_fastmcp

        mcp = PaymentsMCP(mock_payments, name="test-server", agent_id="did:nv:123")

        # Dynamic credits based on result length
        def calculate_credits(args, result):
            return len(result) // 100

        @mcp.tool(credits=calculate_credits)
        def generate_text(prompt: str) -> str:
            return "A" * 500  # 500 chars = 5 credits

        # Function should be registered
        mock_fastmcp.add_tool.assert_called_once()
