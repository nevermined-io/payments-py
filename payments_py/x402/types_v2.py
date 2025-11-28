"""
Extended x402 v2 types with extension support.

This module extends the base x402 v2 types to include the extensions field
that is present in TypeScript and Go implementations but not yet in Python.

When official Python v2 extension support is added, we can migrate to use
those types directly.

Note: This is a temporary implementation until x402's Python package includes
official extension support. We're following the TypeScript/Go pattern from:
https://github.com/coinbase/x402/tree/v2-development
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel
from typing import Any, Dict, List, Optional


class Extension(BaseModel):
    """
    x402 v2 extension structure.

    Extensions follow the info + schema pattern where:
    - info: Contains the actual extension data (values, metadata)
    - schema: JSON Schema that validates the info structure

    This pattern allows for:
    - Self-validating extensions
    - Machine-readable metadata
    - Consistent structure across different extension types

    Example:
        >>> extension = Extension(
        ...     info={"plan_id": "123", "agent_id": "456"},
        ...     schema={
        ...         "$schema": "https://json-schema.org/draft/2020-12/schema",
        ...         "type": "object",
        ...         "properties": {
        ...             "plan_id": {"type": "string"},
        ...             "agent_id": {"type": "string"}
        ...         }
        ...     }
        ... )
    """

    info: Dict[str, Any]
    schema: Dict[str, Any]

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class ResourceInfo(BaseModel):
    """
    Resource information in PaymentRequired response.

    Provides metadata about the resource being payment-protected.
    """

    url: str
    description: Optional[str] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class PaymentRequiredResponseV2(BaseModel):
    """
    x402 v2 Payment Required Response with extensions support.

    This is returned by a server with a 402 status code to indicate
    that payment is required to access the resource.

    Extends the base x402PaymentRequiredResponse to include:
    - resource: Detailed resource information (not just URL)
    - extensions: Optional extension metadata

    The extensions field allows servers to attach additional metadata
    about payment requirements, discovery information, or other features.

    Example:
        >>> from payments_py.x402.extensions.nevermined import (
        ...     declare_nevermined_extension,
        ...     NEVERMINED
        ... )
        >>>
        >>> response = PaymentRequiredResponseV2(
        ...     x402_version=2,
        ...     resource=ResourceInfo(url="https://api.example.com/data"),
        ...     accepts=[...],  # List of payment requirements
        ...     extensions={
        ...         NEVERMINED: declare_nevermined_extension(
        ...             plan_id="123",
        ...             agent_id="456",
        ...             max_amount="2"
        ...         )
        ...     }
        ... )
    """

    x402_version: int
    resource: ResourceInfo
    accepts: List[
        Any
    ]  # List of payment requirements (using Any to avoid x402 dependency)
    extensions: Optional[Dict[str, Extension]] = None
    error: Optional[str] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class PaymentPayloadV2(BaseModel):
    """
    x402 v2 Payment Payload with extensions support.

    This is sent by the client in the X-PAYMENT header to pay for a resource.

    Extends the base x402 PaymentPayload to include the extensions field.
    The client copies extensions from the PaymentRequired response into
    this payload, allowing the payment information to flow through to
    the facilitator for processing.

    Flow:
        1. Server includes extensions in PaymentRequired response
        2. Client copies extensions to PaymentPayload
        3. Server forwards to facilitator for verification/settlement
        4. Facilitator extracts and processes extension data

    Example:
        >>> payload = PaymentPayloadV2(
        ...     x402_version=2,
        ...     scheme="exact",
        ...     network="base-sepolia",
        ...     payload={...},  # Scheme-specific payload
        ...     resource={"url": "https://api.example.com/data"},
        ...     extensions={
        ...         "nevermined": {
        ...             "info": {...},
        ...             "schema": {...}
        ...         }
        ...     }
        ... )
    """

    x402_version: int
    scheme: str
    network: str
    payload: Any  # Scheme-dependent payload (e.g., ExactPaymentPayload)
    resource: Optional[Dict[str, str]] = None
    extensions: Optional[Dict[str, Extension]] = None

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


# Type aliases for convenience
Extensions = Dict[str, Extension]

__all__ = [
    "Extension",
    "ResourceInfo",
    "PaymentRequiredResponseV2",
    "PaymentPayloadV2",
    "Extensions",
]
