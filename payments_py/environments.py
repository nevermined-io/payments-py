import os
from dataclasses import dataclass
from typing import Literal, Union


@dataclass
class EnvironmentInfo:
    """
    Data class to store environment information.

    Attributes:
        frontend (str): Frontend URL
        backend (str): Backend URL
        proxy (str): Proxy URL
    """

    backend: str
    proxy: str
    frontend: str = None


# Zero address constant
ZeroAddress = "0x0000000000000000000000000000000000000000"

# Supported environment names
EnvironmentName = Literal[
    "sandbox",
    "live",
    "staging_sandbox",
    "staging_live",
    "custom",
]

# Environments dictionary
Environments = {
    "staging_sandbox": EnvironmentInfo(
        frontend="https://staging.nevermined.app",
        backend="https://api-base-sepolia.staging.nevermined.app",
        proxy="https://proxy.staging.nevermined.app",
    ),
    "staging_live": EnvironmentInfo(
        frontend="https://staging.nevermined.app",
        backend="https://api-base-mainnet.staging.nevermined.app",
        proxy="https://proxy.staging.nevermined.app",
    ),
    "sandbox": EnvironmentInfo(
        frontend="https://nevermined.app",
        backend="https://api-base-sepolia.nevermined.app",
        proxy="https://proxy.testing.nevermined.app",
    ),
    "live": EnvironmentInfo(
        frontend="https://nevermined.app",
        backend="https://api-base-mainnet.nevermined.app",
        proxy="https://proxy.nevermined.app",
    ),
    "custom": EnvironmentInfo(
        frontend=os.getenv("NVM_FRONTEND_URL", "http://localhost:3000"),
        backend=os.getenv("NVM_BACKEND_URL", "http://localhost:3001"),
        proxy=os.getenv("NVM_PROXY_URL", "https://localhost:443"),
    ),
}


def get_environment(name: EnvironmentName) -> EnvironmentInfo:
    """
    Get the environment configuration by name.

    Args:
        name: The name of the environment.

    Returns:
        EnvironmentInfo: The environment configuration.

    Raises:
        ValueError: If the environment name is not defined.
    """
    if name not in Environments:
        raise ValueError(f"Environment '{name}' is not defined.")
    return Environments[name]
