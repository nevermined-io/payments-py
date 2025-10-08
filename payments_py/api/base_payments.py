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
        self, method: str, body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Get HTTP options for backend requests.

        Args:
            method: HTTP method
            body: Optional request body

        Returns:
            HTTP options object
        """
        # Disable SSL verification for development/staging environments
        # For now, disable SSL verification for all environments to handle
        # self-signed certificates
        verify_ssl = False

        options = {
            "headers": {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.nvm_api_key}",
            },
            "verify": verify_ssl,
        }
        if body:
            # Convert to camelCase for consistency with TypeScript
            camel_body = dict_keys_to_camel(body)
            options["data"] = json.dumps(camel_body)
        return options
