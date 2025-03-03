import asyncio
import json
import pytest
import os

from payments_py.payments import Payments
from payments_py import Environment
from payments_py.data_models import (
    AgentExecutionStatus,
    CreateAgentDto,
    CreateAssetResultDto,
    CreateCreditsPlanDto,
    OrderPlanResultDto,
    StepEvent,
    TaskLog,
)

response_event = asyncio.Event()
global response_data
response_data = None

# Set environment variables for the test
nvm_api_key = os.getenv("NVM_API_KEY")
nvm_api_key2 = os.getenv("NVM_API_KEY2")


@pytest.fixture
def ai_query_api_build_fixture() -> Payments:
    return Payments(
        nvm_api_key=nvm_api_key,
        environment=Environment.staging,
        app_id="your_app_id",
        version="1.0.0",
    )


@pytest.fixture
def ai_query_api_subscriber_fixture() -> Payments:
    return Payments(
        nvm_api_key=nvm_api_key2,
        environment=Environment.staging,
        app_id="your_app_id",
        version="1.0.0",
    )


def test_AIQueryApi_creation(ai_query_api_build_fixture):
    ai_query_api = ai_query_api_build_fixture
    assert ai_query_api.opts.backend_host == Environment.staging.value["backend"]
    assert ai_query_api.opts.api_key == nvm_api_key
    assert ai_query_api.opts.proxy_host == Environment.staging.value["proxy"]
    assert ai_query_api.opts.web_socket_host == Environment.staging.value["websocket"]
    assert ai_query_api.socket_client
    assert ai_query_api.user_room_id


async def eventsReceived(data: StepEvent):
    payments_builder = Payments(
        nvm_api_key=nvm_api_key,
        environment=Environment.staging,
        app_id="your_app_id",
        version="1.0.0",
    )
    global response_data
    step = payments_builder.query.get_step(data["step_id"])
    print("eventsReceived::", len(data))
    if step.step_status != AgentExecutionStatus.Pending.value:
        print("Step status is not pending")
        return
    print("eventsReceived::", "parsing event with did:", data)
    response_data = data
    response_event.set()
    result = payments_builder.query.update_step(
        did=data["did"],
        task_id=data["task_id"],
        step_id=data["step_id"],
        step={
            "step_id": data["step_id"],
            "task_id": data["task_id"],
            "step_status": AgentExecutionStatus.Completed.value,
            "output": "success",
            "is_last": True,
        },
    )
    print(result.success)
    print(result.data)


@pytest.mark.asyncio(loop_scope="session")
async def test_AIQueryApi_create_task_in_plan_purchased(
    ai_query_api_build_fixture: Payments, ai_query_api_subscriber_fixture: Payments
):
    builder = ai_query_api_build_fixture
    subscriber = ai_query_api_subscriber_fixture

    plan = builder.create_credits_plan(
        createCreditsPlanDto=CreateCreditsPlanDto(
            name="Plan with agent",
            description="test",
            price=0,
            token_address="0x75faf114eafb1BDbe2F0316DF893fd58CE46AA4d",
            amount_of_credits=100,
            tags=["test"],
        )
    )
    assert isinstance(plan, CreateAssetResultDto)
    assert plan.did.startswith("did:")
    print("Plan created:", plan.did)

    agent = builder.create_agent(
        createAgentDto=CreateAgentDto(
            plan_did=plan.did,
            name="Agent service",
            description="test",
            amount_of_credits=1,
            service_charge_type="fixed",
            auth_type="none",
            use_ai_hub=True,
        )
    )

    assert isinstance(agent, CreateAssetResultDto)
    assert agent.did.startswith("did:")
    print("Agent service created:", agent.did)

    order_response = subscriber.order_plan(plan_did=plan.did)
    assert isinstance(order_response, OrderPlanResultDto)
    print("Plan ordered:", order_response.success)

    balance_before_task = subscriber.get_plan_balance(
        plan_did=plan.did, account_address="0x496D42f45a2C2Dc460c6605A2b414698232F123f"
    )

    subscription_task = asyncio.create_task(builder.query.subscribe(eventsReceived))

    # Ensure the WebSocket connection is established
    for i in range(5):
        await asyncio.sleep(1)  # Wait for 1 second between each attempt
        if builder.query.socket_client.connected:
            break
    assert builder.query.socket_client.connected, "WebSocket connection failed"
    assert builder.user_room_id, "User room ID is not set"

    task = await subscriber.query.create_task(
        agent.did, {"input_query": "sample_query", "name": "sample_task"}
    )
    print("Task created:", task.data)

    await asyncio.wait_for(response_event.wait(), timeout=120)

    assert (
        response_data is not None
    ), "Builder did not receive the event from subscriber"
    print("Task received by builder:", response_data)

    task_result = subscriber.query.get_task_with_steps(
        did=agent.did, task_id=response_data["task_id"]
    )
    try:
        assert task_result.task.task_status == AgentExecutionStatus.Completed.value
    except Exception as e:
        print("Task status:", task_result)
        print(e)

    print("Wait for credits to be burned")
    await asyncio.sleep(20)

    balance2 = subscriber.get_plan_balance(
        plan_did=plan.did, account_address="0x496D42f45a2C2Dc460c6605A2b414698232F123f"
    )
    print("Plan balance2:", balance2)
    assert int(balance2.balance) == int(balance_before_task.balance) - 2

    task_invalid = await subscriber.query.create_task(did=agent.did, task={})
    assert task_invalid.success == False

    # Disconnect both clients after test
    await builder.query.socket_client.disconnect()
    await subscriber.query.socket_client.disconnect()

    subscription_task.cancel()
    try:
        await subscription_task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio(loop_scope="session")
