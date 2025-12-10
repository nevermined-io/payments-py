"""
Pytest configuration for E2E tests.

This module provides fixtures and configuration for end-to-end testing
of payment flows. Common fixtures and test configuration are centralized here
to avoid duplication across test files.
"""

import asyncio
import os
import pytest
import logging
from payments_py.payments import Payments
from payments_py.common.types import PaymentOptions

# Configure logging for E2E tests
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# ============================================================================
# Test Configuration Constants
# ============================================================================

# Test environment (can be overridden via TEST_ENVIRONMENT env var)
TEST_ENVIRONMENT = os.getenv("TEST_ENVIRONMENT", "staging_sandbox")

# Test timeout in seconds (can be overridden per test file if needed)
TEST_TIMEOUT = int(os.getenv("TEST_TIMEOUT", "60"))

# Test ERC20 token address (USDC on Base Sepolia)
# Same address used across all E2E tests
TEST_ERC20_TOKEN = "0x036CbD53842c5426634e7929541eC2318f3dCF7e"

# Test API keys - can be overridden via environment variables
# Default values are for staging_sandbox environment
SUBSCRIBER_API_KEY = os.getenv(
    "TEST_SUBSCRIBER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDcxZTZGN2Y4QzY4ZTdlMkU5NkIzYzkwNjU1YzJEMmNBMzc2QmMzZmQiLCJqdGkiOiIweDMwN2Y0NWRkMTBiOTc1YjhlNDU5NzNkMmNiNTljY2MzZDQ2NjFmY2RiOTJiMTVmMjI2ZDNhY2Q0NjdkODYyMDUiLCJleHAiOjE3OTY5MzM3MjcsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.0khtYy6bG_m6mDE2Oa1sozQLBHve2yVwyUeeM9DAHzFxhwK86JSfGL973Sg8FzhTfD2xhzYWiFP3KV2GjWNnDRs",
)

AGENT_API_KEY = os.getenv(
    "TEST_BUILDER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDlkREQwMkQ0RTExMWFiNWNFNDc1MTE5ODdCMjUwMGZjQjU2MjUyYzYiLCJqdGkiOiIweDQ2YzY3OTk5MTY5NDBhZmI4ZGNmNmQ2NmRmZmY4MGE0YmVhYWMyY2NiYWZlOTlkOGEwOTAwYTBjMzhmZjdkNjEiLCJleHAiOjE3OTU1NDI4NzAsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.n51gkto9Jw-MXxnXW92XDAB_CnHUFxkritWp9Lj1qFASmtf_TuQwU57bauIEGrQygumX8S3pXqRqeGRWT2AJiRs",
)

# Alias for backward compatibility (some tests use BUILDER_API_KEY)
BUILDER_API_KEY = AGENT_API_KEY

# ============================================================================
# Pytest Fixtures
# ============================================================================


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


@pytest.fixture(scope="module")
def payments_subscriber():
    """
    Create a Payments instance for the subscriber.

    This fixture is shared across all E2E test files and provides
    a Payments instance configured with the subscriber API key.
    """
    return Payments(
        PaymentOptions(nvm_api_key=SUBSCRIBER_API_KEY, environment=TEST_ENVIRONMENT)
    )


@pytest.fixture(scope="module")
def payments_agent():
    """
    Create a Payments instance for the agent (builder).

    This fixture is shared across all E2E test files and provides
    a Payments instance configured with the agent/builder API key.
    """
    return Payments(
        PaymentOptions(nvm_api_key=AGENT_API_KEY, environment=TEST_ENVIRONMENT)
    )


# Alias for backward compatibility (some tests use payments_builder)
@pytest.fixture(scope="module")
def payments_builder():
    """
    Alias for payments_agent fixture.

    Some tests use 'payments_builder' instead of 'payments_agent'.
    This provides backward compatibility.
    """
    return Payments(
        PaymentOptions(nvm_api_key=BUILDER_API_KEY, environment=TEST_ENVIRONMENT)
    )


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
