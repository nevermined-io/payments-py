"""
Helper functions for the Nevermined Payments protocol.
"""

from typing import Any


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
    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def camel_to_snake(camel_str: str) -> str:
    """
    Convert a camelCase string to snake_case.

    Args:
        camel_str: The camelCase string to convert

    Returns:
        The snake_case string
    """
    import re

    return re.sub(r"(?<!^)(?=[A-Z])", "_", camel_str).lower()


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
