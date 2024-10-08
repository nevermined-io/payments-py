from typing import Any, List, Optional
from payments_py.data_models import AgentExecutionStatus, ServiceTokenResultDto
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi

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

    async def subscribe(self, callback: Any, events: Optional[str]=None):
        await self._subscribe(callback, events)
        print('query-api:: Connected to the server')
        pending_steps = self.get_steps(AgentExecutionStatus.Pending)
        
        if callback is not None:
            await callback(pending_steps.json()['steps'])
        # print('query-api:: Pending steps:', pending_steps.json())
        await self._emit_events(pending_steps.json())
        # await self.socket_client.wait()

        # return pending_steps.json()    
    
        

    def create_task(self, did: str, task: Any, jwt: Optional[str] = None):
        """
        Creates a task for an agent to execute.
        
        Args:
            did (str): The DID of the service.
            task (Any): The task to create.
            jwt (Optional[str]): The JWT token.
        """
        endpoint = self.parse_url_to_proxy(TASK_ENDPOINT).replace('{did}', did)
        if jwt:
            self.set_bearer_token(jwt)
            return self.post(endpoint, task)
        else:
            token = self.get_service_token(did)
            self.set_bearer_token(token.accessToken)
            return self.post(endpoint, task)

    def create_steps(self, did: str, task_id: str, steps: Any):
        endpoint = self.parse_url_to_backend(CREATE_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        return self.post(endpoint, steps)

    def update_step(self, did: str, task_id: str, step_id: str, step: Any, jwt: Optional[str] = None):
        endpoint = self.parse_url_to_backend(UPDATE_STEP_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id).replace('{stepId}', step_id)
        try:
            if jwt:
                self.set_bearer_token(jwt)
                return self.put(endpoint, step)
            else:
                return self.put(endpoint, step)
        except Exception as e:
            print('update_step::', e)
            return None



    def search_tasks(self, search_params: Any):
        return self.post(self.parse_url_to_backend(SEARCH_TASKS_ENDPOINT), search_params)

    def get_task_with_steps(self, did: str, task_id: str, jwt: Optional[str] = None):
        endpoint = self.parse_url_to_proxy(GET_TASK_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        if jwt:
            self.set_bearer_token(jwt)
            return self.get(endpoint)
        else:
            token = self.get_service_token(did)
            self.set_bearer_token(token.accessToken)
            return self.get(endpoint)

    def get_steps_from_task(self, did: str, task_id: str, status: Optional[str] = None):
        endpoint = self.parse_url_to_backend(GET_TASK_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        if status:
            endpoint += f'?status={status}'
        return self.get(endpoint)

    def get_steps(self,
                        status: AgentExecutionStatus = AgentExecutionStatus.Pending,
                        dids: List[str] = []):
        endpoint = f'{self.parse_url_to_backend(GET_BUILDER_STEPS_ENDPOINT)}?'
        if status:
            endpoint += f'&status={status.value}'
        if dids:
            endpoint += f'&dids={",".join(dids)}'
        return self.get(endpoint)

    def get_tasks_from_agents(self):
        return self.get(self.parse_url(GET_AGENTS_ENDPOINT))
    
    def get_service_token(self, service_did: str) -> ServiceTokenResultDto:
        """
        Gets the service token.

        Args:
            service_did (str): The DID of the service.

        Returns:
            ServiceTokenResultDto: The result of the creation operation.

        Raises:
            HTTPError: If the API call fails.

        Example:
            response = your_instance.get_service_token(service_did="did:nv:xyz789")
            print(response)
        """
        url = f"{self.opts.backend_host}/api/v1/payments/service/token/{service_did}"
        response = self.get(url)
        response.raise_for_status() 
        return ServiceTokenResultDto.model_validate(response.json()['token'])
