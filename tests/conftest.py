"""Top-level pytest configuration for the whole test suite.

Ensures plugins are registered at the root (required by recent pytest
versions) and declares custom markers used across the suite.
"""

import pytest

# Register third-party plugins at the root level
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Register custom markers used in the repository."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m " + "not slow')",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-mark tests under tests/e2e as slow to allow -m "not slow" filtering.

    This ensures E2E tests are excluded from unit/integration runs even if
    directory-local conftest is not picked up in some environments.
    """
    for item in items:
        nodeid = getattr(item, "nodeid", "")
        fspath = getattr(getattr(item, "fspath", None), "strpath", "")
        if "/tests/e2e/" in nodeid or "/tests/e2e/" in fspath:
            item.add_marker(pytest.mark.slow)
