import os

class EnvironmentInfo:
    """
    Data class to store environment information.

    Attributes:
        frontend (str): Frontend URL
        backend (str): Backend URL
        proxy (str): Proxy URL
    """
    def __init__(self, frontend=None, backend=None, proxy=None):
        self.frontend = frontend
        self.backend = backend
        self.proxy = proxy

# Zero address constant
ZeroAddress = "0x0000000000000000000000000000000000000000"

# Supported environment names
ENVIRONMENT_NAMES = [
    "local",
    "staging",
    "testing",
    "arbitrum",
    "base",
    "base-sepolia",
    "custom",
]

# Environments dictionary
Environments = {
    "local": EnvironmentInfo(
        frontend="http://localhost:3000",
        backend="http://localhost:3001",
        proxy="https://localhost:443",
    ),
    "staging": EnvironmentInfo(
        frontend="https://staging.nevermined.app",
        backend="https://api.staging.nevermined.app",
        proxy="https://proxy.staging.nevermined.app",
    ),
    "testing": EnvironmentInfo(
        frontend="https://testing.nevermined.app",
        backend="https://api.testing.nevermined.app",
        proxy="https://proxy.testing.nevermined.app",
    ),
    "arbitrum": EnvironmentInfo(
        frontend="https://nevermined.app",
        backend="https://one-backend.arbitrum.nevermined.app",
        proxy="https://proxy.arbitrum.nevermined.app",
    ),
    "base": EnvironmentInfo(
        frontend="https://base.nevermined.app",
        backend="https://one-backend.base.nevermined.app",
        proxy="https://proxy.base.nevermined.app",
    ),
    "base-sepolia": EnvironmentInfo(
        frontend="https://base-sepolia.nevermined.app",
        backend="https://one-backend.base-sepolia.nevermined.app",
        proxy="https://proxy.base-sepolia.nevermined.app",
    ),
    "custom": EnvironmentInfo(
        frontend=os.getenv("NVM_FRONTEND_URL", "http://localhost:3000"),
        backend=os.getenv("NVM_BACKEND_URL", "http://localhost:3001"),
        proxy=os.getenv("NVM_PROXY_URL", "https://localhost:443"),
    ),
}

def get_environment(name):
    """
    Get the environment configuration by name.

    Args:
        name (str): The name of the environment.

    Returns:
        EnvironmentInfo: The environment configuration.

    Raises:
        ValueError: If the environment name is not defined.
    """
    if name not in Environments:
        raise ValueError(f"Environment '{name}' is not defined.")
    return Environments[name]
