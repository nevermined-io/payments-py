"""X402 Protocol Supported Payment Schemes.

Nevermined supports multiple payment schemes:
- nvm:erc4337: ERC-4337 account abstraction for crypto credit-based payments
- nvm:card-delegation: Card delegation for fiat payments (Stripe or Braintree).
  The ``network`` field in the x402 token differentiates: ``'stripe'`` or ``'braintree'``.
"""

from typing import Literal, Optional

X402SchemeType = Literal["nvm:erc4337", "nvm:card-delegation"]
SupportedSchemes = X402SchemeType  # backward-compat alias

# Default network mapping (backward-compat: defaults to Base Sepolia)
X402_SCHEME_NETWORKS: dict[str, str] = {
    "nvm:erc4337": "eip155:84532",
    "nvm:card-delegation": "stripe",
}

# Environment-specific network for the erc4337 scheme
_ERC4337_NETWORK_BY_ENV: dict[str, str] = {
    "sandbox": "eip155:84532",  # Base Sepolia
    "staging_sandbox": "eip155:84532",  # Base Sepolia
    "live": "eip155:8453",  # Base Mainnet
    "staging_live": "eip155:8453",  # Base Mainnet
}


def get_default_network(scheme: str, environment: Optional[str] = None) -> str:
    """Return the default network for a scheme, accounting for the environment.

    For ``nvm:erc4337``, the network depends on the environment:
    - sandbox / staging_sandbox → ``eip155:84532`` (Base Sepolia)
    - live / staging_live → ``eip155:8453`` (Base Mainnet)

    Falls back to ``X402_SCHEME_NETWORKS`` when no environment is given.
    """
    if scheme == "nvm:erc4337" and environment:
        return _ERC4337_NETWORK_BY_ENV.get(environment, "eip155:84532")
    return X402_SCHEME_NETWORKS.get(scheme, "eip155:84532")


def is_valid_scheme(s: object) -> bool:
    """Type guard to check if a value is a valid x402 scheme type."""
    return s in ("nvm:erc4337", "nvm:card-delegation")
