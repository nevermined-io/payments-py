<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `ai_query_api`




**Global Variables**
---------------
- **SEARCH_TASKS_ENDPOINT**
- **CREATE_STEPS_ENDPOINT**
- **UPDATE_STEP_ENDPOINT**
- **GET_AGENTS_ENDPOINT**
- **GET_BUILDER_STEPS_ENDPOINT**
- **GET_TASK_STEPS_ENDPOINT**
- **TASK_ENDPOINT**
- **GET_TASK_ENDPOINT**


---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L16"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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
 - <b>`get_service_token`</b>:  Gets the service token 

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L34"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(opts: BackendApiOptions)
```








---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L71"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_steps`

```python
create_steps(did: str, task_id: str, steps: Any)
```

Creates steps for a task. 



**Args:**
 


 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`steps`</b> (Any):  The steps to create. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L53"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `create_task`

```python
create_task(did: str, task: Any, jwt: Optional[str] = None)
```

Creates a task for an agent to execute. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task`</b> (Any):  The task to create. 
 - <b>`jwt`</b> (Optional[str]):  The JWT token. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L166"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_service_token`

```python
get_service_token(service_did: str) → ServiceTokenResultDto
```

Gets the service token. 



**Args:**
 
 - <b>`service_did`</b> (str):  The DID of the service. 



**Returns:**
 
 - <b>`ServiceTokenResultDto`</b>:  The result of the creation operation. 



**Raises:**
 
 - <b>`HTTPError`</b>:  If the API call fails. 



**Example:**
 response = your_instance.get_service_token(service_did="did:nv:xyz789") print(response) 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L143"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_steps`

```python
get_steps(
    status: AgentExecutionStatus = <AgentExecutionStatus.Pending: 'Pending'>,
    dids: List[str] = []
)
```

Gets the steps. 



**Args:**
 
 - <b>`status`</b> (AgentExecutionStatus):  The status of the steps. 
 - <b>`dids`</b> (List[str]):  The list of DIDs. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L129"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_steps_from_task`

```python
get_steps_from_task(did: str, task_id: str, status: Optional[str] = None)
```

Gets the steps from a task. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`status`</b> (Optional[str]):  The status of the steps. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L117"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_task_with_steps`

```python
get_task_with_steps(did: str, task_id: str, jwt: Optional[str] = None)
```

Gets a task with its steps. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`jwt`</b> (Optional[str]):  The JWT token. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L160"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get_tasks_from_agents`

```python
get_tasks_from_agents()
```

Gets the tasks from the agents. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L108"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `search_tasks`

```python
search_tasks(search_params: Any)
```

Searches for tasks. 



**Args:**
 
 - <b>`search_params`</b> (Any):  The search parameters. 

---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L38"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `subscribe`

```python
subscribe(callback: Any, events: Optional[str] = None)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/ai_query_api.py#L84"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `update_step`

```python
update_step(
    did: str,
    task_id: str,
    step_id: str,
    step: Any,
    jwt: Optional[str] = None
)
```

Updates a step. 



**Args:**
 
 - <b>`did`</b> (str):  The DID of the service. 
 - <b>`task_id`</b> (str):  The task ID. 
 - <b>`step_id`</b> (str):  The step ID. 
 - <b>`step`</b> (Any):  The step to update. 
 - <b>`jwt`</b> (Optional[str]):  The JWT token. 




---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
