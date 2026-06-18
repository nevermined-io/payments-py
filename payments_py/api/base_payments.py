"""
Base class for all Payments API classes.
Provides common functionality such as parsing the NVM API Key and getting the account address.
"""

import jwt
import json
import logging
import warnings
from typing import Optional, Dict, Any
from enum import Enum
from payments_py.common.api_version import API_VERSION_HEADER, LOCKED_API_VERSION
from payments_py.common.payments_error import PaymentsError
from payments_py.common.types import PaymentOptions
from payments_py.environments import (
    EnvironmentName,
    environment_from_api_key,
    get_environment,
)
from payments_py.common.helper import dict_keys_to_camel

logger = logging.getLogger(__name__)

# Default environment when neither the API-key prefix nor the deprecated
# ``environment`` option resolves one (e.g. a local/custom dev key with an
# unrecognized prefix and no ``environment`` passed).
_DEFAULT_ENVIRONMENT: EnvironmentName = "custom"

# Guards the once-per-process stdlib logging nudge for the deprecated
# ``environment`` option (``warnings.warn`` already dedupes by message+location;
# this keeps the logging channel from repeating on every sub-API construction).
_environment_deprecation_logged = False

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

# Allowlist for the per-call ``extra_headers`` argument on
# :meth:`get_backend_http_options`. Mirrors the TS source-of-truth
# (`ALLOWED_EXTRA_HEADERS` in `payments/src/api/base-payments.ts`): without
# this filter a caller could inject ``Authorization`` / ``Content-Type``
# through the new per-call header channel and override the SDK's own
# auth, escalating any per-call workspace targeting path into a
# header-injection surface.
ALLOWED_EXTRA_HEADERS = frozenset({CURRENT_ORG_ID_HEADER})


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
        # Preserve the raw (possibly None) ``environment`` option so internal
        # re-inits (e.g. ``Payments._build_options``) reproduce the caller's
        # intent without re-deriving ``custom`` into a spurious deprecation
        # warning.
        self._environment_option = options.environment
        self.environment_name = self._resolve_environment(
            options.nvm_api_key, options.environment
        )
        self.environment = get_environment(self.environment_name)
        self.app_id = options.app_id
        self.version = options.version
        # Backend API version (monorepo MAJOR.MINOR) declared on every
        # request via the ``Nevermined-Version`` header. Defaults to the
        # version this SDK release is built/tested against.
        self.api_version: str = options.api_version or LOCKED_API_VERSION
        self.account_address: Optional[str] = None
        self.helicone_api_key: str = None
        self.is_browser_instance = True
        self.current_organization_id: Optional[str] = options.organization_id
        self._parse_nvm_api_key()

    @staticmethod
    def _resolve_environment(
        nvm_api_key: Optional[str], environment_option: Optional[str]
    ) -> EnvironmentName:
        """Resolve the effective SDK environment.

        Precedence (non-breaking deprecation of the ``environment`` option):

        1. The API-key prefix (``<prefix>:<jwt>``) when recognized — it always
           wins. If ``environment_option`` was also passed it is ignored, and a
           warning notes the override.
        2. Otherwise the deprecated ``environment`` option, if provided — its
           use emits a deprecation warning.
        3. Otherwise :data:`_DEFAULT_ENVIRONMENT` (``"custom"``).

        Args:
            nvm_api_key: The NVM API key (its prefix drives resolution).
            environment_option: The deprecated ``environment`` init option.

        Returns:
            The resolved :data:`EnvironmentName`.
        """
        derived = environment_from_api_key(nvm_api_key)
        if derived is not None:
            if environment_option is not None:
                # Key prefix wins; the passed option is ignored. Note the
                # override explicitly when the two disagree.
                detail = (
                    f"ignoring the passed '{environment_option}'"
                    if environment_option != derived
                    else "the passed value matched and was redundant"
                )
                BasePaymentsAPI._warn_environment_deprecated(
                    "The 'environment' option is deprecated and is now derived "
                    f"from the API-key prefix. Using '{derived}' from the API "
                    f"key ({detail}). Remove the 'environment' option."
                )
            return derived

        if environment_option is not None:
            BasePaymentsAPI._warn_environment_deprecated(
                "The 'environment' option is deprecated; the environment is now "
                "derived from the API-key prefix. The key prefix was not "
                f"recognized, so falling back to the passed '{environment_option}'."
            )
            return environment_option

        return _DEFAULT_ENVIRONMENT

    @staticmethod
    def _warn_environment_deprecated(message: str) -> None:
        """Emit the ``environment``-deprecation nudge.

        Uses ``FutureWarning`` (not ``DeprecationWarning``) for runtime
        visibility — ``DeprecationWarning`` is filtered out by default outside
        ``__main__``, so agents under FastAPI / gunicorn / Docker workers would
        never see it (same rationale as ``payments_py/x402/token.py``). Also
        logs once per process so the nudge reaches log-based observability.
        """
        global _environment_deprecation_logged
        warnings.warn(message, FutureWarning, stacklevel=3)
        if not _environment_deprecation_logged:
            logger.warning(message)
            _environment_deprecation_logged = True

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
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.nvm_api_key}",
            API_VERSION_HEADER: self.api_version,
        }
        if self.current_organization_id:
            headers[CURRENT_ORG_ID_HEADER] = self.current_organization_id
        if extra_headers:
            # Filter through the allowlist so a per-call header argument
            # can't override Authorization / Content-Type or otherwise
            # poison the transport. Mirror of the TS source-of-truth
            # (`ALLOWED_EXTRA_HEADERS` in `payments/src/api/base-payments.ts`).
            headers.update(
                {k: v for k, v in extra_headers.items() if k in ALLOWED_EXTRA_HEADERS}
            )

        # Leave TLS verification on (requests' default). For environments with
        # self-signed certs, point ``REQUESTS_CA_BUNDLE`` at the CA cert.
        options = {
            "headers": headers,
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
        # Leave TLS verification on (requests' default). For environments with
        # self-signed certs, point ``REQUESTS_CA_BUNDLE`` at the CA cert.
        options = {
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                API_VERSION_HEADER: self.api_version,
            },
            "timeout": DEFAULT_HTTP_TIMEOUT,
        }
        if body:
            # Convert to camelCase for consistency with TypeScript, then
            # stringify any int the JS backend would lose precision on.
            camel_body = dict_keys_to_camel(body)
            safe_body = _stringify_unsafe_ints(camel_body)
            options["data"] = json.dumps(safe_body)
        return options
