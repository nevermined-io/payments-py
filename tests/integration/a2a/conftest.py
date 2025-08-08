"""Shared test fixtures for AnyIO backend forcing asyncio only."""

import pytest


@pytest.fixture
def anyio_backend():  # noqa: D401
    """Force AnyIO to use asyncio backend to avoid trio dependency."""
    return "asyncio"
