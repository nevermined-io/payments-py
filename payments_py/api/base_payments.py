"""
Base class for all Payments API classes.
Provides common functionality such as parsing the NVM API Key and getting the account address.
"""

import jwt
import json
from typing import Optional, Dict, Any
from enum import Enum
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.environments import get_environment
from payments_py.common.helper import dict_keys_to_camel

# Default timeout for HTTP requests in seconds (connect, read)
DEFAULT_HTTP_TIMEOUT = (10, 30)

# JavaScript's ``Number.MAX_SAFE_INTEGER`` (``2**53 - 1``). Python serializes
# ints of any size as JSON numbers, but the Nevermined backend (Node.js)
# parses any number above this threshold as a JS ``number`` that loses
# precision — and its ``@IsUint256()`` validator rejects the precision loss
# with ``BCK.COMMON.0026``. The TS SDK avoids this by storing uint256 values
# as ``bigint`` and stringifying them through a ``jsonReplacer``; Python has
# no equivalent type distinction, so we walk the body recursively and
# stringify any int outside the safe range just before serialization.
_JS_MAX_SAFE_INTEGER = (1 << 53) - 1


def _stringify_unsafe_ints(value: Any) -> Any:
    """Return ``value`` with any int outside the JS safe-integer range
    stringified (recursively into dicts and lists). Booleans are preserved
    even though ``bool`` subclasses ``int``."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        if value > _JS_MAX_SAFE_INTEGER or value < -_JS_MAX_SAFE_INTEGER:
            return str(value)
        return value
    if isinstance(value, dict):
        return {k: _stringify_unsafe_ints(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_stringify_unsafe_ints(v) for v in value]
    return value


# Header used by the Nevermined backend to resolve the active organization
# context for an authenticated request. See `CurrentOrgContextGuard` in
# `apps/api/src/common/guards/current-org-context.guard.ts` (nvm-monorepo).
CURRENT_ORG_ID_HEADER = "X-Current-Org-Id"


class BasePaymentsAPI:
    """
    Base class extended by all Payments API classes.
    It provides common functionality such as parsing the NVM API Key and getting the account address.
    """

    def __init__(self, options: PaymentOptions):
        """
        Initialize the base payments API.

        Args:
            options: The options to initialize the payments class
        """
        self.nvm_api_key = options.nvm_api_key
        self.return_url = options.return_url or ""
        self.environment = get_environment(options.environment)
        self.environment_name = options.environment
        self.app_id = options.app_id
        self.version = options.version
        self.account_address: Optional[str] = None
        self.helicone_api_key: str = None
        self.is_browser_instance = True
        self.current_organization_id: Optional[str] = options.organization_id
        self._parse_nvm_api_key()

    def _parse_nvm_api_key(self) -> None:
        """
        Parse the NVM API Key to get the account address and helicone API key.

        Raises:
            PaymentsError: If the API key is invalid or missing required fields
        """
        try:
            [_, key] = self.nvm_api_key.split(":")
            decoded_jwt = jwt.decode(key, options={"verify_signature": False})
            self.account_address = decoded_jwt.get("sub")
            helicone_key = decoded_jwt.get("o11y")
            if not helicone_key:
                raise PaymentsError.validation(
                    "Helicone API key not found in NVM API Key"
                )
            self.helicone_api_key = helicone_key
        except PaymentsError:
            raise
        except Exception as e:
            raise PaymentsError.validation(f"Invalid NVM API Key: {str(e)}")

    def get_account_address(self) -> Optional[str]:
        """
        Get the account address associated with the NVM API Key.

        Returns:
            The account address extracted from the NVM API Key
        """
        return self.account_address

    def get_organization_id(self) -> Optional[str]:
        """Return the org id pinned for every authenticated backend call.

        ``None`` means no pinned workspace — the backend falls back to the
        API key's org tag or the caller's most-recent active membership.
        """
        return self.current_organization_id

    def set_organization_id(self, organization_id: Optional[str]) -> None:
        """Pin (or clear) the organization context used for every authenticated request.

        When set, the SDK forwards the value as the
        ``X-Current-Org-Id`` header so the backend scopes published
        agents, plans, and other workspace-aware resources to this
        organization.

        Pass ``None`` to clear the pin and let the backend fall back to
        the API key's org tag or the caller's most-recent active
        membership.

        For one-off targeting on publish, prefer the per-call
        ``organization_id`` argument on
        :meth:`payments.agents.register_agent` /
        :meth:`payments.plans.register_plan` / similar.
        """
        self.current_organization_id = organization_id

    def pydantic_to_dict(self, obj):
        """
        Recursively convert Pydantic models and Enums to serializable dicts.
        """
        if isinstance(obj, list):
            return [self.pydantic_to_dict(i) for i in obj]
        elif isinstance(obj, dict):
            return {
                k: self.pydantic_to_dict(v) for k, v in obj.items() if v is not None
            }
        elif hasattr(obj, "model_dump"):
            # Pydantic v2
            return self.pydantic_to_dict(obj.model_dump(exclude_none=True))
        elif hasattr(obj, "dict"):
            # Pydantic v1
            return self.pydantic_to_dict(obj.dict(exclude_none=True))
        elif isinstance(obj, Enum):
            return obj.value
        else:
            return obj

    def get_backend_http_options(
        self,
        method: str,
        body: Optional[Dict[str, Any]] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Get HTTP options for backend requests.

        Args:
            method: HTTP method
            body: Optional request body
            extra_headers: Optional per-call header overrides. Use
                ``{"X-Current-Org-Id": org_id}`` to target a specific
                workspace for one call without mutating the instance-level
                pin.

        Returns:
            HTTP options object
        """
        # Disable SSL verification for development/staging environments
        # For now, disable SSL verification for all environments to handle
        # self-signed certificates
        verify_ssl = False

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.nvm_api_key}",
        }
        if self.current_organization_id:
            headers[CURRENT_ORG_ID_HEADER] = self.current_organization_id
        if extra_headers:
            headers.update(extra_headers)

        options = {
            "headers": headers,
            "verify": verify_ssl,
            "timeout": DEFAULT_HTTP_TIMEOUT,
        }
        if body:
            # Convert to camelCase for consistency with TypeScript, then
            # stringify any int the JS backend would lose precision on.
            camel_body = dict_keys_to_camel(body)
            safe_body = _stringify_unsafe_ints(camel_body)
            options["data"] = json.dumps(safe_body)
        return options

    def get_public_http_options(
        self, method: str, body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get HTTP options for public backend requests (no authorization header).

        Args:
            method: HTTP method
            body: Optional request body

        Returns:
            HTTP options object
        """
        verify_ssl = False

        options = {
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
            "verify": verify_ssl,
            "timeout": DEFAULT_HTTP_TIMEOUT,
        }
        if body:
            # Convert to camelCase for consistency with TypeScript, then
            # stringify any int the JS backend would lose precision on.
            camel_body = dict_keys_to_camel(body)
            safe_body = _stringify_unsafe_ints(camel_body)
            options["data"] = json.dumps(safe_body)
        return options
