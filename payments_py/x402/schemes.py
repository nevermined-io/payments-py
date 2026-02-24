"""X402 Protocol Supported Payment Schemes.

Nevermined supports multiple payment schemes:
- nvm:erc4337: ERC-4337 account abstraction for crypto credit-based payments
- nvm:card-delegation: Stripe card delegation for fiat payments
"""

from typing import Literal

X402SchemeType = Literal["nvm:erc4337", "nvm:card-delegation"]
SupportedSchemes = X402SchemeType  # backward-compat alias

X402_SCHEME_NETWORKS: dict[str, str] = {
    "nvm:erc4337": "eip155:84532",
    "nvm:card-delegation": "stripe",
}


def is_valid_scheme(s: object) -> bool:
    """Type guard to check if a value is a valid x402 scheme type."""
    return s in ("nvm:erc4337", "nvm:card-delegation")
