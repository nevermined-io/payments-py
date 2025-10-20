"""
Nevermined Payments API endpoints and backend client
"""

import requests
from typing import Optional, Dict, Any

# Plan endpoints
API_URL_REGISTER_PLAN = "/api/v1/protocol/plans"
API_URL_GET_PLAN = "/api/v1/protocol/plans/{plan_id}"
API_URL_PLAN_BALANCE = "/api/v1/protocol/plans/{plan_id}/balance/{holder_address}"
API_URL_ORDER_PLAN = "/api/v1/protocol/plans/{plan_id}/order"
API_URL_MINT_PLAN = "/api/v1/protocol/plans/mint"
API_URL_MINT_EXPIRABLE_PLAN = "/api/v1/protocol/plans/mintExpirable"
API_URL_BURN_PLAN = "/api/v1/protocol/plans/burn"
API_URL_GET_PLAN_AGENTS = "/api/v1/protocol/plans/{plan_id}/agents"
API_URL_REDEEM_PLAN = "/api/v1/protocol/plans/redeem"

# Agent endpoints
API_URL_REGISTER_AGENT = "/api/v1/protocol/agents"
API_URL_GET_AGENT = "/api/v1/protocol/agents/{agent_id}"
API_URL_SEARCH_AGENTS = "/api/v1/protocol/agents/search"
API_URL_ADD_PLAN_AGENT = "/api/v1/protocol/agents/{agent_id}/plan/{plan_id}"
API_URL_REMOVE_PLAN_AGENT = "/api/v1/protocol/agents/{agent_id}/plan/{plan_id}"
API_URL_INITIALIZE_AGENT = "/api/v1/protocol/agents/initialize/{agent_id}"
API_URL_TRACK_AGENT_SUB_TASK = "/api/v1/protocol/agent-sub-tasks"
API_URL_REGISTER_AGENTS_AND_PLAN = "/api/v1/protocol/agents/plans"
API_URL_GET_AGENT_PLANS = "/api/v1/protocol/agents/{agent_id}/plans"
API_URL_UPDATE_AGENT = "/api/v1/protocol/agents/{agent_id}"
API_URL_SIMULATE_AGENT_REQUEST = "/api/v1/protocol/agents/simulate/start"
API_URL_SIMULATE_REDEEM_AGENT_REQUEST = "/api/v1/protocol/agents/simulate/finish"

# Token endpoints
API_URL_GET_AGENT_ACCESS_TOKEN = "/api/v1/protocol/token/{plan_id}/{agent_id}"
API_URL_VALIDATE_AGENT_ACCESS_TOKEN = "/api/v1/protocol/token/validate/{agent_id}"

# Stripe endpoints
API_URL_STRIPE_CHECKOUT = "/api/v1/stripe/checkout"


class HTTPRequestOptions:
    """
    HTTP request options for Nevermined Payments API.

    :param send_through_proxy: Whether to send the request through the proxy (default True)
    :param proxy_host: Proxy host to use (optional)
    :param headers: Additional headers for the request (optional)
    :param access_token: Access token for authorization (optional)
    """

    def __init__(
        self,
        send_through_proxy: bool = True,
        proxy_host: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        access_token: Optional[str] = None,
    ):
        self.send_through_proxy = send_through_proxy
        self.proxy_host = proxy_host
        self.headers = headers or {}
        self.access_token = access_token


class AbstractHTTPClient:
    """
    Abstract HTTP client for Nevermined API requests.
    Equivalent to the TypeScript AbstractHTTPClient class.
    """

    def __init__(self):
        """
        Initialize the HTTP client.
        """

    def parse_url(self, url_requested: str, req_options: HTTPRequestOptions) -> str:
        """
        Parse URL for request, using proxy if needed.
        """
        if req_options.send_through_proxy:
            if not req_options.proxy_host:
                raise ValueError("Proxy host is required when sendThroughProxy is true")
            from urllib.parse import urlparse

            proxy_origin = urlparse(req_options.proxy_host).netloc
            return f"https://{proxy_origin}{url_requested}"
        else:
            return url_requested

    def parse_headers(
        self, request_headers: Dict[str, str], access_token: Optional[str] = None
    ) -> Dict[str, str]:
        """
        Parse headers for request, including access token if provided.
        """
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"
        headers.update(request_headers or {})
        return headers

    def request(
        self,
        method: str,
        url: str,
        data: Any = None,
        req_options: Optional[HTTPRequestOptions] = None,
    ):
        """
        Make an HTTP request.
        """
        if req_options is None:
            req_options = HTTPRequestOptions(send_through_proxy=False)

        full_url = self.parse_url(url, req_options)
        headers = self.parse_headers(req_options.headers, req_options.access_token)

        try:
            if method.upper() == "GET":
                response = requests.get(full_url, headers=headers)
            elif method.upper() == "POST":
                response = requests.post(full_url, json=data, headers=headers)
            elif method.upper() == "PUT":
                response = requests.put(full_url, json=data, headers=headers)
            elif method.upper() == "DELETE":
                response = requests.delete(full_url, json=data, headers=headers)
            elif method.upper() == "PATCH":
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
            raise Exception(
                "Network error or request failed without a response."
            ) from err

    def get(self, url: str, req_options: Optional[HTTPRequestOptions] = None):
        """
        Make a GET request.
        """
        if req_options is None:
            req_options = HTTPRequestOptions(send_through_proxy=True)
        return self.request("GET", url, None, req_options)

    def post(
        self, url: str, data: Any, req_options: Optional[HTTPRequestOptions] = None
    ):
        """
        Make a POST request.
        """
        return self.request("POST", url, data, req_options)

    def put(
        self, url: str, data: Any, req_options: Optional[HTTPRequestOptions] = None
    ):
        """
        Make a PUT request.
        """
        return self.request("PUT", url, data, req_options)

    def delete(
        self, url: str, data: Any, req_options: Optional[HTTPRequestOptions] = None
    ):
        """
        Make a DELETE request.
        """
        return self.request("DELETE", url, data, req_options)
