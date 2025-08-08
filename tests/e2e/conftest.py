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


@pytest.fixture
def timeout_config():
    """Provide timeout configuration for E2E tests."""
    return {
        "default_timeout": 30,
        "server_startup_timeout": 10,
        "network_timeout": 15,
    }


def pytest_addoption(parser):
    parser.addoption(
        "--e2e-retries",
        action="store",
        default=os.getenv("E2E_RETRIES", "2"),
        help="Number of retries for E2E tests",
    )


def pytest_runtest_setup(item):
    # Mark all tests in this folder as slow and apply reruns
    item.add_marker(pytest.mark.slow)
    try:
        retries = int(item.config.getoption("--e2e-retries"))
        if retries > 0:
            item.add_marker(pytest.mark.flaky(reruns=retries, reruns_delay=1.0))
    except Exception:
        pass
