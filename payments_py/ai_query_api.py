from typing import Any, Dict, List, Optional, Union
from payments_py.data_models import AgentExecutionStatus, ServiceTokenResultDto
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi

# Define API Endpoints
SEARCH_TASKS_ENDPOINT = '/api/v1/agents/search'
CREATE_STEPS_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/steps'
UPDATE_STEP_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/step/{stepId}'
GET_AGENTS_ENDPOINT = '/api/v1/agents'
GET_BUILDER_STEPS_ENDPOINT = '/api/v1/agents/steps'
GET_TASK_STEPS_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/steps'
GET_STEP_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/step/{stepId}'
TASK_ENDPOINT = '/api/v1/agents/{did}/tasks'
GET_TASK_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}'


class AIQueryApi(NVMBackendApi):
    """
    Represents the AI Query API.

    Args:
        opts (BackendApiOptions): The backend API options

    Methods:
        create_task: Creates a task for an agent to execute
        create_steps: Creates steps for a task
        update_step: Updates a step
        search_tasks: Searches for tasks
        get_task_with_steps: Gets a task with its steps
        get_steps_from_task: Gets the steps from a task
        get_steps: Gets the steps
        get_tasks_from_agents: Gets the tasks from the agents
        get_step: Gets a step details
    """
    def __init__(self, opts: BackendApiOptions):
        super().__init__(opts)
        self.opts = opts

    async def subscribe(self, callback: Any, join_account_room: bool = True, join_agent_rooms: Optional[Union[str, List[str]]] = None, subscribe_event_types: Optional[List[str]] = None, get_pending_events_on_subscribe: bool = True):
        await self._subscribe(callback, join_account_room, join_agent_rooms, subscribe_event_types)
        print('query-api:: Connected to the server')
        if get_pending_events_on_subscribe:
            try: 
                if(get_pending_events_on_subscribe and join_agent_rooms): 
                    await self._emit_step_events(AgentExecutionStatus.Pending, join_agent_rooms)
            except Exception as e:
                print('query-api:: Unable to get pending events', e)

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
        """
        Creates steps for a task.
        
        Args:
        
            did (str): The DID of the service.
            task_id (str): The task ID.
            steps (Any): The steps to create.
        """
        endpoint = self.parse_url_to_backend(CREATE_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        return self.post(endpoint, steps)

    def update_step(self, did: str, task_id: str, step_id: str, step: Any, jwt: Optional[str] = None):
        """
        Updates a step.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            step_id (str): The step ID.
            step (Any): The step to update.
            jwt (Optional[str]): The JWT token.
        """
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
        """
        Searches for tasks.

        Args:
            search_params (Any): The search parameters.
        """    
        return self.post(self.parse_url_to_backend(SEARCH_TASKS_ENDPOINT), search_params)

    def get_task_with_steps(self, did: str, task_id: str, jwt: Optional[str] = None):
        """
        Gets a task with its steps.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            jwt (Optional[str]): The JWT token.
        """
        endpoint = self.parse_url_to_proxy(GET_TASK_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        return self.get(endpoint)

    def get_steps_from_task(self, did: str, task_id: str, status: Optional[str] = None):
        """
        Gets the steps from a task.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            status (Optional[str]): The status of the steps.
        """
        endpoint = self.parse_url_to_backend(GET_TASK_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        if status:
            endpoint += f'?status={status}'
        return self.get(endpoint)
    
    def get_step(self, did: str, task_id: str, step_id: str):
        """
        Gets a step.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            step_id (str): The step ID.
        """
        endpoint = self.parse_url_to_backend(GET_STEP_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id).replace('{stepId}', step_id)
        return self.get(endpoint)

    def get_steps(self,
                        status: AgentExecutionStatus = AgentExecutionStatus.Pending,
                        dids: List[str] = []):
        """
        Gets the steps.

        Args:
            status (AgentExecutionStatus): The status of the steps.
            dids (List[str]): The list of DIDs.
        """
        endpoint = f'{self.parse_url_to_backend(GET_BUILDER_STEPS_ENDPOINT)}?'
        if status:
            endpoint += f'&status={status.value}'
        if dids:
            endpoint += f'&dids={",".join(dids)}'
        return self.get(endpoint)

    def get_tasks_from_agents(self):
        """
        Gets the tasks from the agents.
        """
        return self.get(self.parse_url(GET_AGENTS_ENDPOINT))
    

