"""
Helper functions for the Nevermined Payments protocol.
"""
import json
import re
from typing import Any, Dict
from urllib.parse import urlparse
from payments_py.common.types import Endpoint

def json_replacer(obj: Any) -> Any:
    """
    Custom JSON replacer for handling special types.
    
    Args:
        obj: The object to be serialized
        
    Returns:
        The serialized object
    """
    if isinstance(obj, bytes):
        return obj.hex()
    return obj

def snake_to_camel(snake_str: str) -> str:
    """
    Convert a snake_case string to camelCase.
    
    Args:
        snake_str: The snake_case string to convert
        
    Returns:
        The camelCase string
    """
    components = snake_str.split('_')
    return components[0] + ''.join(x.title() for x in components[1:])

def camel_to_snake(camel_str: str) -> str:
    """
    Convert a camelCase string to snake_case.
    
    Args:
        camel_str: The camelCase string to convert
        
    Returns:
        The snake_case string
    """
    import re
    return re.sub(r'(?<!^)(?=[A-Z])', '_', camel_str).lower() 

def is_ethereum_address(address: str | None) -> bool:
    """
    Check if a string is a valid Ethereum address.
    
    Args:
        address: The address to check
        
    Returns:
        True if the address is a valid Ethereum address, False otherwise
    """
    if address and re.match(r'^0x[a-fA-F0-9]{40}$', address) is not None:
        return True
    return False

def get_service_host_from_endpoints(endpoints: list[Endpoint]) -> str:
    """
    Get the service host from a list of endpoints.
    
    Args:
        endpoints: The list of endpoints
        
    Returns:
        The service host
    """
    service_host = ''
    if not endpoints:
        return service_host

    first_endpoint = next(iter(endpoints[0].values()))
    try:
        parsed_url = urlparse(first_endpoint)
        service_host = f"{parsed_url.scheme}://{parsed_url.netloc}"
    except Exception:
        service_host = ''
    return service_host

def get_random_big_int(bits: int = 53) -> int:
    """
    Generate a random big integer with the specified number of bits (default 48, max safe integer for JS is 53 bits).

    Args:
        bits (int): Number of bits for the random integer.

    Returns:
        int: A random big integer.
    """
    import secrets
    if bits > 53:
        bits = 53
    return secrets.randbits(bits)

def dict_keys_to_camel(obj: Any) -> Any:
    """
    Recursively convert all dict keys from snake_case to camelCase.

    Args:
        obj: The object (dict, list, or other) to convert
    Returns:
        The object with all dict keys in camelCase
    """
    if isinstance(obj, list):
        return [dict_keys_to_camel(item) for item in obj]
    elif isinstance(obj, dict):
        return {snake_to_camel(k): dict_keys_to_camel(v) for k, v in obj.items()}
    else:
        return obj