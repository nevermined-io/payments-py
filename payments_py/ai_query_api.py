import asyncio
import json
from typing import Any, Callable, List, Optional, Union
from urllib.parse import urlencode
from payments_py.data_models import (
    AgentExecutionStatus,
    ApiResponse,
    CreateStepsDto,
    CreateTaskDto,
    FullTaskDto,
    GetStepsDtoResult,
    GetTasksDtoResult,
    SearchSteps,
    SearchStepsDtoResult,
    SearchTasks,
    SearchTasksDtoResult,
    Step,
    StepEvent,
    TaskEvent,
    TaskLog,
    UpdateStepDto,
)
from payments_py.nvm_backend import BackendApiOptions, NVMBackendApi

# Define API Endpoints
SEARCH_TASKS_ENDPOINT = "/api/v1/agents/search/tasks"
SEARCH_STEPS_ENDPOINT = "/api/v1/agents/search/steps"
CREATE_STEPS_ENDPOINT = "/api/v1/agents/{did}/tasks/{taskId}/steps"
UPDATE_STEP_ENDPOINT = "/api/v1/agents/{did}/tasks/{taskId}/step/{stepId}"
GET_AGENTS_ENDPOINT = "/api/v1/agents"
GET_BUILDER_STEPS_ENDPOINT = "/api/v1/agents/steps"
GET_TASK_STEPS_ENDPOINT = "/api/v1/agents/{did}/tasks/{taskId}/steps"
TASK_ENDPOINT = "/api/v1/agents/{did}/tasks"
GET_TASK_ENDPOINT = "/api/v1/agents/{did}/tasks/{taskId}"


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
        self.opts: BackendApiOptions = opts

    async def subscribe(
        self,
        callback: Callable[[StepEvent], None],
        join_account_room: bool = True,
        join_agent_rooms: Optional[Union[str, List[str]]] = None,
        subscribe_event_types: Optional[List[str]] = None,
        get_pending_events_on_subscribe: bool = True,
    ) -> None:
        """
        It subscribes to the Nevermined network to retrieve new AI Tasks requested by other users.
        This method is used by AI agents to subscribe and receive new AI Tasks sent by other subscribers.

        Args:
            callback (Callable[[StepEvent], None]): The callback function to be called when a new event is received.
            join_account_room (bool): If True, it will join the account room.
            join_agent_rooms (Optional[Union[str, List[str]]]): The agent rooms to join.
            subscribe_event_types (Optional[List[str]]): The event types to subscribe to.
            get_pending_events_on_subscribe (bool): If True, it will get the pending events on subscribe.

        Example:
            await subscriber.query.subscribe(
                callback=eventsReceived,
                join_account_room=True,
                join_agent_rooms=["agent1", "agent2"],
                subscribe_event_types=["ste-updated"],
                get_pending_events_on_subscribe=True
            )

        Returns:
            None
        """
        await self.connect_socket_subscriber(
            callback=callback,
            join_account_room=join_account_room,
            join_agent_rooms=join_agent_rooms,
            subscribe_event_types=subscribe_event_types,
            get_pending_events_on_subscribe=get_pending_events_on_subscribe,
        )
        await asyncio.Event().wait()

    async def log_task(self, task_log: TaskLog):
        """
        It send a log message with the status of a task and a message with relevant information for the subscriber.
        This method is used by AI agents to log messages.

        Args:
            task_log (TaskLog): An instance containing log details.
        """
        data = task_log.model_dump(exclude_none=True)
        await self.connect_socket()
        await self.socket_client.emit("_task-log", json.dumps(data))

    async def create_task(
        self,
        did: str,
        task: CreateTaskDto,
        _callback: Optional[Callable[[TaskEvent], None]] = None,
    ) -> ApiResponse:
        """
        Subscribers can create an AI Task for an Agent. The task must contain the input query that will be used by the AI Agent.
        This method is used by subscribers of a Payment Plan required to access a specific AI Agent or Service. Users who are not subscribers won't be able to create AI Tasks for that Agent.
        Because only subscribers can create AI Tasks, the method requires the access token to interact with the AI Agent/Service.
        This is given using the `queryOpts` object (accessToken attribute).

        Args:
            did (str): The DID of the service.
            task (CreateTaskDto): The task to create.
            _callback (Optional[Callable[[TaskEvent], None]]): The callback to execute when a new task updated event is received (optional)


        Example:
            task = {
                "input_query": "https://www.youtube.com/watch?v=0tZFQs7qBfQ",
                "name": "transcribe",
                "input_additional": {},
                "input_artifacts": []
            }
            task = subscriber.query.create_task(agent.did, task)
            print('Task created:', task.json())

        Returns:
            ApiResponse: The response of the request.

        Example:
            task = {
                "input_query": "https://www.youtube.com/watch?v=0tZFQs7qBfQ",
                "name": "transcribe",
                "input_additional": {},
                "input_artifacts": []
            }
            task = subscriber.query.create_task(agent.did, task)
            print('Task created:', task.data)
        """
        endpoint = self.parse_url_to_proxy(TASK_ENDPOINT).replace("{did}", did)
        token = self.get_service_token(did)
        try:
            result = self.post(
                endpoint, task, headers={"Authorization": f"Bearer {token.accessToken}"}
            )
            if 200 <= result.status_code < 300:
                task_data = result.json()
                if _callback:
                    await self.subscribe_tasks_updated(
                        _callback, [task_data["task"]["task_id"]]
                    )
                return ApiResponse(
                    success=True, data=task_data, status=result.status_code
                )
            else:
                return ApiResponse(
                    success=False,
                    error=f"Error: {result.status_code} - {result.text}",
                    status=result.status_code,
                )
        except Exception as e:
            # Handle any request exceptions
            print("create_task::", e)
            return ApiResponse(success=False, error=str(e))

    def create_steps(
        self, did: str, task_id: str, steps: CreateStepsDto
    ) -> ApiResponse:
        """
        It creates the step/s required to complete an AI Task.
        This method is used by the AI Agent to create the steps required to complete the AI Task.

        Args:

            did (str): The DID of the service.
            task_id (str): The task ID.
            steps (CreateStepsDto): The steps to create.

        Returns:
            ApiResponse: The response of the request.

        Example:
            steps = {
                "steps": [
                    {"name": "step1", "input_artifacts": [], "input_additional": {}}
                ]
            }
            steps = subscriber.query.create_steps(agent.did, task_id, steps)
            print('Steps created:', steps.data)
        """
        endpoint = (
            self.parse_url_to_backend(CREATE_STEPS_ENDPOINT)
            .replace("{did}", did)
            .replace("{taskId}", task_id)
        )
        try:
            # Send the POST request to create the steps
            response = self.post(endpoint, steps)

            # Check if the response status code is between 200 and 299
            return (
                ApiResponse(success=True, data=response.json())
                if 200 <= response.status_code < 300
                else ApiResponse(
                    success=False,
                    error=f"Error: {response.status_code} - {response.text}",
                )
            )
        except Exception as e:
            # Handle exceptions and return a structured error response
            print("create_steps::", e)
            return ApiResponse(success=False, error=str(e))

    def update_step(
        self, did: str, task_id: str, step_id: str, step: Step
    ) -> ApiResponse:
        """
        It updates the step with the new information.
        This method is used by the AI Agent to update the status and output of an step. This method can not be called by a subscriber.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            step_id (str): The step ID.
            step (Step): The step object to update. https://docs.nevermined.io/docs/protocol/query-protocol#steps-attributes

        Returns:
            ApiResponse: The response of the request.
        """
        endpoint = (
            self.parse_url_to_backend(UPDATE_STEP_ENDPOINT)
            .replace("{did}", did)
            .replace("{taskId}", task_id)
            .replace("{stepId}", step_id)
        )
        try:
            response = self.put(endpoint, step)
            if 200 <= response.status_code < 300:
                return ApiResponse(success=True, data=response.json())
            else:
                return ApiResponse(
                    success=False,
                    error=f"Error: {response.status_code} - {response.text}",
                )
        except Exception as e:
            print("update_step::", e)
            return ApiResponse(success=False, error=str(e))

    def search_tasks(self, search_params: SearchTasks) -> SearchTasksDtoResult:
        """
        It searches tasks based on the search parameters associated to the user.

        Args:
            search_params (SearchTasks): The search parameters.

        Returns:
            SearchTasksDtoResult: The search result.
        """
        return self.post(
            self.parse_url_to_backend(SEARCH_TASKS_ENDPOINT), search_params
        )

    def get_task_with_steps(self, did: str, task_id: str) -> FullTaskDto:
        """
        It returns the full task and the steps resulted of the execution of the task.

        This method is used by subscribers of a Payment Plan required to access a specific AI Agent or Service. Users who are not subscribers won't be able to create AI Tasks for that Agent.


        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
        Returns:
            FullTaskDto: The full task with steps and logs.
        """
        endpoint = (
            self.parse_url_to_proxy(GET_TASK_ENDPOINT)
            .replace("{did}", did)
            .replace("{taskId}", task_id)
        )
        token = self.get_service_token(did)
        response = self.get(
            endpoint, headers={"Authorization": f"Bearer {token.accessToken}"}
        )
        response.raise_for_status()
        return FullTaskDto.model_validate(response.json())

    def get_steps_from_task(
        self, did: str, task_id: str, status: Optional[str] = None
    ) -> GetStepsDtoResult:
        """
        It retrieves all the steps that the agent needs to execute to complete a specific task associated to the user.
        This method is used by the AI Agent to retrieve information about the tasks created by users to the agents owned by the user.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            status (Optional[str]): The status of the steps.
        Returns:
            GetStepsDtoResult: The steps result.
        """
        endpoint = (
            self.parse_url_to_backend(GET_TASK_STEPS_ENDPOINT)
            .replace("{did}", did)
            .replace("{taskId}", task_id)
        )
        if status:
            endpoint += f"?status={status}"
        response = self.get(endpoint)
        response.raise_for_status()
        return GetStepsDtoResult.model_validate(response.json())

    def search_step(self, search_params: SearchSteps) -> SearchStepsDtoResult:
        """
        It search steps based on the search parameters. The steps belongs to the tasks part of the AI Agents owned by the user.
        This method is used by the AI Agent to retrieve information about the steps part of tasks created by users to the agents owned by the user.

        Args:
            search_params (SearchSteps): The search parameters.

        Returns:
            SearchStepsDtoResult: The search result.
        """
        response = self.post(
            self.parse_url_to_backend(SEARCH_STEPS_ENDPOINT), search_params
        )
        response.raise_for_status()
        return response.json()

    def get_step(self, step_id: str) -> UpdateStepDto:
        """
        Get the details of a step.

        Args:
            did (str): The DID of the service.
            task_id (str): The task ID.
            step_id (str): The step ID.

        Returns:
            UpdateStepDto: The step details.
        """
        result = self.search_step({"step_id": step_id})
        return UpdateStepDto.model_validate(result["steps"][0])

    def get_steps(
        self,
        status: AgentExecutionStatus = AgentExecutionStatus.Pending,
        dids: List[str] = [],
    ) -> GetStepsDtoResult:
        """
        It retrieves all the steps that the agent needs to execute to complete the different tasks assigned.
        This method is used by the AI Agent to retrieve information about the steps part of tasks created by users to the agents owned by the user.

        Args:
            status (AgentExecutionStatus): The status of the steps.
            dids (List[str]): The list of DIDs.

        Returns:
            GetStepsDtoResult: The steps
        """
        params = {}
        if status:
            params["status"] = status.value
        if dids:
            params["dids"] = ",".join(dids)

        query_string = urlencode(params)
        endpoint = (
            f"{self.parse_url_to_backend(GET_BUILDER_STEPS_ENDPOINT)}?{query_string}"
        )

        response = self.get(endpoint)
        response.raise_for_status()
        return GetStepsDtoResult.model_validate(response.json())

    def get_tasks_from_agents(
        self, status: AgentExecutionStatus = AgentExecutionStatus.Pending
    ) -> GetTasksDtoResult:
        """
        It retrieves all the tasks that the agent needs to execute to complete the different tasks assigned.
        This method is used by the AI Agent to retrieve information about the tasks created by users to the agents owned by the user

        Args:
            status (AgentExecutionStatus): The status of the tasks.

        Returns:
            GetTasksDtoResult: The tasks.
        """
        endpoint = f"{self.parse_url_to_backend(GET_AGENTS_ENDPOINT)}"
        if status:
            endpoint += f"?status={status}"
        response = self.get(endpoint)
        response.raise_for_status()
        return GetTasksDtoResult.model_validate(response.json())

    async def subscribe_tasks_updated(
        self, callback: Callable[[TaskEvent], None], tasks: List[str]
    ):
        try:
            if not tasks:
                raise Exception("No task rooms to join in configuration")

            await self.connect_socket()

            async def join_task():
                await self.socket_client.emit(
                    "_join-tasks", json.dumps({"tasks": tasks})
                )
                self.socket_client.on(
                    "_join-tasks_", self._on_connected(callback, tasks)
                )

            self.socket_client.on("_connected", await join_task())
        except Exception as error:
            raise Exception(
                f"Unable to initialize websocket client: {self.web_socket_host} - {str(error)}"
            )

    def _on_connected(self, callback: Callable[[TaskEvent], None], tasks: List[str]):
        def handle_connected_event(*args):
            async def handle_task_update_event(data: Any):
                parsed_data = json.loads(data)
                task_event: TaskEvent = TaskEvent.model_validate(parsed_data)
                if task_event.did != self.did:  # Avoid processing own events
                    await callback(task_event)

            self.socket_client.on("task-updated", handle_task_update_event)

        return handle_connected_event
