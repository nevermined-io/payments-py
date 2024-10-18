import asyncio
import pytest
import os

from payments_py.payments import Payments
from payments_py import Environment
from payments_py.data_models import AgentExecutionStatus, CreateAssetResultDto, OrderPlanResultDto

response_event = asyncio.Event()
room_joined_event = asyncio.Event()
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

async def on_join_rooms(data):
    print("Joined room:", data)
    room_joined_event.set()

@pytest.mark.asyncio(loop_scope="session")
async def test_AIQueryApi_create_task_in_plan_purchased(ai_query_api_build_fixture, ai_query_api_subscriber_fixture):
    builder = ai_query_api_build_fixture
    subscriber = ai_query_api_subscriber_fixture

    plan = builder.create_credits_plan(
        name="Plan with agent",
        description="test",
        price=0,
        token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
        amount_of_credits=100,
        tags=["test"]
    )
    assert isinstance(plan, CreateAssetResultDto)
    assert plan.did.startswith("did:")
    print('Plan created:', plan.did)

    agent = builder.create_service(
        plan_did=plan.did,
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

    order_response = subscriber.order_plan(plan_did=plan.did)
    assert isinstance(order_response, OrderPlanResultDto)
    print('Plan ordered:', order_response.success)

    balance_before_task = subscriber.get_plan_balance(plan_did=plan.did, account_address="0x496D42f45a2C2Dc460c6605A2b414698232F123f")

    subscription_task = asyncio.create_task(builder.ai_protocol.subscribe(eventsReceived))

    # Ensure the WebSocket connection is established
    for i in range(5):
        await asyncio.sleep(1)  # Wait for 1 second between each attempt
        if builder.ai_protocol.socket_client.connected:
            break
    assert builder.ai_protocol.socket_client.connected, "WebSocket connection failed"
    assert builder.user_room_id, "User room ID is not set"

    builder.ai_protocol.socket_client.on("_join-rooms_", on_join_rooms)
    await asyncio.wait_for(room_joined_event.wait(), timeout=10)
    
    task = subscriber.ai_protocol.create_task(agent.did, {'query': 'sample_query', 'name': 'sample_task'})
    print('Task created:', task.json())

    await asyncio.wait_for(response_event.wait(), timeout=120)

    assert response_data is not None, "Builder did not receive the event from subscriber"
    print('Task received by builder:', response_data)

    task_result = subscriber.ai_protocol.get_task_with_steps(did=agent.did, task_id=response_data['task_id'])
    try:
        assert task_result.json()['task']['task_status'] == AgentExecutionStatus.Completed.value  
    except Exception as e:
        print('Task status:', task_result)
        print(e) 
    
    print('Wait for credits to be burned')
    await asyncio.sleep(10)

    balance2 = subscriber.get_plan_balance(plan_did=plan.did, account_address="0x496D42f45a2C2Dc460c6605A2b414698232F123f")
    print('Plan balance2:', balance2)
    assert int(balance2.balance) == int(balance_before_task.balance) - 2

    with pytest.raises(Exception) as excinfo:
        task = subscriber.ai_protocol.create_task(did=agent.did, task={})
    exception_args = excinfo.value.args[0] 
    assert exception_args['status'] == 400

    # Disconnect both clients after test
    await builder.ai_protocol.socket_client.disconnect()
    await subscriber.ai_protocol.socket_client.disconnect()

    subscription_task.cancel()
    try:
        await subscription_task
    except asyncio.CancelledError:
        pass

# @pytest.mark.asyncio(loop_scope="session")
# async def test_AI_send_task(ai_query_api_build_fixture):
#     builder = ai_query_api_build_fixture
#     task = builder.ai_protocol.create_task('did:nv:a8983b06c0f25fb4064fc61d6527c84ca1813e552bfad5fa1c974caa3c5ccf49', 
#                                               {'query': 'https://www.youtube.com/watch?v=-_4GZnGl55c&t=5s', 'name': 'Summarize video'})
#     print('Task created:', task.json())

# @pytest.mark.asyncio(loop_scope="session")
# async def test_AI_send_task2(ai_query_api_build_fixture):
#     builder = ai_query_api_build_fixture
#     task = builder.ai_protocol.get_task_with_steps(did='did:nv:a8983b06c0f25fb4064fc61d6527c84ca1813e552bfad5fa1c974caa3c5ccf49', task_id='task-cd5a90e6-688f-45a3-a299-1845d10db625')
#     print('Task result:', task.json())