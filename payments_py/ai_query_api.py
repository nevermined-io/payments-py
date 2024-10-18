import asyncio
from typing import Any, List, Optional, Union
from payments_py.data_models import AgentExecutionStatus, ServiceTokenResultDto
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi

# Define API Endpoints
SEARCH_TASKS_ENDPOINT = '/api/v1/agents/search/tasks'
SEARCH_STEPS_ENDPOINT = '/api/v1/agents/search/steps'
CREATE_STEPS_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/steps'
UPDATE_STEP_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/step/{stepId}'
GET_AGENTS_ENDPOINT = '/api/v1/agents'
GET_BUILDER_STEPS_ENDPOINT = '/api/v1/agents/steps'
GET_TASK_STEPS_ENDPOINT = '/api/v1/agents/{did}/tasks/{taskId}/steps'
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
        search_step: Searches for steps
        get_step: Gets the details of a step
    """
    def __init__(self, opts: BackendApiOptions):
        super().__init__(opts)
        self.opts = opts

    async def subscribe(self, callback: Any, join_account_room: bool = True, join_agent_rooms: Optional[Union[str, List[str]]] = None, subscribe_event_types: Optional[List[str]] = None, get_pending_events_on_subscribe: bool = True):
        """
        It subscribes to the Nevermined network to retrieve new AI Tasks requested by other users.
        This method is used by AI agents to subscribe and receive new AI Tasks sent by other subscribers.

        Args:
            callback (Any): The callback function to be called when a new event is received.
            join_account_room (bool): If True, it will join the account room.
            join_agent_rooms (Optional[Union[str, List[str]]]): The agent rooms to join.
            subscribe_event_types (Optional[List[str]]): The event types to subscribe to.
            get_pending_events_on_subscribe (bool): If True, it will get the pending events on subscribe.
        """
        await self._subscribe(callback, join_account_room, join_agent_rooms, subscribe_event_types)
        print('query-api:: Connected to the server')
        if get_pending_events_on_subscribe:
            try: 
                if(get_pending_events_on_subscribe and join_agent_rooms): 
                    await self._emit_step_events(AgentExecutionStatus.Pending, join_agent_rooms)
            except Exception as e:
                print('query-api:: Unable to get pending events', e)
        await asyncio.Event().wait()


    def create_task(self, did: str, task: Any):
        """
        Subscribers can create an AI Task for an Agent. The task must contain the input query that will be used by the AI Agent.
        This method is used by subscribers of a Payment Plan required to access a specific AI Agent or Service. Users who are not subscribers won't be able to create AI Tasks for that Agent.
        Because only subscribers can create AI Tasks, the method requires the access token to interact with the AI Agent/Service.
        This is given using the `queryOpts` object (accessToken attribute).
        
        Args:
            did (str): The DID of the service.
            task (Any): The task to create.

        Example:
            task = {
                "query": "https://www.youtube.com/watch?v=0tZFQs7qBfQ",
                "name": "transcribe",
                "additional_params": [],
                "artifacts": []
            }
            task = subscriber.ai_protocol.create_task(agent.did, task)
            print('Task created:', task.json())
        """
        endpoint = self.parse_url_to_proxy(TASK_ENDPOINT).replace('{did}', did)
        token = self.get_service_token(did)
        return self.post(endpoint, task, headers={'Authorization': f'Bearer {token.accessToken}'})

    def create_steps(self, did: str, task_id: str, steps: Any):
        """
        It creates the step/s required to complete an AI Task.
        This method is used by the AI Agent to create the steps required to complete the AI Task.
        
        Args:
        
            did (str): The DID of the service.
            task_id (str): The task ID.
            steps (Any): The steps to create.
        """
        endpoint = self.parse_url_to_backend(CREATE_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        return self.post(endpoint, steps)

    def update_step(self, did: str, task_id: str, step_id: str, step: Any):
        """
        It updates the step with the new information.
        This method is used by the AI Agent to update the status and output of an step. This method can not be called by a subscriber.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            step_id (str): The step ID.
            step (Any): The step object to update. https://docs.nevermined.io/docs/protocol/query-protocol#steps-attributes
        """
        endpoint = self.parse_url_to_backend(UPDATE_STEP_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id).replace('{stepId}', step_id)
        try:
            return self.put(endpoint, step)
        except Exception as e:
            print('update_step::', e)
            return None

    def search_tasks(self, search_params: Any):
        """
        It searches tasks based on the search parameters associated to the user.

        Args:
            search_params (Any): The search parameters.
        """    
        return self.post(self.parse_url_to_backend(SEARCH_TASKS_ENDPOINT), search_params)

    def get_task_with_steps(self, did: str, task_id: str):
        """
        It returns the full task and the steps resulted of the execution of the task.

        This method is used by subscribers of a Payment Plan required to access a specific AI Agent or Service. Users who are not subscribers won't be able to create AI Tasks for that Agent.


        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
        """
        endpoint = self.parse_url_to_proxy(GET_TASK_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        token = self.get_service_token(did)
        return self.get(endpoint, headers={'Authorization': f'Bearer {token.accessToken}'})


    def get_steps_from_task(self, did: str, task_id: str, status: Optional[str] = None):
        """
        It retrieves all the steps that the agent needs to execute to complete a specific task associated to the user.
        This method is used by the AI Agent to retrieve information about the tasks created by users to the agents owned by the user.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            status (Optional[str]): The status of the steps.
        """
        endpoint = self.parse_url_to_backend(GET_TASK_STEPS_ENDPOINT).replace('{did}', did).replace('{taskId}', task_id)
        if status:
            endpoint += f'?status={status}'
        return self.get(endpoint)
    
    def search_step(self, search_params: Any):
        """
        It search steps based on the search parameters. The steps belongs to the tasks part of the AI Agents owned by the user.
        This method is used by the AI Agent to retrieve information about the steps part of tasks created by users to the agents owned by the user.

        Args:
            search_params (Any): The search parameters.
        """
        return self.post(self.parse_url_to_backend(SEARCH_STEPS_ENDPOINT), search_params)

    def get_step(self,  step_id: str):
        """
        Get the details of a step.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            step_id (str): The step ID.
        """
        result = self.search_step({"step_id": step_id})
        return result.json()['steps'][0]

    def get_steps(self,
                        status: AgentExecutionStatus = AgentExecutionStatus.Pending,
                        dids: List[str] = []):
        """
        It retrieves all the steps that the agent needs to execute to complete the different tasks assigned.
        This method is used by the AI Agent to retrieve information about the steps part of tasks created by users to the agents owned by the user.

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
        It retrieves all the tasks that the agent needs to execute to complete the different tasks assigned.
        This method is used by the AI Agent to retrieve information about the tasks created by users to the agents owned by the user

        """
        return self.get(self.parse_url(GET_AGENTS_ENDPOINT))
    

