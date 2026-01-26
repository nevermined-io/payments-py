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

        assert mcp.agent_id == "did:nv:123"

    def test_creates_instance_with_version_and_description(self):
        """Test that PaymentsMCP can be created with version and description."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(
            mock_payments,
            name="test-server",
            version="2.0.0",
            description="Test description",
        )

        assert mcp.version == "2.0.0"
        assert mcp.description == "Test description"


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

    def test_tool_decorator_registers_function(self):
        """Test that @tool() registers the function."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool()
        def my_tool(x: int) -> int:
            return x * 2

        # Verify tool was registered
        assert "my_tool" in mcp._registered_tools
        assert mcp._registered_tools["my_tool"]["name"] == "my_tool"

    def test_tool_decorator_with_custom_name(self):
        """Test that @tool(name='custom') uses custom name."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool(name="custom_tool_name", description="A custom tool")
        def my_tool(x: int) -> int:
            return x * 2

        # Verify custom name was used
        assert "custom_tool_name" in mcp._registered_tools
        assert "my_tool" not in mcp._registered_tools
        assert (
            mcp._registered_tools["custom_tool_name"]["description"] == "A custom tool"
        )

    def test_tool_decorator_with_credits(self):
        """Test that @tool(credits=N) stores credits in registration."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server", agent_id="did:nv:123")

        @mcp.tool(credits=5)
        def paid_tool(x: int) -> int:
            return x * 2

        # Verify credits were stored
        assert mcp._registered_tools["paid_tool"]["credits"] == 5

        # Verify original function still works
        assert paid_tool(5) == 10

    def test_tool_decorator_preserves_function_metadata(self):
        """Test that decorated function preserves its metadata."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool()
        def documented_tool(x: int) -> int:
            """This is a documented tool."""
            return x * 2

        # Original function should still have its name and docstring
        assert documented_tool.__name__ == "documented_tool"
        assert "documented tool" in documented_tool.__doc__


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

    def test_resource_decorator_registers_function(self):
        """Test that @resource() registers the function."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.resource("data://config")
        def get_config() -> str:
            return '{"version": "1.0.0"}'

        # Verify resource was registered
        assert "data://config" in mcp._registered_resources
        assert mcp._registered_resources["data://config"]["uri"] == "data://config"

    def test_resource_decorator_with_credits(self):
        """Test that @resource(credits=N) stores credits in registration."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.resource("data://config", credits=3)
        def get_config() -> str:
            return '{"version": "1.0.0"}'

        # Verify credits were stored
        assert mcp._registered_resources["data://config"]["credits"] == 3


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

    def test_prompt_decorator_registers_function(self):
        """Test that @prompt() registers the function."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.prompt(description="A greeting prompt")
        def greeting(name: str) -> list:
            return [{"role": "user", "content": f"Hello {name}!"}]

        # Verify prompt was registered
        assert "greeting" in mcp._registered_prompts
        assert mcp._registered_prompts["greeting"]["name"] == "greeting"

    def test_prompt_decorator_with_custom_name(self):
        """Test that @prompt(name='custom') uses custom name."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.prompt(name="custom_greeting")
        def greeting(name: str) -> list:
            return [{"role": "user", "content": f"Hello {name}!"}]

        # Verify custom name was used
        assert "custom_greeting" in mcp._registered_prompts
        assert "greeting" not in mcp._registered_prompts


class TestPaymentsMCPIntrospection:
    """Tests for introspection methods."""

    def test_list_tools_returns_registered_tool_names(self):
        """Test that list_tools() returns registered tool names."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool()
        def tool1() -> str:
            return "1"

        @mcp.tool()
        def tool2() -> str:
            return "2"

        tools = mcp.list_tools()

        assert "tool1" in tools
        assert "tool2" in tools
        assert len(tools) == 2

    def test_list_resources_returns_registered_resource_uris(self):
        """Test that list_resources() returns registered resource URIs."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.resource("data://config")
        def get_config() -> str:
            return "{}"

        @mcp.resource("data://users")
        def get_users() -> str:
            return "[]"

        resources = mcp.list_resources()

        assert "data://config" in resources
        assert "data://users" in resources
        assert len(resources) == 2

    def test_list_prompts_returns_registered_prompt_names(self):
        """Test that list_prompts() returns registered prompt names."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.prompt()
        def greeting() -> list:
            return []

        @mcp.prompt()
        def farewell() -> list:
            return []

        prompts = mcp.list_prompts()

        assert "greeting" in prompts
        assert "farewell" in prompts
        assert len(prompts) == 2

    def test_get_tool_info_returns_tool_details(self):
        """Test that get_tool_info() returns tool details."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        @mcp.tool(credits=5)
        def my_tool(x: int) -> int:
            """My tool description."""
            return x * 2

        info = mcp.get_tool_info("my_tool")

        assert info is not None
        assert info["name"] == "my_tool"
        assert info["credits"] == 5
        assert "My tool description" in info["description"]

    def test_get_tool_info_returns_none_for_unknown_tool(self):
        """Test that get_tool_info() returns None for unknown tool."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server")

        info = mcp.get_tool_info("unknown_tool")

        assert info is None


class TestPaymentsMCPCreditsCallback:
    """Tests for dynamic credits via callback."""

    def test_tool_accepts_credits_as_callable(self):
        """Test that credits can be a callable for dynamic pricing."""
        from payments_py.mcp import PaymentsMCP

        mock_payments = MagicMock()
        mcp = PaymentsMCP(mock_payments, name="test-server", agent_id="did:nv:123")

        # Dynamic credits based on result length
        def calculate_credits(args, result):
            return len(result) // 100

        @mcp.tool(credits=calculate_credits)
        def generate_text(prompt: str) -> str:
            return "A" * 500  # 500 chars = 5 credits

        # Function should be registered with callable credits
        assert mcp._registered_tools["generate_text"]["credits"] == calculate_credits

        # Original function should still work
        result = generate_text("test")
        assert len(result) == 500
