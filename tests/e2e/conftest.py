"""
Pytest configuration for E2E tests.

This module provides fixtures and configuration for end-to-end testing
of A2A payment flows.
"""

import asyncio
import os
import pytest
import logging

# Configure logging for E2E tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


# Force asyncio backend for pytest-anyio
@pytest.fixture
def anyio_backend():
    """Force asyncio backend for E2E tests."""
    return "asyncio"


@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for the entire test session."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_test_environment():
    """Setup test environment before each test."""
    # Set environment variables for testing
    os.environ.setdefault("E2E_BUILDER_API_KEY", "test-builder-key")
    os.environ.setdefault("E2E_SUBSCRIBER_API_KEY", "test-subscriber-key")

    # Add any other global setup here
    yield

    # Cleanup after test
    # Add any global cleanup here
    pass


@pytest.fixture
def timeout_config():
    """Provide timeout configuration for E2E tests."""
    return {
        "default_timeout": 30,
        "server_startup_timeout": 10,
        "network_timeout": 15,
    }


# Configure pytest markers
pytest_plugins = ["pytest_asyncio"]

# Mark all E2E tests as slow
pytestmark = [
    pytest.mark.slow,  # Can be used to skip E2E tests with -m "not slow"
]
