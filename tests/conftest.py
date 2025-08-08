"""Top-level pytest configuration for the whole test suite.

Ensures plugins are registered at the root (required by recent pytest
versions) and declares custom markers used across the suite.
"""

# Register third-party plugins at the root level
pytest_plugins = ["pytest_asyncio"]


def pytest_configure(config):
    """Register custom markers used in the repository."""
    config.addinivalue_line(
        "markers",
        "slow: marks tests as slow (deselect with '-m " + "not slow')",
    )
