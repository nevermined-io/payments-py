"""
Validation helpers for Nevermined extensions.

Provides functions to validate Nevermined extension data against JSON Schema.
"""

from typing import List, Optional
from typing_extensions import TypedDict
from jsonschema import validate, ValidationError

from .types import NeverminedExtension


class ValidationResult(TypedDict):
    """Result of extension validation."""

    valid: bool
    errors: Optional[List[str]]


def validate_nevermined_extension(extension: NeverminedExtension) -> ValidationResult:
    """
    Validate a Nevermined extension's info against its schema.

    Uses JSON Schema validation to ensure the extension data is properly
    structured and contains all required fields.

    Args:
        extension: The Nevermined extension to validate (info + schema)

    Returns:
        ValidationResult with valid flag and optional error messages

    Example:
        >>> from payments_py.x402.extensions.nevermined import (
        ...     declare_nevermined_extension,
        ...     validate_nevermined_extension
        ... )
        >>>
        >>> extension = declare_nevermined_extension(
        ...     plan_id="123",
        ...     agent_id="456",
        ...     max_amount="2"
        ... )
        >>>
        >>> result = validate_nevermined_extension(extension)
        >>> if result["valid"]:
        ...     print("Extension is valid")
        ... else:
        ...     print(f"Validation errors: {result['errors']}")
    """
    try:
        # Handle both dict and Pydantic model formats
        if isinstance(extension, dict):
            info = extension["info"]
            schema = extension["schema"]
        else:
            # Pydantic Extension model
            info = extension.info
            schema = extension.schema

        # Validate info against schema using JSON Schema
        validate(instance=info, schema=schema)
        return {"valid": True, "errors": None}

    except ValidationError as e:
        # Validation failed - construct helpful error message
        error_msg = f"{e.json_path}: {e.message}" if hasattr(e, "json_path") else str(e)
        return {"valid": False, "errors": [error_msg]}

    except Exception as e:
        # Unexpected error during validation
        return {"valid": False, "errors": [f"Validation error: {str(e)}"]}


__all__ = ["validate_nevermined_extension", "ValidationResult"]
