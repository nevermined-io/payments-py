import pytest
import os

from payments_py.protocol.nvm_backend import BackendApiOptions
from payments_py.protocol.query_api import AIQueryApi



nvm_api_key = os.getenv('NVM_API_KEY') 
backend_host = os.getenv('BACKEND_HOST')
proxy_host = os.getenv('PROXY_HOST')
web_socket_host = os.getenv('WEB_SOCKET_HOST')

@pytest.fixture
def AIQueryApi():
    opts = BackendApiOptions(
        backend_host=backend_host,
        bearer_token=nvm_api_key,
        proxy_host=proxy_host,
        web_socket_host=web_socket_host,
        web_socket_options={'bearerToken': nvm_api_key}
    )
    return AIQueryApi(opts)

def test_AIQueryApi_creation():
    assert AIQueryApi.opts.backend_host == backend_host
    assert AIQueryApi.opts.bearer_token == nvm_api_key
    assert AIQueryApi.opts.proxy_host == proxy_host
    assert AIQueryApi.opts.web_socket_host == web_socket_host
    assert AIQueryApi.opts.web_socket_options['bearerToken'] == nvm_api_key
    assert AIQueryApi.socket_client == None
    assert AIQueryApi.room_id == None
    assert AIQueryApi._default_socket_options