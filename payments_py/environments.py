import os
from dataclasses import dataclass
from typing import Literal


@dataclass
class EnvironmentInfo:
    """
    Data class to store environment information.

    Attributes:
        frontend (str): Frontend URL
        backend (str): Backend URL
        proxy (str): Proxy URL
        helicone_url (str): Helicone URL
    """

    backend: str
    proxy: str
    helicone_url: str
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
        frontend="https://nevermined.dev",
        backend="https://api.sandbox.nevermined.dev",
        proxy="https://proxy.sandbox.nevermined.dev",
        helicone_url="https://helicone.nevermined.dev",
    ),
    "staging_live": EnvironmentInfo(
        frontend="https://nevermined.dev",
        backend="https://api.live.nevermined.dev",
        proxy="https://proxy.live.nevermined.dev",
        helicone_url="https://helicone.nevermined.dev",
    ),
    "sandbox": EnvironmentInfo(
        frontend="https://nevermined.app",
        backend="https://api.sandbox.nevermined.app",
        proxy="https://proxy.sandbox.nevermined.app",
        helicone_url="https://helicone.nevermined.dev",
    ),
    "live": EnvironmentInfo(
        frontend="https://nevermined.app",
        backend="https://api.live.nevermined.app",
        proxy="https://proxy.live.nevermined.app",
        helicone_url="https://helicone.nevermined.dev",
    ),
    "custom": EnvironmentInfo(
        frontend=os.getenv("NVM_FRONTEND_URL", "http://localhost:3000"),
        backend=os.getenv("NVM_BACKEND_URL", "http://localhost:3001"),
        proxy=os.getenv("NVM_PROXY_URL", "https://localhost:443"),
        helicone_url=os.getenv("HELICONE_URL", "http://localhost:8585"),
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
