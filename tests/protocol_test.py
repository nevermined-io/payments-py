import pytest
import os

from payments_py.payments import Payments
from payments_py import Environment

# Set environment variables for the test
nvm_api_key = os.getenv('NVM_API_KEY') 

@pytest.fixture
def ai_query_api_fixture():
    return Payments(nvm_api_key=nvm_api_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key})

def test_AIQueryApi_creation(ai_query_api_fixture):
    ai_query_api = ai_query_api_fixture
    assert ai_query_api.opts.backend_host == Environment.appStaging.value['backend']
    assert ai_query_api.opts.api_key == nvm_api_key
    assert ai_query_api.opts.proxy_host == Environment.appStaging.value['proxy']    
    assert ai_query_api.opts.web_socket_host == Environment.appStaging.value['websocket']
    assert ai_query_api.opts.web_socket_options['bearer_token'] == nvm_api_key
    assert ai_query_api.socket_client is None
    assert ai_query_api.room_id
    assert hasattr(ai_query_api, '_default_socket_options')

@pytest.mark.asyncio
async def test_AIQueryApi_create_task(ai_query_api_fixture):
    ai_query_api = ai_query_api_fixture

    # Define a sample task payload
    task_payload = {
        'query': 'sample_query',
        'name': 'sample_task',
        'additional_params': {
            'param1': 'value1',
            'param2': 'value2'
        }
    }

    # Call the method to create a task
    response = await ai_query_api.ai_protocol.create_task('did:nv:1d4e97eed9bf3fa8141d7091b0daafee9bd7946a5d3727f368b0e55dedb011dd', task_payload)

    # Print response for debugging (optional)
    print(response)

    # Assert that the response is as expected
    # assert response['status'] == 'success'
    # assert response['task_name'] == task_payload['name']
    # assert response['task_params'] == task_payload['additional_params']
