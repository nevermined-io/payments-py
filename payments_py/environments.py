import os
from dataclasses import dataclass
from typing import Literal, Optional


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


# Known API-key prefixes mapped to their SDK environment name. This is the
# inverse of the backend's ``addPrefixToToken`` (nvm-monorepo
# ``apps/api/src/common/helpers/utils.ts``), which builds the prefix as
# ``{environment}`` or ``{environment}-{deploymentName}`` (the deployment
# segment is omitted for ``production``). So ``sandbox-staging`` is the
# ``staging`` deployment of the ``sandbox`` environment → ``staging_sandbox``.
# Keep this table in sync with the TS SDK (payments#399) — both must map the
# same prefixes to the same environment names.
_API_KEY_PREFIX_TO_ENVIRONMENT: dict[str, EnvironmentName] = {
    "sandbox-staging": "staging_sandbox",
    "live-staging": "staging_live",
    "sandbox": "sandbox",
    "live": "live",
}


def environment_from_api_key(nvm_api_key: Optional[str]) -> Optional[EnvironmentName]:
    """Derive the SDK environment from an NVM API key's prefix.

    Keys are ``<prefix>:<jwt>``. The prefix encodes the environment the key was
    minted for (see ``_API_KEY_PREFIX_TO_ENVIRONMENT``). Returns the mapped
    :data:`EnvironmentName`, or ``None`` when the key is missing, has no prefix,
    or carries an unrecognized prefix (e.g. local/custom dev keys) — callers
    fall back to the deprecated ``environment`` option in that case.

    Args:
        nvm_api_key: The NVM API key, or ``None``.

    Returns:
        The mapped environment name, or ``None`` if it cannot be derived.
    """
    if not nvm_api_key or ":" not in nvm_api_key:
        return None
    prefix = nvm_api_key.split(":", 1)[0].lower()
    return _API_KEY_PREFIX_TO_ENVIRONMENT.get(prefix)


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
