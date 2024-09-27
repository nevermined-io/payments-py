from typing import Any, List, Optional
from payments_py.data_models import AgentExecutionStatus
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi
import asyncio


# Define API Endpoints
SEARCH_TASKS_ENDPOINT = '/api/v1/agents/search'
CREATE_STEPS_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/steps'
UPDATE_STEP_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/step/{stepId}'
GET_AGENTS_ENDPOINT = '/api/v1/agents'
GET_BUILDER_STEPS_ENDPOINT = '/api/v1/agents/steps'
GET_TASK_STEPS_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/steps'
TASK_ENDPOINT = '/api/v1/agents/{did}/tasks'
GET_TASK_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}'


class AIQueryApi(NVMBackendApi):
    def __init__(self, opts: BackendApiOptions):
        super().__init__(opts)
        self.opts = opts

    async def subscribe(self, callback: Any):
        pending_steps = await self.get_steps(AgentExecutionStatus.Pending)
        await self._subscribe(callback)
        print('query-api:: Connected to the server')
        await self._emit_events(pending_steps)

    async def create_task(self, did: str, task: Any):
        endpoint = self.parse_url(TASK_ENDPOINT).replace('{did}', did)
        print('endpoint', endpoint)
        return await self.post(endpoint, task)

    async def create_steps(self, did: str, task_id: str, steps: Any):
        endpoint = self.parse_url(CREATE_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        return await self.post(endpoint, steps)

    async def update_step(self, did: str, task_id: str, step_id: str, step: Any):
        endpoint = self.parse_url(UPDATE_STEP_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id).replace('{stepId}', step_id)
        return await self.put(endpoint, step)

    async def search_tasks(self, search_params: Any):
        return await self.post(self.parse_url(SEARCH_TASKS_ENDPOINT), search_params)

    async def get_task_with_steps(self, did: str, task_id: str):
        endpoint = self.parse_url(GET_TASK_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        return await self.get(endpoint)

    async def get_steps_from_task(self, did: str, task_id: str, status: Optional[str] = None):
        endpoint = self.parse_url(GET_TASK_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        if status:
            endpoint += f'?status={status}'
        return await self.get(endpoint)

    async def get_steps(self,
                        status: AgentExecutionStatus = AgentExecutionStatus.Pending,
                        dids: List[str] = []):
        endpoint = f'{self.parse_url(GET_BUILDER_STEPS_ENDPOINT)}?'
        if status:
            endpoint += f'&status={status.value}'
        if dids:
            endpoint += f'&dids={",".join(dids)}'
        return await self.get(endpoint)

    async def get_tasks_from_agents(self):
        return await self.get(self.parse_url(GET_AGENTS_ENDPOINT))
