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


######################## OBSERVABILITY ########################

def generate_deterministic_agent_id(agent_id: str, class_name: Optional[str] = None) -> str:
    """
    Generate deterministic agent ID: if no class_name, return agent_id as is;
    if class_name provided, hash it.

    Args:
        agent_id: The agent ID
        class_name: Optional class name to hash

    Returns:
        The deterministic agent ID
    """
    if not class_name:
        return agent_id

    import hashlib
    hash_obj = hashlib.sha256(class_name.encode()).hexdigest()[:32]
    # Format as UUID: 8-4-4-4-12
    return f"{hash_obj[:8]}-{hash_obj[8:12]}-{hash_obj[12:16]}-{hash_obj[16:20]}-{hash_obj[20:32]}"


def generate_session_id() -> str:
    """
    Generate random session ID.

    Returns:
        A random UUID string
    """
    return str(uuid.uuid4())


def log_session_info(agent_id: str, session_id: str, agent_name: str = "SceneTechnicalExtractor") -> None:
    """
    Log session information.

    Args:
        agent_id: The agent ID
        session_id: The session ID
        agent_name: The agent name (default: "SceneTechnicalExtractor")
    """
    import os
    import json
    from datetime import datetime

    timestamp = datetime.utcnow().isoformat() + "Z"
    logs_dir = os.path.join(os.path.dirname(__file__), "logs")

    # Ensure logs directory exists
    if not os.path.exists(logs_dir):
        os.makedirs(logs_dir, exist_ok=True)

    log_entry = {
        "timestamp": timestamp,
        "agentId": agent_id,
        "sessionId": session_id,
        "agentName": agent_name,
    }

    log_file = os.path.join(logs_dir, "session_info.log")
    with open(log_file, "a", encoding="utf-8") as f:
        f.write(json.dumps(log_entry) + "\n")

    print(f"[{timestamp}] Agent: {agent_name} | Session: {session_id} | Agent ID: {agent_id}")
