import asyncio
import pytest
import os
import time

from payments_py.payments import Payments
from payments_py import Environment
from payments_py.data_models import AgentExecutionStatus, CreateAssetResultDto, OrderSubscriptionResultDto

response_event = asyncio.Event()
global response_data

response_data = None

# Set environment variables for the test
nvm_api_key= os.getenv('NVM_API_KEY') 
nvm_api_key2 = os.getenv('NVM_API_KEY2') 

@pytest.fixture
def ai_query_api_build_fixture():
    return Payments(nvm_api_key=nvm_api_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key})

@pytest.fixture
def ai_query_api_subscriber_fixture():
    return Payments(nvm_api_key=nvm_api_key2, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key2})

def test_AIQueryApi_creation(ai_query_api_build_fixture):
    ai_query_api = ai_query_api_build_fixture
    assert ai_query_api.opts.backend_host == Environment.appStaging.value['backend']
    assert ai_query_api.opts.api_key == nvm_api_key
    assert ai_query_api.opts.proxy_host == Environment.appStaging.value['proxy']    
    assert ai_query_api.opts.web_socket_host == Environment.appStaging.value['websocket']
    assert ai_query_api.opts.web_socket_options['bearer_token'] == nvm_api_key
    assert ai_query_api.socket_client
    assert ai_query_api.user_room_id


async def eventsReceived(data):
    payments_builder = Payments(nvm_api_key=nvm_api_key, environment=Environment.appStaging, app_id="your_app_id", version="1.0.0", ai_protocol=True, web_socket_options={'bearer_token': nvm_api_key})
    global response_data
    print('eventsReceived::', len(data))
    if isinstance(data, list):
        print('eventsReceived::', 'pending data:', len(data))
        for step in data:
            print('eventsReceived::', 'step:', step)
            result = payments_builder.ai_protocol.update_step(did=step['did'], 
                                                              task_id=step['task_id'], 
                                                              step_id=step['step_id'], 
                                                              step={'step_id': step['step_id'],
                                                                    'task_id': step['task_id'], 
                                                                    'step_status': AgentExecutionStatus.Completed.value,
                                                                    'output': 'success',
                                                                    'is_last': True
                                                                    })
            print(result.json())

    else:
        print('eventsReceived::', 'parsing event with did:', data)
        response_data = data
        response_event.set()
        result = payments_builder.ai_protocol.update_step(did=data["did"], 
                                                                task_id=data["task_id"], 
                                                                step_id=data['step_id'], 
                                                                step={'step_id': data['step_id'],
                                                                    'task_id': data["task_id"], 
                                                                    'step_status': AgentExecutionStatus.Completed.value,
                                                                    'output': 'success',
                                                                    'is_last': True
                                                                    })
        print(result.json())


@pytest.mark.asyncio(loop_scope="session")
async def test_AIQueryApi_create_task(ai_query_api_build_fixture, ai_query_api_subscriber_fixture):
    builder = ai_query_api_build_fixture
    subscriber = ai_query_api_subscriber_fixture

    subscription = builder.create_credits_subscription(
        name="Subscription with agent",
        description="test",
        price=0,
        token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        amount_of_credits=100,
        tags=["test"]
    )
    assert isinstance(subscription, CreateAssetResultDto)
    assert subscription.did.startswith("did:")
    print('Subscription created:', subscription.did)

    agent = builder.create_service(
        subscription_did=subscription.did,
        service_type='agent',
        name="Agent service",
        description="test",
        amount_of_credits=1,
        service_charge_type="fixed",
        auth_type="none",
        is_nevermined_hosted=True,
        implements_query_protocol=True,
        query_protocol_version='v1'
    )
    assert isinstance(agent, CreateAssetResultDto)
    assert agent.did.startswith("did:")
    print('Agent service created:', agent.did)

    await builder.ai_protocol.subscribe(eventsReceived)
    assert builder.ai_protocol.socket_client.connected
    assert builder.user_room_id

    order_response = subscriber.order_subscription(subscription_did=subscription.did)
    assert isinstance(order_response, OrderSubscriptionResultDto)
    print('Subscription ordered:', order_response.success)


    task = subscriber.ai_protocol.create_task(agent.did, {'query': 'sample_query', 'name': 'sample_task', 'additional_params': {'param1': 'value1', 'param2': 'value2'}})
    print('Task created:', task.json())

    await asyncio.wait_for(response_event.wait(), timeout=600)

    assert response_data is not None, "Builder did not receive the event from subscriber"
    print('Task received by builder:', response_data)

    task_result = subscriber.ai_protocol.get_task_with_steps(did=agent.did, task_id=response_data['task_id']).json()
    assert task_result['task']['task_status'] == AgentExecutionStatus.Completed.value   

    # Disconnect both clients after test
    await builder.ai_protocol.socket_client.disconnect()
    await subscriber.ai_protocol.socket_client.disconnect()
