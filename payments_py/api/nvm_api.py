"""
Nevermined Payments API endpoints and backend client
"""

import requests
import jwt
from typing import Optional, Dict, Any
from urllib.parse import urlparse
from payments_py.common.helper import is_ethereum_address

# Plan endpoints
API_URL_REGISTER_PLAN = "/api/v1/protocol/plans"
API_URL_GET_PLAN = "/api/v1/protocol/plans/{plan_id}"
API_URL_PLAN_BALANCE = "/api/v1/protocol/plans/{plan_id}/balance/{holder_address}"
API_URL_ORDER_PLAN = "/api/v1/protocol/plans/{plan_id}/order"
API_URL_MINT_PLAN = "/api/v1/protocol/plans/mint"
API_URL_MINT_EXPIRABLE_PLAN = "/api/v1/protocol/plans/mintExpirable"
API_URL_BURN_PLAN = "/api/v1/protocol/plans/burn"

# Agent endpoints
API_URL_REGISTER_AGENT = "/api/v1/protocol/agents"
API_URL_GET_AGENT = "/api/v1/protocol/agents/{agent_id}"
API_URL_SEARCH_AGENTS = "/api/v1/protocol/agents/search"
API_URL_ADD_PLAN_AGENT = "/api/v1/protocol/agents/{agent_id}/plan/{plan_id}"
API_URL_REMOVE_PLAN_AGENT = "/api/v1/protocol/agents/{agent_id}/plan/{plan_id}"

class BackendApiOptions:
    """
    Backend API options for Nevermined Payments.

    :param backend_host: The host of the backend server
    :param api_key: The Nevermined API Key (optional)
    :param proxy_host: The host of the Nevermined Proxy (optional)
    :param headers: Additional headers to send with the requests (optional)
    """
    def __init__(self, backend_host: str, api_key: Optional[str] = None, proxy_host: Optional[str] = None, headers: Optional[Dict[str, str]] = None):
        self.backend_host = backend_host
        self.api_key = api_key
        self.proxy_host = proxy_host
        self.headers = headers or {}

class HTTPRequestOptions:
    """
    HTTP request options for Nevermined Payments API.

    :param send_through_proxy: Whether to send the request through the proxy (default True)
    :param proxy_host: Proxy host to use (optional)
    :param headers: Additional headers for the request (optional)
    """
    def __init__(self, send_through_proxy: bool = True, proxy_host: Optional[str] = None, headers: Optional[Dict[str, str]] = None):
        self.send_through_proxy = send_through_proxy
        self.proxy_host = proxy_host
        self.headers = headers or {}

class NVMBackendApi:
    """
    Nevermined Backend API client, equivalent to the TypeScript NVMBackendApi class.
    """
    def __init__(self, opts: BackendApiOptions):
        """
        Initialize the API client with backend options.
        """
        default_headers = {
            "Accept": "application/json",
            **opts.headers,
        }
        if opts.api_key:
            default_headers["Authorization"] = f"Bearer {opts.api_key}"
        self.opts = BackendApiOptions(
            backend_host=opts.backend_host,
            api_key=opts.api_key,
            proxy_host=opts.proxy_host,
            headers=default_headers,
        )
        self.has_key = False
        self.agent_id = ""
        try:
            if self.opts.api_key and len(self.opts.api_key) > 0:
                jwt_decoded = jwt.decode(self.opts.api_key, options={"verify_signature": False})
                sub = jwt_decoded.get("sub", "")
                if isinstance(sub, str) and is_ethereum_address(sub):
                    self.has_key = True
        except Exception:
            self.has_key = False
        try:
            backend_url = urlparse(self.opts.backend_host)
            self.opts.backend_host = f"{backend_url.scheme}://{backend_url.netloc}"
        except Exception as error:
            raise ValueError(f"Invalid URL: {self.opts.backend_host} - {str(error)}")

    def parse_url(self, uri: str, req_options: Optional[HTTPRequestOptions] = None) -> str:
        """
        Compose the full URL for a request, using proxy if needed.
        """
        req_options = req_options or HTTPRequestOptions()
        if req_options.send_through_proxy:
            if req_options.proxy_host:
                host = req_options.proxy_host
            elif self.opts.proxy_host:
                host = self.opts.proxy_host
            else:
                host = self.opts.backend_host
        else:
            host = self.opts.backend_host
        parsed = urlparse(host)
        return f"{parsed.scheme}://{parsed.netloc}{uri}"

    def parse_headers(self, additional_headers: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Merge default headers with additional headers.
        """
        return {
            **self.opts.headers,
            **(additional_headers or {}),
        }

    def set_bearer_token(self, token: str):
        """
        Set a new Bearer token for Authorization header.
        """
        self.opts.headers["Authorization"] = f"Bearer {token}"

    def request(self, method: str, url: str, data: Any = None, req_options: Optional[HTTPRequestOptions] = None):
        """
        Make an HTTP request to the backend.
        """
        req_options = req_options or HTTPRequestOptions(send_through_proxy=False)
        full_url = self.parse_url(url, req_options)
        headers = self.parse_headers(req_options.headers)
        try:
            if method.upper() in ["GET"]:
                response = requests.get(full_url, headers=headers)
            elif method.upper() in ["POST"]:
                response = requests.post(full_url, json=data, headers=headers)
            elif method.upper() in ["PUT"]:
                response = requests.put(full_url, json=data, headers=headers)
            elif method.upper() in ["DELETE"]:
                response = requests.delete(full_url, json=data, headers=headers)
            elif method.upper() in ["PATCH"]:
                response = requests.patch(full_url, json=data, headers=headers)
            else:
                raise ValueError(f"Unsupported HTTP method: {method}")
            response.raise_for_status()
            return response
        except requests.HTTPError as err:
            try:
                message = response.json().get("message", "Request failed")
            except Exception:
                message = "Request failed"
            raise Exception(f"HTTP {response.status_code}: {message}") from err
        except Exception as err:
            raise Exception("Network error or request failed without a response.") from err

    def get(self, url: str, req_options: Optional[HTTPRequestOptions] = None):
        """
        Make a GET request.
        """
        req_options = req_options or HTTPRequestOptions(send_through_proxy=True)
        return self.request("GET", url, None, req_options)

    def post(self, url: str, data: Any, req_options: Optional[HTTPRequestOptions] = None):
        """
        Make a POST request.
        """
        return self.request("POST", url, data, req_options)

    def put(self, url: str, data: Any, req_options: Optional[HTTPRequestOptions] = None):
        """
        Make a PUT request.
        """
        return self.request("PUT", url, data, req_options)

    def delete(self, url: str, data: Any, req_options: Optional[HTTPRequestOptions] = None):
        """
        Make a DELETE request.
        """
        return self.request("DELETE", url, data, req_options)