async def test_AIQueryApi_log(
    ai_query_api_build_fixture, ai_query_api_subscriber_fixture
):
    builder = ai_query_api_build_fixture
    subscriber = ai_query_api_subscriber_fixture

    join_event = asyncio.Event()

    def on_join_task(*args):
        print("_join-task_ event received")
        join_event.set()

    await subscriber.connect_socket()
    subscriber.socket_client.on("_join-tasks_", on_join_task)

    await subscriber.socket_client.emit(
        "_join-tasks",
        json.dumps({"tasks": ["task-d9d8096a-0c97-42d1-8d6c-ff1481d72ed0"]}),
    )
    await asyncio.wait_for(join_event.wait(), timeout=10)
    assert join_event.is_set(), "Join-task event was not received."

    log_task_event = asyncio.Event()

    def on_log_task_send(*args):
        print("task-log event received")
        log_task_event.set()

    subscriber.socket_client.on("task-log", on_log_task_send)

    await builder.connect_socket()
    task_log = TaskLog(
        task_id="task-d9d8096a-0c97-42d1-8d6c-ff1481d72ed0",
        message="message",
        level="info",
    )
    await builder.query.log_task(task_log)
    await asyncio.wait_for(log_task_event.wait(), timeout=10)
    assert log_task_event.is_set(), "Task-log event was not received."

    await builder.disconnect_socket()
    await subscriber.disconnect_socket()
    assert not builder.socket_client.connected, "Builder socket is still open."
    assert not subscriber.socket_client.connected, "Subscriber socket is still open."


# @pytest.mark.asyncio(loop_scope="session")
# async def test_AI_send_task(ai_query_api_subscriber_fixture):
#     builder = ai_query_api_subscriber_fixture
#     task = builder.query.create_task('did:nv:268cc4cb5d9d6531f25b9e750b6aa4d96cc5a514116e3afcf41fe4ca0a27dad0',
#                                               {'query': 'https://www.youtube.com/watch?v=-yGk3P5LWAA', 'name': 'Summarize video'})
#     print('Task created:', task.json()['task']['task_id'])
#     task_id = task.json()['task']['task_id']

#     final_task_result = None
#     while True:
#         task_result = builder.query.get_task_with_steps(did='did:nv:268cc4cb5d9d6531f25b9e750b6aa4d96cc5a514116e3afcf41fe4ca0a27dad0', task_id=task_id)
#         task_status = task_result.json()['task']['task_status']

#         if task_status != 'Pending':
#             final_task_result = task_result
#             break
#         else:
#             print('Task still pending...')
#             await asyncio.sleep(1)

#     # Print the final result after the loop
#     print('Task completed:', final_task_result.json())

# @pytest.mark.asyncio(loop_scope="session")
# async def test_AI_send_task2(ai_query_api_subscriber_fixture):
#     builder = ai_query_api_subscriber_fixture
#     task = builder.query.get_task_with_steps(did='did:nv:c48ee23c3eab23d0094dbe2ae7d01a1ddb6394e85dca8614f7de84d8e4eb4ee1', task_id='task-7cd4dbd7-5055-4340-8bb2-78169a6f4e33')
#     print('Task result:', task.json())
