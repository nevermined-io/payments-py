"""
AI Query API implementation for the Nevermined Payments protocol
"""

from typing import Optional, Any
from payments_py.common.types import AgentAccessCredentials
from payments_py.api.nvm_api import AbstractHTTPClient, HTTPRequestOptions


class AIQueryApi(AbstractHTTPClient):
    """
    The AIQueryApi class provides methods to query AI Agents on Nevermined.

    This API is oriented for AI users who already purchased access to an AI Agent and want to start querying them.
    """

    @classmethod
    def get_instance(cls) -> "AIQueryApi":
        """
        Get a singleton instance of the AIQueryApi class.

        Returns:
            The instance of the AIQueryApi class
        """
        return cls()

    def send(
        self,
        access_credentials: AgentAccessCredentials,
        method: str,
        url: str,
        data: Optional[Any] = None,
        req_options: Optional[HTTPRequestOptions] = None,
    ) -> Any:
        """
        Sends a request to the AI Agent/Service.

        This method is used to query an existing AI Agent. It requires the user controlling the NVM API Key to have access to the agent.

        To send this request through a Nevermined proxy, it's necessary to specify the "sendThroughProxy" in the reqOptions parameter

        Args:
            access_credentials: The access credentials for the agent
            method: The HTTP method to use (GET, POST, PUT, DELETE, PATCH)
            url: The URL of the endpoint to query the Agent/Service
            data: The data to send to the Agent/Service
            req_options: The request options to use when querying the Agent/Service

        Returns:
            The result of the query

        Raises:
            PaymentsError: If the request fails

        Example:
            ```python
            result = payments.query.send(access_credentials, 'POST', 'http://example.com/agent/prompt', {'input': 'Hello'})
            ```
        """
        if req_options is None:
            req_options = HTTPRequestOptions(send_through_proxy=False)

        req_options.access_token = access_credentials.access_token

        if access_credentials.proxies and len(access_credentials.proxies) > 0:
            req_options.proxy_host = access_credentials.proxies[0]
            req_options.send_through_proxy = True

        return self.request(method, url, data, req_options)
