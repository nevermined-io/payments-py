"""X402 Protocol Supported Networks (CAIP-2 format)."""

from typing import Literal

SupportedNetworks = Literal[
    "eip155:8453",  # Base Mainnet
    "eip155:84532",  # Base Sepolia
    "stripe",  # Stripe (card-delegation)
]
