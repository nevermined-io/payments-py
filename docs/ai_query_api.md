<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `ai_query_api`




**Global Variables**
---------------
- **SEARCH_TASKS_ENDPOINT**
- **SEARCH_STEPS_ENDPOINT**
- **CREATE_STEPS_ENDPOINT**
- **UPDATE_STEP_ENDPOINT**
- **GET_AGENTS_ENDPOINT**
- **GET_BUILDER_STEPS_ENDPOINT**
- **GET_TASK_STEPS_ENDPOINT**
- **TASK_ENDPOINT**
- **GET_TASK_ENDPOINT**


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L18"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `AIQueryApi`
Represents the AI Query API. 



**Args:**
 
 - <b>`opts`</b> (BackendApiOptions):  The backend API options 

Methods: 
 - <b>`create_task`</b>:  Creates a task for an agent to execute 
 - <b>`create_steps`</b>:  Creates steps for a task 
 - <b>`update_step`</b>:  Updates a step 
 - <b>`search_tasks`</b>:  Searches for tasks 
 - <b>`get_task_with_steps`</b>:  Gets a task with its steps 
 - <b>`get_steps_from_task`</b>:  Gets the steps from a task 
 - <b>`get_steps`</b>:  Gets the steps 
 - <b>`get_tasks_from_agents`</b>:  Gets the tasks from the agents 
 - <b>`search_step`</b>:  Searches for steps 
 - <b>`get_step`</b>:  Gets the details of a step 

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L37"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(opts: BackendApiOptions)
```








---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L89"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_steps`

```python
create_steps(did: str, task_id: str, steps: Any)
```

It creates the step/s required to complete an AI Task. This method is used by the AI Agent to create the steps required to complete the AI Task. 



**Args:**
 


 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`steps`</b> (Any):  The steps to create. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L64"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_task`

```python
create_task(did: str, task: Any)
```

Subscribers can create an AI Task for an Agent. The task must contain the input query that will be used by the AI Agent. This method is used by subscribers of a Payment Plan required to access a specific AI Agent or Service. Users who are not subscribers won't be able to create AI Tasks for that Agent. Because only subscribers can create AI Tasks, the method requires the access token to interact with the AI Agent/Service. This is given using the `queryOpts` object (accessToken attribute). 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task`</b> (Any):  The task to create. 



**Example:**
 task = {  "query": "https://www.youtube.com/watch?v=0tZFQs7qBfQ",  "name": "transcribe",  "additional_params": [],  "artifacts": [] } task = subscriber.ai_protocol.create_task(agent.did, task) print('Task created:', task.json()) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L171"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_step`

```python
get_step(step_id: str)
```

Get the details of a step. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`step_id`</b> (str):  The step ID. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L183"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_steps`

```python
get_steps(
    status: AgentExecutionStatus = <AgentExecutionStatus.Pending: 'Pending'>,
    dids: List[str] = []
)
```

It retrieves all the steps that the agent needs to execute to complete the different tasks assigned. This method is used by the AI Agent to retrieve information about the steps part of tasks created by users to the agents owned by the user. 



**Args:**
 
 - <b>`status`</b> (AgentExecutionStatus):  The status of the steps. 
 - <b>`dids`</b> (List[str]):  The list of DIDs. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L146"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_steps_from_task`

```python
get_steps_from_task(did: str, task_id: str, status: Optional[str] = None)
```

It retrieves all the steps that the agent needs to execute to complete a specific task associated to the user. This method is used by the AI Agent to retrieve information about the tasks created by users to the agents owned by the user. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`status`</b> (Optional[str]):  The status of the steps. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L130"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_task_with_steps`

```python
get_task_with_steps(did: str, task_id: str)
```

It returns the full task and the steps resulted of the execution of the task. 

This method is used by subscribers of a Payment Plan required to access a specific AI Agent or Service. Users who are not subscribers won't be able to create AI Tasks for that Agent. 





**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L201"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_tasks_from_agents`

```python
get_tasks_from_agents()
```

It retrieves all the tasks that the agent needs to execute to complete the different tasks assigned. This method is used by the AI Agent to retrieve information about the tasks created by users to the agents owned by the user 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L161"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `search_step`

```python
search_step(search_params: Any)
```

It search steps based on the search parameters. The steps belongs to the tasks part of the AI Agents owned by the user. This method is used by the AI Agent to retrieve information about the steps part of tasks created by users to the agents owned by the user. 



**Args:**
 
 - <b>`search_params`</b> (Any):  The search parameters. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L121"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `search_tasks`

```python
search_tasks(search_params: Any)
```

It searches tasks based on the search parameters associated to the user. 



**Args:**
 
 - <b>`search_params`</b> (Any):  The search parameters. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L41"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `subscribe`

```python
subscribe(
    callback: Any,
    join_account_room: bool = True,
    join_agent_rooms: Optional[str, List[str]] = None,
    subscribe_event_types: Optional[List[str]] = None,
    get_pending_events_on_subscribe: bool = True
)
```

It subscribes to the Nevermined network to retrieve new AI Tasks requested by other users. This method is used by AI agents to subscribe and receive new AI Tasks sent by other subscribers. 



**Args:**
 
 - <b>`callback`</b> (Any):  The callback function to be called when a new event is received. 
 - <b>`join_account_room`</b> (bool):  If True, it will join the account room. 
 - <b>`join_agent_rooms`</b> (Optional[Union[str, List[str]]]):  The agent rooms to join. 
 - <b>`subscribe_event_types`</b> (Optional[List[str]]):  The event types to subscribe to. 
 - <b>`get_pending_events_on_subscribe`</b> (bool):  If True, it will get the pending events on subscribe. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L103"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `update_step`

```python
update_step(did: str, task_id: str, step_id: str, step: Any)
```

It updates the step with the new information. This method is used by the AI Agent to update the status and output of an step. This method can not be called by a subscriber. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`step_id`</b> (str):  The step ID. 
 - <b>`step`</b> (Any):  The step object to update. https://docs.nevermined.io/docs/protocol/query-protocol#steps-attributes 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
