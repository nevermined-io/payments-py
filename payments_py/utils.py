"""
Utility functions for the payments library.
"""

import uuid
import time
import secrets
from urllib.parse import urlparse
import jwt
from typing import Optional, Dict, Any, List


def snake_to_camel(name):
    """
    Convert snake_case to camelCase.

    :param name: str
    :return: str
    """
    components = name.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def is_ethereum_address(address: str) -> bool:
    """
    Check if a string is a valid Ethereum address.

    Args:
        address: The address to validate

    Returns:
        True if the address is valid, False otherwise
    """
    if not address:
        return False

    # Basic Ethereum address validation
    if not address.startswith("0x"):
        return False

    if len(address) != 42:  # 0x + 40 hex characters
        return False

    try:
        int(address[2:], 16)  # Check if the rest is valid hex
        return True
    except ValueError:
        return False


def get_random_big_int(bits: int = 128) -> int:
    """
    Generate a random big integer with the specified number of bits.

    Args:
        bits: The number of bits for the random integer (default: 128)

    Returns:
        A random big integer
    """
    bytes_needed = (bits + 7) // 8
    random_bytes = secrets.token_bytes(bytes_needed)

    result = 0
    for byte in random_bytes:
        result = (result << 8) | byte

    # Ensure we don't exceed the requested bit length
    mask = (1 << bits) - 1
    return result & mask


def generate_step_id() -> str:
    """
    Generate a random step id.

    :return: str
    """
    return f"step-{str(uuid.uuid4())}"


def is_step_id_valid(step_id: str) -> bool:
    """
    Check if the step id has the right format.

    :param step_id: str
    :return: bool
    """
    if not step_id.startswith("step-"):
        return False
    try:
        uuid.UUID(step_id[5:])
        return True
    except ValueError:
        return False


def sleep(ms: int) -> None:
    """
    Sleep for the specified number of milliseconds.

    Args:
        ms: The number of milliseconds to sleep
    """
    time.sleep(ms / 1000.0)


def json_replacer(key: str, value: Any) -> Any:
    """
    Custom JSON replacer function to handle special values.

    Args:
        key: The key being serialized
        value: The value being serialized

    Returns:
        The value to serialize, or None to exclude the key-value pair
    """
    if value is None:
        return None
    return value


def decode_access_token(access_token: str) -> Optional[Dict[str, Any]]:
    """
    Decode an access token to extract wallet address and plan ID.

    Args:
        access_token: The access token to decode

    Returns:
        The decoded token data or None if invalid
    """
    try:
        # Decode without verification since we're just extracting data
        decoded = jwt.decode(access_token, options={"verify_signature": False})
        return decoded
    except Exception:
        return None


def get_query_protocol_endpoints(server_host: str):
    """
    Returns the list of endpoints that are used by agents/services implementing the Nevermined Query Protocol.

    :param server_host: str
    :return: list
    """
    url = urlparse(server_host)
    origin = f"{url.scheme}://{url.netloc}"
    return [
        {"POST": f"{origin}/api/v1/agents/(.*)/tasks"},
        {"GET": f"{origin}/api/v1/agents/(.*)/tasks/(.*)"},
    ]


def get_ai_hub_open_api_url(server_host: str) -> str:
    """
    Returns the URL to the OpenAPI documentation of the AI Hub.

    :param server_host: str
    :return: str
    """
    url = urlparse(server_host)
    origin = f"{url.scheme}://{url.netloc}"
    return f"{origin}/api/v1/rest/docs-json"


def get_service_host_from_endpoints(endpoints: List[Dict[str, str]]) -> Optional[str]:
    """
    Extract the service host from a list of endpoints.

    Args:
        endpoints: List of endpoint dictionaries

    Returns:
        The service host URL or None if not found
    """
    if not endpoints:
        return None

    # Try to extract host from the first endpoint
    first_endpoint = endpoints[0]
    for method, url in first_endpoint.items():
        if url:
            parsed = urlparse(url)
            return f"{parsed.scheme}://{parsed.netloc}"

    return None
