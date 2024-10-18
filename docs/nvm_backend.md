<!-- markdownlint-disable -->

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `nvm_backend`






---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L13"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `BackendApiOptions`
Represents the backend API options. 



**Args:**
 
 - <b>`environment`</b> (Environment):  The environment. 
 - <b>`api_key`</b> (Optional[str]):  The Nevermined API Key. This key identify your user and is required to interact with the Nevermined API. You can get your API key by logging in to the Nevermined App. See https://docs.nevermined.app/docs/tutorials/integration/nvm-api-keys 
 - <b>`headers`</b> (Optional[Dict[str, str]]):  Additional headers to send with the requests 
 - <b>`web_socket_options`</b> (Optional[Dict[str, Any]]):  Configuration of the websocket connection 

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L23"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    environment: Environment,
    api_key: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None,
    web_socket_options: Optional[Dict[str, Any]] = None
)
```









---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L36"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `NVMBackendApi`




<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L37"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(opts: BackendApiOptions)
```








---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L80"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `connect_socket`

```python
connect_socket()
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L182"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `delete`

```python
delete(url: str, data: Any, headers: Optional[Dict[str, str]] = None)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L140"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `disconnect`

```python
disconnect()
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L98"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `disconnect_socket`

```python
disconnect_socket()
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L156"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `get`

```python
get(url: str, headers: Optional[Dict[str, str]] = None)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L190"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L128"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `join_room`

```python
join_room(join_account_room: bool, room_ids: Optional[str, List[str]] = None)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L150"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `parse_headers`

```python
parse_headers(additional_headers: dict[str, str]) → dict[str, str]
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L147"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `parse_url_to_backend`

```python
parse_url_to_backend(uri: str) → str
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L144"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `parse_url_to_proxy`

```python
parse_url_to_proxy(uri: str) → str
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L165"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `post`

```python
post(url: str, data: Any, headers: Optional[Dict[str, str]] = None)
```





---

<a href="https://github.com/nevermined-io/payments-py/blob/main/payments_py/nvm_backend.py#L174"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `put`

```python
put(url: str, data: Any, headers: Optional[Dict[str, str]] = None)
```








---

_This file was automatically generated via [lazydocs](https://github.com/ml-tooling/lazydocs)._
