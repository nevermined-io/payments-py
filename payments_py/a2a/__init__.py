"""A2A helpers integrated with Nevermined Payments (Python)."""

from .client_registry import ClientRegistry
from .payments_client import PaymentsClient
from .agent_card import build_payment_agent_card

# IMPORTANT: we avoid importing server & handler at package-import time to prevent
# optional dependencies (FastAPI, uvicorn) or circular imports during unit tests.
# They can be imported lazily by user code when needed.

__all__ = [
    "ClientRegistry",
    "PaymentsClient",
    "build_payment_agent_card",
]
