import asyncio
import json
import pytest
import os
import time

from payments_py.payments import Payments
from payments_py import Environment
import socketio
from payments_py.data_models import AgentExecutionStatus

socket_client = socketio.AsyncClient()
response_event = asyncio.Event()
global response_data

response_data = None

# Set environment variables for the test
nvm_api_key = os.getenv('NVM_API_KEY') 
nvm_api_key2 = os.getenv('NVM_API_KEY2') 

@pytest.fixture
def ai_query_api_build_fixture():
    return Payments(nvm_api_key=nvm_api_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key})

@pytest.fixture
def ai_query_api_subscriber_fixture():
    return Payments(nvm_api_key=nvm_api_key2, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key2})

# def test_AIQueryApi_creation(ai_query_api_fixture):
#     ai_query_api = ai_query_api_fixture
#     assert ai_query_api.opts.backend_host == Environment.appStaging.value['backend']
#     assert ai_query_api.opts.api_key == nvm_api_key
#     assert ai_query_api.opts.proxy_host == Environment.appStaging.value['proxy']    
#     assert ai_query_api.opts.web_socket_host == Environment.appStaging.value['websocket']
#     assert ai_query_api.opts.web_socket_options['bearer_token'] == nvm_api_key
#     assert ai_query_api.socket_client is None
#     assert ai_query_api.room_id


# @socket_client.on('room:0x0c51455f696c91454edc2f29a6c5639c20cb8a2ad27616ec6d1e2b89a55f36c2')
async def eventsReceived(data):
    payments_builder = Payments(nvm_api_key=nvm_api_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key})
    global response_data
    print('eventsReceived::', len(data))
    if isinstance(data, list):
        print('eventsReceived::', 'pending data:', len(data))
        for step in data:
            print('eventsReceived::', 'step:', step)
            result = payments_builder.ai_protocol.update_step(did='did:nv:70392a44a1a4707e64c3deac5ea87eb01820c2a7933accca9f1f43c6c67fdf05', 
                                                              task_id=step['task_id'], 
                                                              step_id=step['step_id'], 
                                                              step={'step_id': step['step_id'],
                                                                    'task_id': step['task_id'], 
                                                                    'step_status': AgentExecutionStatus.Completed.value,
                                                                    'output': 'success'
                                                                    })
            print(result.json())

    else:
        # parsed_data = json.loads(data)
        print('eventsReceived::', 'parsing event with did:', data)
        # task_with_steps = payments_builder.ai_protocol.get_steps_from_task(did=parsed_data["data"]["did"], task_id=parsed_data["data"]["task_id"]).json()
        # print('eventsReceived::', 'task_with_steps:', task_with_steps['steps'])

        # for step in task_with_steps['steps']:
        #     print('eventsReceived::', 'step:', step["step_id"])
        result = payments_builder.ai_protocol.update_step(did=data["did"], 
                                                              task_id=data["task_id"], 
                                                              step_id=data['step_id'], 
                                                              step={'step_id': data['step_id'],
                                                                    'task_id': data["task_id"], 
                                                                    'step_status': AgentExecutionStatus.Completed.value,
                                                                    'output': 'success'
                                                                    })
        print(result.json())
        response_data = data  # Store the received data for assertion
        response_event.set()


@pytest.mark.asyncio(loop_scope="module")
async def test_subscribe(ai_query_api_build_fixture, ai_query_api_subscriber_fixture):

    builder = ai_query_api_build_fixture
    subscriber = ai_query_api_subscriber_fixture

    await builder.ai_protocol.subscribe(eventsReceived, ['step-created'])
    print('query-api:: Connected and listening for events')
    await asyncio.sleep(2)
    # print('data length:', len(response_data))

    assert builder.ai_protocol.socket_client.connected
    assert builder.room_id

    task = subscriber.ai_protocol.create_task('did:nv:70392a44a1a4707e64c3deac5ea87eb01820c2a7933accca9f1f43c6c67fdf05', {'query': 'sample_query', 'name': 'sample_task', 'additional_params': {'param1': 'value1', 'param2': 'value2'}})
    print('Task created:', task.json())

    print('Waiting for the builder to receive the event from subscriber...')
    await asyncio.wait_for(response_event.wait(), timeout=10)



    print('data length:', len(response_data))


    assert response_data is not None, "Builder did not receive the event from subscriber"
    print('Task received by builder:', response_data)


    # Disconnect both clients after test
    await builder.ai_protocol.socket_client.disconnect()
    await subscriber.ai_protocol.socket_client.disconnect()




# @pytest.mark.asyncio
# async def test_AIQueryApi_create_task(ai_query_api_fixture):
#     ai_query_api = ai_query_api_fixture

#     # Define a sample task payload
#     task_payload = {
#         'query': 'sample_query',
#         'name': 'sample_task',
#         'additional_params': {
#             'param1': 'value1',
#             'param2': 'value2'
#         }
#     }

#     # Call the method to create a task
#     response = ai_query_api.ai_protocol.create_task('did:nv:1d4e97eed9bf3fa8141d7091b0daafee9bd7946a5d3727f368b0e55dedb011dd', task_payload)

#     # Print response for debugging (optional)
#     print(response)

#     # Assert that the response is as expected
#     # assert response['status'] == 'success'
#     # assert response['task_name'] == task_payload['name']
#     # assert response['task_params'] == task_payload['additional_params']


