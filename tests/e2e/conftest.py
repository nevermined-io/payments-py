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

# Test API keys - can be overridden via environment variables.
# Defaults are the staging-sandbox `testing-merchant@nevermined.io` /
# `testing-buyer@nevermined.io` accounts; both are members of the
# `Nevermined Testing` Enterprise org so plan/agent registrations bypass
# the personal-account caps.
SUBSCRIBER_API_KEY = os.getenv(
    "TEST_SUBSCRIBER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDRkNEM5RmFBRjY2ZmI1NjI5NDY0MGZDMzI5NjgzMTdEYWQ4ZWQ4ZWQiLCJqdGkiOiIweGZjNzU1N2Q0NGNmNjEzYjI0OWRjNjZkYjk1ZGMyZmNiMmM5MTUxM2M1YmYxMWZkNjEzYmE2YTM3ZjA1ZWJmN2MiLCJleHAiOjQ5MzUxMzE2OTcsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.kwvQxOC0XLMXQlVOSQiGgr7iggma1X5QIu46odHXzp5zwNav1PQfR3j6xW1KgkVFt0tHHRjVuzVBPHG2Dahbnhw",
)

AGENT_API_KEY = os.getenv(
    "TEST_BUILDER_API_KEY",
    "sandbox-staging:eyJhbGciOiJFUzI1NksifQ.eyJpc3MiOiIweDU4MzhCNTUxMmNGOWYxMkZFOWYyYmVjY0IyMGViNDcyMTFGOUIwYmMiLCJzdWIiOiIweDM0RDdGMjBmOTYzMDI0NGFkRmI0Y2Q0ODQwY2Q1MTBGN0ZGQTczQzgiLCJqdGkiOiIweGNiZGVhMzE2OTgzYTJjOWYyNDVlYzQyZWI3MjJiNmM4ZDkxNTM2ZmYwOGNmM2QyNTg5ZjBkN2VmMGZlNjA0NTMiLCJleHAiOjQ5MzUxMzE2MjQsIm8xMXkiOiJzay1oZWxpY29uZS13amUzYXdpLW5ud2V5M2EtdzdndnY3YS1oYmh3bm1pIn0.gmI-i6GlwA0t__X1Ql5kBAjxViDas-cVY3WuNW5oTAh5I-CuALkIxznF468bfNvnwImAfgc2GrJ_PSnLJg3F7xw",
)

# Enterprise org on staging where both fixture accounts are members; passed
# through to the SDK so the `X-Current-Org-Id` header is set explicitly on
# every publish. Override via `TEST_BUILDER_ORG_ID` if a CI run should target
# a different org.
TEST_BUILDER_ORG_ID = os.getenv(
    "TEST_BUILDER_ORG_ID", "org-031a0329-ebe2-444e-ac2a-1637f694ad0b"
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


# Note: event_loop fixture is now managed by pytest-asyncio via
# asyncio_default_fixture_loop_scope = "session" in pyproject.toml
# Do not define a custom event_loop fixture as it's deprecated


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
    a Payments instance configured with the subscriber API key. The
    Enterprise org is pinned via ``organization_id`` so any writes the
    subscriber drives are scoped to the test workspace.
    """
    return Payments(
        PaymentOptions(
            nvm_api_key=SUBSCRIBER_API_KEY,
            environment=TEST_ENVIRONMENT,
            organization_id=TEST_BUILDER_ORG_ID,
        )
    )


@pytest.fixture(scope="module")
def payments_agent():
    """
    Create a Payments instance for the agent (builder).

    This fixture is shared across all E2E test files and provides
    a Payments instance configured with the agent/builder API key,
    pinned to the Enterprise test org so plan / agent registrations
    bypass the personal-account cap.
    """
    return Payments(
        PaymentOptions(
            nvm_api_key=AGENT_API_KEY,
            environment=TEST_ENVIRONMENT,
            organization_id=TEST_BUILDER_ORG_ID,
        )
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
        PaymentOptions(
            nvm_api_key=BUILDER_API_KEY,
            environment=TEST_ENVIRONMENT,
            organization_id=TEST_BUILDER_ORG_ID,
        )
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
