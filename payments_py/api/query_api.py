"""
AI Query API implementation for the Nevermined Payments protocol
"""
from typing import Optional, Dict, Any
from payments_py.common.payments_error import PaymentsError
from payments_py.api.nvm_api import NVMBackendApi, BackendApiOptions, HTTPRequestOptions

class AIQueryOptions:
    """
    Options required for interacting with an external AI Agent/Service.
    """
    def __init__(self, access_token: Optional[str] = None, nevermined_proxy_uri: Optional[str] = None):
        """
        Initialize AIQueryOptions.

        Args:
            access_token: The access token to interact with the AI Agent/Service.
            nevermined_proxy_uri: The Nevermined Proxy URI to interact with the AI Agent/Service.
        """
        self.access_token = access_token
        self.nevermined_proxy_uri = nevermined_proxy_uri

class AIQueryApi(NVMBackendApi):
    """
    The AI Query API class provides the methods to interact with the AI Query API.
    This API implements the Nevermined AI Query Protocol @see https://docs.nevermined.io/docs/protocol/query-protocol.

    @remarks
    This API is oriented for AI Builders providing AI Agents and AI Subscribers interacting with them.
    """
    def __init__(
        self,
        opts: BackendApiOptions
    ):
        """
        Initialize the AI Query API.

        Args:
            opts: BackendApiOptions instance with backend_host, api_key, proxy_host, headers
        """
        super().__init__(opts)
        self.query_options_cache: Dict[str, AIQueryOptions] = {}

    def get_service_access_config(self, agent_id: str) -> Dict[str, Any]:
        """
        Get the required configuration for accessing a remote service agent.
        This configuration includes:
        - The JWT access token
        - The Proxy url that can be used to query the agent/service.

        Args:
            agent_id: The unique identifier of the agent

        Returns:
            A dictionary with 'accessToken' and 'neverminedProxyUri'.

        Raises:
            PaymentsError: If the request fails

        @example
        ```python
        access_config = payments.query.get_service_access_config(agent_id)
        print(f"Agent JWT Token: {access_config.access_token}")
        print(f"Agent Proxy URL: {access_config.nevermined_proxy_uri}")
        ```
        """
        try:
            url = f"/api/v1/payments/service/token/{agent_id}"
            response = self.get(url, HTTPRequestOptions(send_through_proxy=False))
            data = response.json()
            token = data.get('token', {})
            return token
        except Exception as e:
            raise PaymentsError(str(e))

    def send(
        self,
        method: str,
        url: str,
        data: Optional[Any] = None,
        req_options: Optional[HTTPRequestOptions] = None
    ) -> Any:
        """
        Sends a request to the AI Agent/Service.

        Args:
            method: The HTTP method to use (GET, POST, PUT, DELETE, PATCH)
            url: The URL of the endpoint to query the Agent/Service.
            data: The data to send to the Agent/Service.
            req_options: The request options (e.g., sendThroughProxy)

        Returns:
            The result of the query

        Raises:
            PaymentsError: If the request fails

        @remarks
        This method is used to query an existing AI Agent. It requires the user controlling the NVM API Key to have access to the agent.

        @remarks
        To send this request through a Nevermined proxy, it's necessary to specify the "sendThroughProxy" in the reqOptions parameter
        @example
        ```python
        payments.query.send('POST', 'http://example.com/agent/prompt', {'input': 'Hello'})
        ```
        """
        try:
            response = self.request(method, url, data, req_options)
            return response.json()
        except Exception as e:
            raise PaymentsError(str(e)) 