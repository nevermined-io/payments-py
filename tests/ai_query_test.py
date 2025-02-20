import asyncio
import json
import pytest
import os

from payments_py.payments import Payments
from payments_py import Environment
from payments_py.data_models import AgentExecutionStatus, CreateAgentDto, CreateAssetResultDto, CreateCreditsPlanDto, FullTaskDto, GetStepsDtoResult, GetTasksDtoResult, OrderPlanResultDto, TaskLog, UpdateStepDto

response_event = asyncio.Event()
global response_data
response_data = None

# Set environment variables for the test
nvm_api_key= os.getenv('NVM_API_KEY') 
nvm_api_key2 = os.getenv('NVM_API_KEY2') 

@pytest.fixture
def ai_query_api_build_fixture():
    return Payments(nvm_api_key=nvm_api_key, environment=Environment.staging, app_id="your_app_id", version="1.0.0")

@pytest.fixture
def ai_query_api_subscriber_fixture():
    return Payments(nvm_api_key=nvm_api_key2, environment=Environment.staging, app_id="your_app_id", version="1.0.0")

@pytest.mark.asyncio(loop_scope="session")
async def test_ai_query_api(ai_query_api_build_fixture, ai_query_api_subscriber_fixture):
    builder = ai_query_api_build_fixture
    subscriber = ai_query_api_subscriber_fixture

    steps = builder.query.get_steps(status=AgentExecutionStatus.Completed, dids=['did:nv:06d810d0f78ebbc229892182e0d1354cf35d80627a6d7af28624017e1a380182'])
    assert isinstance(steps, GetStepsDtoResult)

    steps_from_task = builder.query.get_steps_from_task(did='did:nv:06d810d0f78ebbc229892182e0d1354cf35d80627a6d7af28624017e1a380182' , task_id='task-1015a1ee-b230-49a0-9214-2ba1764046ec')
    assert isinstance(steps_from_task, GetStepsDtoResult)

    step = builder.query.get_step(step_id='step-d3e298cc-bb5c-4e6b-9c8a-82fb7de7ae22')
    assert isinstance(step, UpdateStepDto)

    task_from_agents = builder.query.get_tasks_from_agents()
    assert isinstance(task_from_agents, GetTasksDtoResult)

    task_with_steps= subscriber.query.get_task_with_steps(did='did:nv:06d810d0f78ebbc229892182e0d1354cf35d80627a6d7af28624017e1a380182' , task_id='task-1015a1ee-b230-49a0-9214-2ba1764046ec')
    assert isinstance(task_with_steps, FullTaskDto)


